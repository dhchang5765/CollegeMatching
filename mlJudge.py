"""
mlJudge.py
─────────────────────────────────────────────────────────────────────
ML 판정 슬롯. 현재 데이터(레이블된 합격결과 4건 미만)에서는
'판정자'가 아니라 '교차검증 자문'으로만 동작한다.

활성화 게이트
- 검증된 합격결과(outcome label) 수가 MIN_LABELS 이상이어야
  ML 이 '보조 판정'에 참여할 수 있다(그래도 최종 결정은 규칙 엔진).
- 그 전까지는 prototype distance(레퍼런스 프로파일과의 거리)만 계산해
  규칙 판정과 어긋나면 'low confidence' 플래그만 띄운다.

이렇게 설계하는 이유(사실):
- 피처 ~200, 표본 <5 → 지도학습은 통계적으로 과적합. 학습 불가.
- 질문지가 버전별로 다르므로 피처는 slot_id 기준으로만 정렬 가능.
"""
from __future__ import annotations
import json
import os
from typing import Dict, List, Optional, Tuple

from answer_schema import SEMANTIC_SLOTS

MIN_LABELS = 60          # 이 수 이상 검증 레이블이 쌓이면 ML 보조판정 허용
PROTOTYPE_STORE = "ml_prototypes.json"


def _vec(feature_vector: Dict[str, str]) -> List[str]:
    """slot_id 순서 고정 → 버전 무관 정렬된 범주형 벡터."""
    return [feature_vector.get(s, "") for s in SEMANTIC_SLOTS]


def _hamming(a: List[str], b: List[str]) -> float:
    """범주형 거리(정규화 해밍). 0=동일, 1=완전상이."""
    if not a:
        return 1.0
    diff = sum(1 for x, y in zip(a, b) if x != y)
    return diff / len(a)


def load_prototypes() -> List[Dict]:
    if not os.path.exists(PROTOTYPE_STORE):
        return []
    try:
        with open(PROTOTYPE_STORE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def label_count() -> int:
    return sum(1 for p in load_prototypes() if p.get("verified_outcome"))


def ml_status() -> Dict:
    n = label_count()
    return {
        "labeled": n,
        "threshold": MIN_LABELS,
        "mode": "assist" if n >= MIN_LABELS else "advisory_only",
        "is_judge": False,  # 어떤 경우에도 ML 단독 판정 금지
    }


def cross_check(feature_vector: Dict[str, str],
                rule_top_categories: List[str]) -> Dict:
    """
    레퍼런스 프로토타입과의 최근접 비교.
    - advisory_only: 규칙 판정과 불일치 시 confidence 경고만.
    - assist: 최근접 K개의 검증 결과를 다수결로 '보조 의견' 제시(여전히 비판정).
    """
    protos = load_prototypes()
    status = ml_status()
    if not protos:
        return {"available": False, "status": status, "is_judge": False,
                "confidence_flag": "ok",
                "note": "축적된 레퍼런스 없음 — 규칙 판정 100% 채택"}

    target = _vec(feature_vector)
    scored: List[Tuple[float, Dict]] = []
    for p in protos:
        d = _hamming(target, _vec(p.get("feature_vector", {})))
        scored.append((d, p))
    scored.sort(key=lambda x: x[0])
    k = min(5, len(scored))
    neighbors = scored[:k]

    nn_categories: List[str] = []
    for _, p in neighbors:
        if p.get("verified_outcome"):
            nn_categories.append(p["verified_outcome"])

    agree = bool(nn_categories) and (nn_categories[0] in rule_top_categories)
    result = {
        "available": True,
        "status": status,
        "nearest_distance": round(neighbors[0][0], 3),
        "neighbor_outcomes": nn_categories,
        "agrees_with_rule": agree,
        "confidence_flag": "ok" if (not nn_categories or agree) else "review",
        "is_judge": False,
    }
    return result


def register_prototype(student_key: str, feature_vector: Dict[str, str],
                        verified_outcome: Optional[str] = None) -> None:
    """검증 루프에서 호출. 실제 합격결과(verified_outcome)와 함께 누적."""
    protos = load_prototypes()
    protos = [p for p in protos if p.get("student_key") != student_key]
    protos.append({
        "student_key": student_key,
        "feature_vector": feature_vector,
        "verified_outcome": verified_outcome,  # None 이면 미검증(학습 미사용)
    })
    try:
        with open(PROTOTYPE_STORE, "w", encoding="utf-8") as f:
            json.dump(protos, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
