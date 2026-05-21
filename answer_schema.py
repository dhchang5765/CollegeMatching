"""
answer_schema.py
─────────────────────────────────────────────────────────────────────
질문지가 버전별로 다르다는 사실(200문항 / 162문항 셋, idx 정렬 불가)을
전제로, 답변을 '시맨틱 슬롯' 단위로 정규화한다.

핵심 원칙
- 절대 idx(위치)로 키잉하지 않는다. sub_category 의 부분 문자열 패턴으로 매칭.
- persona / persona_summary / reason 은 임의 작성이므로 절대 사용하지 않는다.
- 한 슬롯에 여러 sub_category 가 매핑될 수 있다(버전 간 명칭 차이 흡수).
"""
from __future__ import annotations
import json
import hashlib
from typing import Dict, List, Optional, Tuple

# ── 시맨틱 슬롯 정의 ──────────────────────────────────────────────
# slot_id : (설명, [sub_category 패턴], [question 텍스트 패턴])
# question 패턴은 답변지 버전이 달라도(섹션 묶음형 vs 문항별형) 매칭되도록 보조.
SEMANTIC_SLOTS: Dict[str, Tuple[str, List[str], List[str]]] = {
    "strong_subject":   ("강점/무기/효자/타고난 과목",
                          ["무기 과목", "효자 과목", "타고난 과목", "강점 과목"],
                          ["무기 과목", "효자 과목", "타고난 과목", "날로 먹는", "잘 나오는 과목"]),
    "weak_subject":     ("약점/방어/새는/취약/막막 과목",
                          ["방어 과목", "새는 과목", "취약 과목", "막막한 과목", "약점 과목"],
                          ["방어 과목", "새는 과목", "취약 과목", "막막한 과목",
                           "공부하기 진짜 싫은데", "성적이 안 오르는"]),
    "efficient_subject":("가성비 과목",
                          ["가성비 과목"],
                          ["시간 대비", "효율이 제일", "가성비"]),
    "subject_pref_order":("과목 선호 순서",
                          ["과목 선호 순서", "과목 호감도", "과목별 선호"],
                          ["좋아하거나 자신 있는 과목 순서", "과목 순서"]),
    "sci_track_interest":("이과 진로 관심",
                          ["이과 진로", "이과 분야", "이과 직업", "이과 계열"],
                          ["이과 진로", "이공계 진로", "이과 분야"]),
    "hum_track_interest":("문과 진로 관심",
                          ["문과 진로", "문과 분야", "문과 직업", "문과 계열"],
                          ["문과 진로", "인문계 진로", "문과 분야"]),
    "science_subject_pref":("과학탐구 선호",
                          ["과학탐구 선호", "과학 선호 파트", "실험vs이론", "실험·이론"],
                          ["과학탐구 중에서", "과학 중 어떤"]),
    "social_subject_pref":("사회탐구 선호",
                          ["사회탐구 선호", "사회 선호 파트"],
                          ["사회탐구 중에서", "사회 중 어떤"]),
    "track_orientation":("문이과 성향",
                          ["문이과 성향", "문과·이과 성향", "문이과 통합",
                           "성적 기준 계열", "강점 과목 계열"],
                          ["문과 vs 이과", "문이과 성향"]),
    "desired_field":    ("희망 계열",
                          ["희망 계열", "진로 계열"],
                          ["희망 전공", "지원하고 싶은 계열"]),
    "career_decided":   ("진로 결정 여부",
                          ["진로 결정 여부", "진로 변경"],
                          ["진로 정해", "장래 희망 정해", "진로 결정"]),
    "career_motive":    ("진로 선택 이유/기준",
                          ["진로 선택 이유", "진로 선택 기준", "진로 영향"],
                          ["진로 결정에 가장", "진로 선택"]),
    "target_univ_tier": ("목표 대학 수준",
                          ["목표 대학"],
                          ["목표 대학", "지원하고 싶은 대학", "어느 대학"]),
    "grade_goal":       ("내신 목표 등급",
                          ["내신 목표 등급", "주요 3과목 등급", "탐구 등급"],
                          ["목표 등급", "내신 목표"]),
    "major_job_align":  ("전공-직업 일치 인식",
                          ["전공-직업 일치", "잘하는 과목·전공 일치"],
                          ["전공과 직업", "전공-직업"]),
    "admission_pref":   ("수시/정시 선호",
                          ["수시 비선호", "정시 비선호", "수시", "정시"],
                          ["수시·정시", "수시 vs 정시", "수시랑 정시"]),
}

