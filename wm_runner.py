#!/usr/bin/env python3
"""
Headless World-Model growth runner for "Shapka".

What it does
- Runs without any web UI.
- Auto-generates prompts (from a seed list + optional self-generated next prompts),
  queries the LLM, and feeds the results into WorldModel.apply_observation(...).
- Persists the evolving world model to a JSON file after every step.

Requirements
- Same venv as your backend (fastapi not required here)
- OPENAI_API_KEY must be available in environment or .env in the same folder
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
from openai import OpenAI

from world_model import WorldModel


# --------- Prompts (kept here, not in app.py) ----------

RAW_SYSTEM = "You are a helpful assistant. Answer normally, concisely."

CAP_SYSTEM = """You are "Thinking Cap": extract structured relations from the RAW answer.
Return ONLY valid JSON (no markdown), with this schema:
{
  "answer": "<short answer or empty>",
  "triples": [
    {"src": "...", "rel": "...", "dst": "...", "w": 0.0-1.0}
  ],
  "notes": ["..."]
}
Rules:
- Keep src/dst as short noun phrases.
- rel must be short verb/edge label (e.g. 'causes', 'located_in', 'is', 'wants', 'uses').
- If you cannot extract anything, return {"answer":"", "triples":[], "notes":["no triples"]}.
"""

NEXT_PROMPT_SYSTEM = """You propose the next prompts to grow a world model.
Given the current WM summary and the last user prompt, suggest 3 next prompts.
Return ONLY valid JSON: {"prompts":["...","...","..."]}.
Prompts should be concrete and likely to yield factual/relational triples.
"""


def _strip_code_fences(s: str) -> str:
    s = (s or "").strip()
    if s.startswith("```"):
        # remove leading/trailing fences
        s = s.strip("`")
        # if language label present, drop first line
        lines = s.splitlines()
        if lines and lines[0].strip().lower() in {"json", "javascript", "js"}:
            s = "\n".join(lines[1:])
    return s.strip()


def llm_chat(client: OpenAI, model: str, system: str, user: str) -> str:
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content or ""


def ensure_env():
    # Load .env from current working dir (the folder where you run this)
    load_dotenv()
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set (env or .env).")


def load_seeds(seed_file: Optional[str]) -> List[str]:
    if not seed_file:
        return []
    p = Path(seed_file)
    if not p.exists():
        raise FileNotFoundError(f"Seed file not found: {p}")
    lines = [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines()]
    return [ln for ln in lines if ln and not ln.startswith("#")]


def append_jsonl(path: Path, obj: Dict[str, Any]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def save_wm(path: Path, wm: WorldModel):
    path.write_text(wm.to_json(pretty=True), encoding="utf-8")


def propose_next_prompts(client: OpenAI, model: str, wm: WorldModel, last_prompt: str) -> List[str]:
    summary = wm.summary(limit_edges=12)
    user = json.dumps({"wm": summary, "last_prompt": last_prompt}, ensure_ascii=False)
    out = llm_chat(client, model=model, system=NEXT_PROMPT_SYSTEM, user=user)
    out = _strip_code_fences(out)
    try:
        data = json.loads(out)
        prompts = data.get("prompts", [])
        if isinstance(prompts, list):
            return [str(p).strip() for p in prompts if str(p).strip()]
    except Exception:
        return []
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gpt-4.1-mini")
    ap.add_argument("--steps", type=int, default=20)
    ap.add_argument("--interval", type=float, default=0.0, help="sleep seconds between steps")
    ap.add_argument("--seed-file", default="", help="text file with initial prompts (one per line)")
    ap.add_argument("--state", default="wm_state.json", help="world model snapshot output")
    ap.add_argument("--log", default="wm_log.jsonl", help="event log output")
    ap.add_argument("--self-prompts", action="store_true", help="ask LLM to propose next prompts")
    args = ap.parse_args()

    ensure_env()
    client = OpenAI()

    wm = WorldModel()
    queue: List[str] = load_seeds(args.seed_file)

    if not queue:
        # reasonable default seeds (can be replaced)
        queue = [
            "Describe the main entities in the current system and how they interact.",
            "What are common causes of JSON parse failures in browser fetch handlers?",
            "What are typical components of a minimal world model store and viewer?",
        ]

    state_path = Path(args.state)
    log_path = Path(args.log)

    for i in range(1, args.steps + 1):
        prompt = queue.pop(0)

        t0 = time.time()
        raw = llm_chat(client, model=args.model, system=RAW_SYSTEM, user=prompt)
        t1 = time.time()

        cap_user = json.dumps({"prompt": prompt, "raw": raw}, ensure_ascii=False)
        cap = llm_chat(client, model=args.model, system=CAP_SYSTEM, user=cap_user)
        t2 = time.time()

        # Feed into WM
        wm.apply_observation(user_text=prompt, raw_text=raw, cap_text=cap)

        # Persist
        save_wm(state_path, wm)
        append_jsonl(log_path, {
            "i": i,
            "prompt": prompt,
            "timing_ms": {"raw": int((t1 - t0) * 1000), "cap": int((t2 - t1) * 1000)},
            "wm_snapshot": json.loads(wm.to_json(pretty=False)).get("snapshot", {}),
        })

        # Optionally extend queue
        if args.self_prompts:
            more = propose_next_prompts(client, model=args.model, wm=wm, last_prompt=prompt)
            for p in more:
                if p not in queue:
                    queue.append(p)

        if args.interval > 0:
            time.sleep(args.interval)

    print(f"OK. Saved: {state_path} (snapshot), {log_path} (events)")


if __name__ == "__main__":
    main()
