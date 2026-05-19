"""
validationLoop.py
─────────────────────────────────────────────────────────────────────
Layer 3 — 검증 루프. 사람(입학사정관/교사)은 여기에만 개입한다.
개별 학생 판정에는 절대 개입하지 않는다.

역할
- 예측(top_categories) vs 실제 합격결과를 누적 기록.
- 분기별 적중률 집계 → 규칙 가중치 튜닝 근거 산출.
- 검증된 결과는 mlJudge 프로토타입으로 승격(레이블 공급).
"""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

from mlJudge import register_prototype

OUTCOME_LOG = "validation_outcomes.jsonl"


def record_prediction(student_key: str, decision: Dict,
                       feature_vector: Dict[str, str]) -> None:
    """판정 직후 호출. 예측 스냅샷 저장(결과는 추후 갱신)."""
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "student_key": student_key,
        "predicted_top": decision.get("top_categories"),
        "decision_version": decision.get("decision_version"),
        "feature_vector": feature_vector,
        "verified_outcome": None,
    }
    with open(OUTCOME_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def attach_outcome(student_key: str, actual_category: str) -> None:
    """실제 합격 결과 확정 시 호출(사람이 입력). 프로토타입으로 승격."""
    rows = _read_all()
    fv = None
    for r in rows:
        if r["student_key"] == student_key:
            r["verified_outcome"] = actual_category
            fv = r.get("feature_vector")
    _rewrite(rows)
    if fv is not None:
        register_prototype(student_key, fv, verified_outcome=actual_category)


def accuracy_report() -> Dict:
    rows = [r for r in _read_all() if r.get("verified_outcome")]
    if not rows:
        return {"labeled": 0, "hit_rate": None,
                "note": "검증된 합격결과 없음 — 규칙 엔진 단독 운용"}
    hit = sum(1 for r in rows
              if r["verified_outcome"] in (r.get("predicted_top") or []))
    return {
        "labeled": len(rows),
        "hit_rate": round(hit / len(rows), 3),
        "by_version": _group_hit_by_version(rows),
    }


def _group_hit_by_version(rows: List[Dict]) -> Dict:
    agg: Dict[str, List[int]] = {}
    for r in rows:
        v = r.get("decision_version", "unknown")
        ok = 1 if r["verified_outcome"] in (r.get("predicted_top") or []) else 0
        agg.setdefault(v, []).append(ok)
    return {k: round(sum(v) / len(v), 3) for k, v in agg.items()}


def _read_all() -> List[Dict]:
    if not os.path.exists(OUTCOME_LOG):
        return []
    out = []
    with open(OUTCOME_LOG, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    return out


def _rewrite(rows: List[Dict]) -> None:
    with open(OUTCOME_LOG, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