# 슬롯이 어떤 신호 종류인지(판정 엔진이 사용)
SLOT_KIND = {
    "strong_subject": "subject_strength",
    "weak_subject": "subject_weakness",
    "efficient_subject": "subject_strength",
    "subject_pref_order": "subject_order",
    "sci_track_interest": "career_cluster_hint",
    "hum_track_interest": "career_cluster_hint",
    "science_subject_pref": "track_hint",
    "social_subject_pref": "track_hint",
    "track_orientation": "track_hint",
    "desired_field": "career_cluster_hint",
    "career_decided": "meta",
    "career_motive": "meta",
    "target_univ_tier": "target_tier",
    "grade_goal": "grade_goal",
    "major_job_align": "meta",
    "admission_pref": "admission_pref",
}


def detect_questionnaire_version(responses: List[Dict]) -> str:
    """질문 텍스트 집합의 해시로 버전 식별(idx 길이가 아니라 내용 기반)."""
    qs = "|".join(sorted(r.get("question", "") for r in responses))
    h = hashlib.sha1(qs.encode("utf-8")).hexdigest()[:10]
    n = len(responses)
    return f"v{n}-{h}"


def _match_slot(sub_category: str, question: str = "") -> Optional[str]:
    """
    sub_category 우선 매칭 → 매칭 실패 시 question 텍스트로 fallback.
    이혜진 답변지처럼 sub_category 가 섹션 단위로 묶여 변별력 없을 때
    question 텍스트의 시그니처 어구로 슬롯을 식별한다.
    """
    sc = sub_category or ""
    q = question or ""
    for slot_id, item in SEMANTIC_SLOTS.items():
        # (설명, sub_patterns, q_patterns)
        sub_patterns = item[1] if len(item) > 1 else []
        q_patterns = item[2] if len(item) > 2 else []
        if any(p in sc for p in sub_patterns):
            return slot_id
        if q_patterns and any(p in q for p in q_patterns):
            return slot_id
    return None


def normalize_responses(raw_json: str) -> Dict:
    """
    원본 답변 JSON → 슬롯 정규화 구조.
    question 과 choice_text 만 사용. persona/reason 무시.
    """
    data = json.loads(raw_json)
    responses = data.get("responses", [])
    version = detect_questionnaire_version(responses)

    slots: Dict[str, List[Dict]] = {}
    for r in responses:
        slot_id = _match_slot(r.get("sub_category", ""), r.get("question", ""))
        if not slot_id:
            continue
        slots.setdefault(slot_id, []).append({
            "idx": r.get("idx"),
            "sub_category": r.get("sub_category"),
            "question": r.get("question", ""),
            "choice_text": r.get("choice_text", ""),
            "choice_idx": r.get("choice_idx"),
        })

    return {
        "version": version,
        "n_questions": len(responses),
        "slots": slots,                       # slot_id -> [답변들]
        "persona_display_only": data.get("persona"),  # 표시 전용. 점수 미사용.
    }


def build_feature_vector(normalized: Dict) -> Dict[str, str]:
    """
    ML 준비용 고정 스키마 피처. key = slot_id, value = 대표 choice_text.
    버전이 달라도 동일 slot_id 로 정렬되므로 학습 가능 형태로 누적 가능.
    """
    fv: Dict[str, str] = {s: "" for s in SEMANTIC_SLOTS}
    for slot_id, answers in normalized.get("slots", {}).items():
        if answers:
            # 같은 슬롯에 여러 답이면 첫 응답을 대표값으로(idx 최소)
            primary = sorted(answers, key=lambda a: (a.get("idx") or 1e9))[0]
            fv[slot_id] = primary.get("choice_text", "")
    return fv
