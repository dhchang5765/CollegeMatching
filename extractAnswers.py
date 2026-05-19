"""
extractAnswers.py
─────────────────────────────────────────────────────────────────────
Layer 1 (규칙 기반 추출기). answer_schema 의 정규화 슬롯에서
결정론적으로 신호를 추출한다. 동일 입력 → 동일 출력.

출력 신호는 모두 evidence(출처 문항 idx)를 동반한다.
근거 없는 신호는 만들지 않는다.
"""
from __future__ import annotations
import re
from typing import Dict, List, Optional

_SUBJECTS = [
    "국어", "영어", "수학", "물리", "화학", "생명과학", "생명", "지구과학",
    "사회문화", "정치와법", "정치", "경제", "윤리", "한국사", "세계사",
    "지리", "사회", "과학", "탐구",
]


def _subject_in(text: str) -> List[str]:
    """choice_text 에서 명시된 과목명만 추출(추정 없음)."""
    found = []
    for s in _SUBJECTS:
        if s in text:
            found.append(s)
    # '사회'는 '사회문화/정치와법'이 있으면 중복 제거
    if any(x in found for x in ["사회문화", "정치와법", "경제", "정치"]) and "사회" in found:
        found.remove("사회")
    if "생명과학" in found and "생명" in found:
        found.remove("생명")
    return list(dict.fromkeys(found))


def _is_negative(text: str) -> bool:
    """선택지가 '없다/별로/모른다/싫다' 류 부정인지."""
    neg = ["없어", "없다", "별로", "모르", "막막", "싫", "안 ", "아직", "딱히", "못"]
    return any(n in text for n in neg)


# 명시적 진로 키워드 → CLUSTER_ENUM (LLM 없이도 결정론 처리)
# 모호/나열형은 LLM 보강 대상으로 남기고, 여기서는 명백한 것만.
CLUSTER_KEYWORDS = {
    "의약학": ["의대", "치대", "한의대", "약대", "수의대", "의사", "약사",
              "의예", "한의", "치의", "수의", "의료/보건", "생명과 건강"],
    "컴퓨터·AI": ["코딩", "프로그래", "컴퓨터", "공대 계열", "소프트웨어",
                 "인공지능", "AI ", "데이터 분석", "개발자"],
    "공학": ["공학", "기계", "전자", "반도체", "건축", "토목", "로봇"],
    "생명·바이오": ["생명공학", "바이오", "유전", "제약 연구", "생명과학자"],
    "미디어·콘텐츠": ["언론", "미디어", "아나운서", "PD", "유튜버", "방송",
                   "콘텐츠", "기자", "광고"],
    "사회·정치": ["정치", "법", "정의", "외교", "행정", "변호사", "판사", "검사"],
    "경영·경제": ["경영", "마케터", "투자", "금융", "CEO", "창업", "경제"],
    "인문·언어": ["작가", "문학", "어문", "번역", "언어학", "글 쓰"],
    "교육": ["교사", "교수", "교육자", "선생님"],
    "예술·디자인": ["디자인", "예술", "미술", "음악", "건축가 디자인"],
}


def _clusters_from_text(text: str) -> List[str]:
    hits = []
    for cluster, kws in CLUSTER_KEYWORDS.items():
        if any(k in text for k in kws):
            hits.append(cluster)
    return hits


