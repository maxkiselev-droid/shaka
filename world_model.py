# world_model.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Any
import time
import json
import re
import hashlib


def _now_ms() -> int:
    return int(time.time() * 1000)


def _stable_id(s: str) -> str:
    h = hashlib.sha1(s.encode("utf-8", errors="ignore")).hexdigest()[:10]
    return h


def _strip_code_fence(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s)
    return s.strip()


def _try_parse_json(s: str) -> Any | None:
    try:
        return json.loads(s)
    except Exception:
        return None


def _simple_extract_triples(text: str) -> List[Tuple[str, str, str]]:
    """
    Очень простой (детерминированный) извлекатель отношений.
    Это "fallback", чтобы WM работала даже если LLM не дал структуру.

    Формат трипла: (subject, relation, object)
    """
    triples: List[Tuple[str, str, str]] = []

    # Примитив: "X это Y"
    m = re.findall(r"([A-Za-zА-Яа-я0-9_\- ]{2,80})\s+это\s+([A-Za-zА-Яа-я0-9_\- ]{2,80})", text)
    for a, b in m[:20]:
        a = a.strip()
        b = b.strip()
        if a and b:
            triples.append((a, "is_a", b))

    # Примитив: "X содержит Y"
    m2 = re.findall(r"([A-Za-zА-Яа-я0-9_\- ]{2,80})\s+содержит\s+([A-Za-zА-Яа-я0-9_\- ]{2,80})", text)
    for a, b in m2[:20]:
        triples.append((a.strip(), "contains", b.strip()))

    return triples


@dataclass
class Edge:
    src: str
    rel: str
    dst: str
    w: float = 0.5  # “belief weight” 0..1
    n: int = 1      # сколько раз подтверждалось
    last_ms: int = field(default_factory=_now_ms)


@dataclass
class WorldModel:
    """
    W: objects + arrows (категориально: объекты + морфизмы)
    B: веса/уверенность на морфизмах
    M: наблюдения (лог)
    """
    nodes: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    edges: Dict[str, Edge] = field(default_factory=dict)
    obs_log: List[Dict[str, Any]] = field(default_factory=list)

    def _ensure_node(self, label: str) -> str:
        label = label.strip()
        nid = _stable_id(label.lower())
        if nid not in self.nodes:
            self.nodes[nid] = {"id": nid, "label": label, "created_ms": _now_ms()}
        return nid

    def _edge_key(self, src: str, rel: str, dst: str) -> str:
        return f"{src}::{rel}::{dst}"

    def add_edge(self, src_label: str, rel: str, dst_label: str, strength: float = 0.55) -> Dict[str, Any]:
        src = self._ensure_node(src_label)
        dst = self._ensure_node(dst_label)
        k = self._edge_key(src, rel, dst)

        if k not in self.edges:
            self.edges[k] = Edge(src=src, rel=rel, dst=dst, w=float(strength), n=1)
            return {"action": "edge_added", "src": src_label, "rel": rel, "dst": dst_label, "w": self.edges[k].w}
        else:
            e = self.edges[k]
            e.n += 1
            # очень простое “bayesian-ish” усиление: вес чуть растет при подтверждениях
            e.w = min(0.99, e.w + 0.05)
            e.last_ms = _now_ms()
            return {"action": "edge_reinforced", "src": src_label, "rel": rel, "dst": dst_label, "w": e.w, "n": e.n}

    def update_from_observation(self, user_text: str, raw_text: str, cap_text: str) -> Dict[str, Any]:
        """
        Принимаем наблюдение m = (user_text, raw_text, cap_text)
        Пытаемся вытащить структуру из cap JSON (если есть),
        иначе fallback: простые триплы из raw.
        """
        t0 = _now_ms()

        cap_clean = _strip_code_fence(cap_text or "")
        cap_obj = _try_parse_json(cap_clean)

        triples: List[Tuple[str, str, str]] = []
        source = "fallback_raw"

        # Если cap дал структуру — используем её
        # Ожидаем (минимально): cap_obj["world_delta"]["triples"] или cap_obj["triples"]
        if isinstance(cap_obj, dict):
            if isinstance(cap_obj.get("triples"), list):
                for item in cap_obj["triples"][:50]:
                    if isinstance(item, dict) and {"s", "r", "o"} <= set(item.keys()):
                        triples.append((str(item["s"]), str(item["r"]), str(item["o"])))
                if triples:
                    source = "cap.triples"
            elif isinstance(cap_obj.get("world_delta"), dict) and isinstance(cap_obj["world_delta"].get("triples"), list):
                for item in cap_obj["world_delta"]["triples"][:50]:
                    if isinstance(item, dict) and {"s", "r", "o"} <= set(item.keys()):
                        triples.append((str(item["s"]), str(item["r"]), str(item["o"])))
                if triples:
                    source = "cap.world_delta.triples"

        # Fallback
        if not triples:
            triples = _simple_extract_triples(raw_text or "")
            source = "fallback_raw"

        applied: List[Dict[str, Any]] = []
        for s, r, o in triples[:30]:
            applied.append(self.add_edge(s, r, o, strength=0.55))

        obs = {
            "ts_ms": _now_ms(),
            "user_text": user_text,
            "source": source,
            "n_triples": len(triples),
        }
        self.obs_log.append(obs)

        dt = _now_ms() - t0
        return {
            "ok": True,
            "source": source,
            "applied": applied,
            "snapshot": {"nodes": len(self.nodes), "edges": len(self.edges), "obs": len(self.obs_log)},
            "wm_ms": dt,
        }

    def to_json(self, limit_edges: int = 200) -> Dict[str, Any]:
        edges_list = list(self.edges.values())
        # сортируем по “силе”
        edges_list.sort(key=lambda e: (e.w, e.n), reverse=True)

        def node_label(nid: str) -> str:
            return self.nodes.get(nid, {}).get("label", nid)

        return {
            "snapshot": {"nodes": len(self.nodes), "edges": len(self.edges), "obs": len(self.obs_log)},
            "top_edges": [
                {"src": node_label(e.src), "rel": e.rel, "dst": node_label(e.dst), "w": e.w, "n": e.n}
                for e in edges_list[:limit_edges]
            ],
        }


WM = WorldModel()
