# app.py
from __future__ import annotations


import os
import time
import json
from dotenv import load_dotenv

# Load .env from this folder (so OPENAI_API_KEY works without exporting it in shell)
HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, '.env'))

from typing import Any, Dict
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from openai import OpenAI
from world_model import WM

# -------------------------
# App
# -------------------------
app = FastAPI(title="Shapka (Thinking Cap v0)", version="0.1")

# -------------------------
# Files (UI)
# -------------------------
# We keep index.html and app.js in the same folder as app.py (backend/).
HERE = os.path.dirname(os.path.abspath(__file__))

@app.get("/")
def index():
    return FileResponse(os.path.join(HERE, "index.html"), media_type="text/html")

@app.get("/app.js")
def app_js():
    return FileResponse(os.path.join(HERE, "app.js"), media_type="application/javascript")

@app.get("/favicon.ico")
def favicon():
    # optional, avoid 404 spam in console
    # Return 204 if no favicon file exists.
    path = os.path.join(HERE, "favicon.ico")
    if os.path.exists(path):
        return FileResponse(path, media_type="image/x-icon")
    return JSONResponse(status_code=204, content=None)

# -------------------------
# OpenAI client
# -------------------------
def _get_client() -> OpenAI:
    # OpenAI python SDK will also read OPENAI_API_KEY automatically,
    # but we keep it explicit and fail with a clean JSON error.
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return OpenAI(api_key=api_key)

client = None
try:
    client = _get_client()
except Exception:
    # we will error lazily in /run with a JSON message
    client = None

# -------------------------
# API models
# -------------------------
class RunRequest(BaseModel):
    text: str

# -------------------------
# Helpers
# -------------------------
def _safe_json_error(msg: str, status_code: int = 500) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"ok": False, "error": msg})

def _call_llm(user_text: str) -> str:
    """
    Vanilla LLM call — must not change logic of your existing prompt strategy.
    """
    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": user_text}],
    )
    return resp.choices[0].message.content or ""

def _call_cap(user_text: str) -> str:
    """
    Thinking Cap call — same model, but you can route a different prompt later.
    For now it's identical input, different consumer downstream.
    """
    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": user_text}],
    )
    return resp.choices[0].message.content or ""

# -------------------------
# Endpoints
# -------------------------
@app.post("/run")
def run(req: RunRequest):
    global client
    if client is None:
        try:
            client = _get_client()
        except Exception as e:
            return _safe_json_error(str(e), status_code=500)

    user_text = req.text

    try:
        # --- Vanilla
        t0 = time.time()
        raw_text = _call_llm(user_text)
        raw_ms = int((time.time() - t0) * 1000)

        # --- Cap
        t1 = time.time()
        cap_text = _call_cap(user_text)
        cap_ms = int((time.time() - t1) * 1000)

        # --- World Model update (purely deterministic; safe)
        wm_t0 = time.time()
        wm_update = WM.update_from_observation(
            user_text=user_text,
            raw_text=raw_text,
            cap_text=cap_text,
        )
        wm_ms = int((time.time() - wm_t0) * 1000)

        return JSONResponse(
            content={
                "ok": True,
                "input": user_text,
                "raw": raw_text,
                "cap": cap_text,
                "wm": wm_update,
                "metrics": {"raw_ms": raw_ms, "cap_ms": cap_ms, "wm_ms": wm_ms},
            }
        )
    except Exception as e:
        # IMPORTANT: always return JSON, иначе фронт ловит "Unexpected token I"
        return _safe_json_error(f"/run failed: {type(e).__name__}: {e}", status_code=500)

@app.get("/wm")
def world_model():
    # Current snapshot of the world model
    return JSONResponse(content={"ok": True, "wm": WM.to_json()})

@app.get("/wm_view")
def world_model_view():
    # Simple built-in viewer
    return FileResponse(os.path.join(HERE, "wm.html"), media_type="text/html")

@app.get("/wm.js")
def world_model_js():
    return FileResponse(os.path.join(HERE, "wm.js"), media_type="application/javascript")