def extract_rule_signals(normalized: Dict) -> Dict:
    """슬롯 → 규칙 신호. 각 신호에 evidence_idx 부착."""
    slots = normalized.get("slots", {})
    sig = {
        "strong_subjects": [],
        "weak_subjects": [],
        "track_hint": None,          # 'sci' | 'hum' | None
        "career_cluster_hints": [],  # 자유 텍스트 단서(LLM 정규화 대상)
        "career_clusters": [],       # 규칙으로 확정한 CLUSTER_ENUM (결정론)
        "target_tier_text": None,
        "grade_goal_text": None,
        "admission_pref": None,
        "evidence": [],
        "source": "rule",
    }

    def ev(slot, idx, field, quote):
        sig["evidence"].append({"slot": slot, "idx": idx, "field": field,
                                 "quote": (quote or "")[:50]})

    # 강점 과목
    for a in slots.get("strong_subject", []) + slots.get("efficient_subject", []):
        for s in _subject_in(a["choice_text"]):
            if s not in sig["strong_subjects"]:
                sig["strong_subjects"].append(s)
                ev("strong_subject", a["idx"], "strong_subjects", a["choice_text"])

    # 약점 과목
    for a in slots.get("weak_subject", []):
        for s in _subject_in(a["choice_text"]):
            if s not in sig["weak_subjects"]:
                sig["weak_subjects"].append(s)
                ev("weak_subject", a["idx"], "weak_subjects", a["choice_text"])

    # 문이과 성향(명시 단서만)
    for a in slots.get("track_orientation", []):
        t = a["choice_text"]
        if any(k in t for k in ["이과", "이공", "자연계", "수학", "과학"]) and not _is_negative(t):
            sig["track_hint"] = "sci"
            ev("track_orientation", a["idx"], "track_hint", t)
        elif any(k in t for k in ["문과", "인문", "사회계", "언어"]) and not _is_negative(t):
            sig["track_hint"] = "hum"
            ev("track_orientation", a["idx"], "track_hint", t)

    # 과학/사회 탐구 선호 → 보조 track 단서
    for a in slots.get("science_subject_pref", []):
        if _is_negative(a["choice_text"]):
            if sig["track_hint"] is None:
                sig["track_hint"] = "hum"
                ev("science_subject_pref", a["idx"], "track_hint", a["choice_text"])
    for a in slots.get("social_subject_pref", []):
        if not _is_negative(a["choice_text"]) and sig["track_hint"] is None:
            sig["track_hint"] = "hum"
            ev("social_subject_pref", a["idx"], "track_hint", a["choice_text"])

    # 진로 계열 단서(원문 보존 → LLM/매핑이 정규화)
    for key in ["sci_track_interest", "hum_track_interest", "desired_field"]:
        for a in slots.get(key, []):
            if not _is_negative(a["choice_text"]):
                sig["career_cluster_hints"].append(a["choice_text"])
                ev(key, a["idx"], "career_cluster_hints", a["choice_text"])
                # 명시 키워드는 규칙으로 클러스터 확정(LLM 없이도 동작)
                for cl in _clusters_from_text(a["choice_text"]):
                    if cl not in sig["career_clusters"]:
                        sig["career_clusters"].append(cl)
                        ev(key, a["idx"], "career_clusters", a["choice_text"])
    # 진로 선택 이유/기준 슬롯도 클러스터 단서로 스캔
    for a in slots.get("career_motive", []):
        for cl in _clusters_from_text(a["choice_text"]):
            if cl not in sig["career_clusters"]:
                sig["career_clusters"].append(cl)
                ev("career_motive", a["idx"], "career_clusters", a["choice_text"])

    # 목표 대학 티어
    for a in slots.get("target_univ_tier", []):
        sig["target_tier_text"] = a["choice_text"]
        ev("target_univ_tier", a["idx"], "target_tier_text", a["choice_text"])
        break

    # 내신 목표 등급
    for a in slots.get("grade_goal", []):
        sig["grade_goal_text"] = a["choice_text"]
        ev("grade_goal", a["idx"], "grade_goal_text", a["choice_text"])
        break

    # 수시/정시 선호
    for a in slots.get("admission_pref", []):
        t = a["choice_text"]
        if "정시" in a["sub_category"] and _is_negative(t):
            sig["admission_pref"] = "수시 선호(정시 비선호)"
        elif "수시" in a["sub_category"] and _is_negative(t):
            sig["admission_pref"] = "정시 선호(수시 비선호)"
        if sig["admission_pref"]:
            ev("admission_pref", a["idx"], "admission_pref", t)
            break

    return sig
