"""
decisionEngine.py
─────────────────────────────────────────────────────────────────────
Layer 2 — 최종 판정자. 순수 결정론 함수.
동일 입력 → 항상 동일 출력. LLM 호출 없음.

설계 원칙
- 규칙·LLM 신호는 '출처 신뢰계수'만큼만 점수에 반영.
- 모든 점수 변동을 audit_trail 에 기록(설명가능성).
- 충돌(예: 의약학 지망 + 수학 약점)은 명시적 규칙으로 결정론 해소.
"""
from __future__ import annotations
from collections import defaultdict
from typing import Dict, List, Optional

RULE_VERSION = "decision-2026.05-v1.0"

# 신호 출처별 신뢰계수 (고정 상수. 검증 루프에서만 변경)
SOURCE_WEIGHT = {
    "consensus": 1.00,   # 규칙·LLM 합의
    "rule": 0.85,        # 규칙 단독
    "llm": 0.55,         # LLM 단독
    "html": 0.40,        # HTML 추정(레거시)
}

# CLUSTER_ENUM → 내부 카테고리 가중치
CLUSTER_TO_CATEGORY = {
    "인문·언어":   {"국어국문·언어": 25, "역사·철학·윤리": 10},
    "사회·정치":   {"사회과학": 25, "역사·철학·윤리": 8},
    "경영·경제":   {"경영·경제": 25},
    "미디어·콘텐츠": {"미디어·광고·콘텐츠": 25, "국어국문·언어": 10},
    "수리·통계":   {"수학·통계": 25, "인공지능·데이터사이언스": 10},
    "컴퓨터·AI":   {"인공지능·데이터사이언스": 22, "컴퓨터·소프트웨어": 20},
    "공학":        {"기계·로봇·모빌리티": 18, "전기·전자·반도체": 14, "화공·신소재·에너지공학": 12},
    "생명·바이오": {"생명과학·바이오": 25},
    "의약학":      {"의학": 28, "약학": 14, "간호": 8},
    "교육":        {"교육": 25},
    "예술·디자인": {"디자인·예술": 25},
    "융합":        {},  # 단일 계열로 몰지 않음
}

SUBJECT_TO_CATEGORY = {
    "국어":     {"국어국문·언어": 16, "미디어·광고·콘텐츠": 8},
    "영어":     {"국어국문·언어": 6, "사회과학": 4},
    "수학":     {"수학·통계": 16, "인공지능·데이터사이언스": 8},
    "물리":     {"물리·화학·기초과학": 14, "전기·전자·반도체": 8, "기계·로봇·모빌리티": 6},
    "화학":     {"물리·화학·기초과학": 12, "화공·신소재·에너지공학": 8},
    "생명과학": {"생명과학·바이오": 16, "의학": 8},
    "지구과학": {"환경·지구과학": 14},
    "사회문화": {"사회과학": 14},
    "정치와법": {"사회과학": 14},
    "경제":     {"경영·경제": 14},
}


def _add(scores, audit, cat, pts, frm, source, ev_idx=None):
    if abs(pts) < 1e-9:
        return
    scores[cat] += pts
    audit.append({"category": cat, "delta": round(pts, 2),
                  "from": frm, "source": source, "evidence_q": ev_idx})


def _consensus(rule_set, llm_set):
    """규칙·LLM 신호 합의/단독 분류."""
    r, l = set(rule_set or []), set(llm_set or [])
    return {
        "consensus": sorted(r & l),
        "rule_only": sorted(r - l),
        "llm_only": sorted(l - r),
    }


def decide(rule_sig: Dict, llm_sig: Optional[Dict],
           base_category_scores: Optional[Dict] = None) -> Dict:
    """
    최종 판정. rule_sig(필수) + llm_sig(선택) + HTML 기반 base 점수(선택).
    """
    scores = defaultdict(float)
    audit: List[Dict] = []

    # 0) HTML 레거시 점수는 낮은 신뢰계수로만 시드
    if base_category_scores:
        w = SOURCE_WEIGHT["html"]
        for cat, v in base_category_scores.items():
            if v > 0:
                _add(scores, audit, cat, v * w * 0.20, "html_base", "html")

    llm_sig = llm_sig or {}

    # 1) 강점 과목
    cs = _consensus(rule_sig.get("strong_subjects"), llm_sig.get("strong_subjects"))
    for grp, src in [("consensus", "consensus"), ("rule_only", "rule"), ("llm_only", "llm")]:
        for subj in cs[grp]:
            for cat, pts in SUBJECT_TO_CATEGORY.get(subj, {}).items():
                _add(scores, audit, cat, pts * SOURCE_WEIGHT[src],
                     f"strong_subject:{subj}", src)

    # 2) 약점 과목 → 해당 계열 감점
    cw = _consensus(rule_sig.get("weak_subjects"), llm_sig.get("weak_subjects"))
    for grp, src in [("consensus", "consensus"), ("rule_only", "rule"), ("llm_only", "llm")]:
        for subj in cw[grp]:
            for cat, pts in SUBJECT_TO_CATEGORY.get(subj, {}).items():
                _add(scores, audit, cat, -pts * 0.7 * SOURCE_WEIGHT[src],
                     f"weak_subject:{subj}", src)

    # 3) 진로 클러스터 (규칙 확정 + LLM 정규화 합의)
    rule_clusters = rule_sig.get("career_clusters", [])
    llm_clusters = llm_sig.get("career_clusters", [])
    cc = _consensus(rule_clusters, llm_clusters)
    is_fusion = bool(llm_sig.get("is_fusion")) or len(set(rule_clusters)) >= 3
    for grp, src in [("consensus", "consensus"), ("rule_only", "rule"), ("llm_only", "llm")]:
        cl_list = cc[grp]
        for c in cl_list:
            factor = 0.6 if (is_fusion and len(cl_list) > 1) else 1.0
            for cat, pts in CLUSTER_TO_CATEGORY.get(c, {}).items():
                _add(scores, audit, cat, pts * factor * SOURCE_WEIGHT[src],
                     f"career_cluster:{c}", src)

    # 4) 문이과 단서(규칙) — 약한 가중
    th = rule_sig.get("track_hint")
    if th == "sci":
        for cat in ["수학·통계", "물리·화학·기초과학", "컴퓨터·소프트웨어"]:
            _add(scores, audit, cat, 6 * SOURCE_WEIGHT["rule"], "track_hint:sci", "rule")
    elif th == "hum":
        for cat in ["국어국문·언어", "사회과학", "미디어·광고·콘텐츠"]:
            _add(scores, audit, cat, 6 * SOURCE_WEIGHT["rule"], "track_hint:hum", "rule")

    # 5) 충돌 해소(결정론) — 의약학 명시 지망 시 STEM 오분류 억제
    all_clusters = list(rule_clusters) + list(llm_clusters)
    hint_txt = " ".join(rule_sig.get("career_cluster_hints", []))
    txt = " ".join(all_clusters) + " " + hint_txt + " " + (rule_sig.get("target_tier_text") or "")
    med_intent = ("의약학" in all_clusters) or any(
        k in txt for k in ["의대", "의예", "약대", "한의", "치대", "수의대", "의사", "약사"]
    )
    if med_intent:
        for cat in ["인공지능·데이터사이언스", "컴퓨터·소프트웨어"]:
            if scores.get(cat, 0) > scores.get("의학", 0):
                before = scores[cat]
                scores[cat] *= 0.4
                audit.append({"category": cat, "delta": round(scores[cat]-before, 2),
                              "from": "conflict_rule:의약학지망_우선",
                              "source": "deterministic", "evidence_q": None})
        _add(scores, audit, "의학", 20, "med_intent_boost", "rule")

    ranked = sorted(scores.items(), key=lambda x: -x[1])
    return {
        "category_scores": {k: round(v, 2) for k, v in scores.items()},
        "top_categories": [c for c, _ in ranked[:3]],
        "ranked": ranked,
        "audit_trail": audit,
        "decision_version": RULE_VERSION,
        "is_fusion": is_fusion,
        "reproducible": True,
    }
