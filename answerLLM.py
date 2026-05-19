"""
answerLLM.py
─────────────────────────────────────────────────────────────────────
Layer 1 (LLM 구조화기). 규칙이 약한 영역(나열형 답변, 복합 선택지,
융합 진로)만 보강한다. 분류·점수 산정은 하지 않는다.

안전장치
- temperature=0, response_mime_type=json (재현성)
- 출력은 고정 enum 으로 제한. enum 이탈 항목은 코드에서 폐기.
- evidence 없는 항목 불채택.
- API 키 없음/실패 시 None 반환 → 규칙 단독으로 동작(graceful).
- persona/reason 은 프롬프트에 절대 포함하지 않는다.
"""
from __future__ import annotations
import json
from typing import Dict, List, Optional

try:
    from google import genai
except ImportError:
    genai = None

from constants import GEMINI_MODEL
from password import get_secret_value

CLUSTER_ENUM = [
    "인문·언어", "사회·정치", "경영·경제", "미디어·콘텐츠",
    "수리·통계", "컴퓨터·AI", "공학", "생명·바이오", "의약학",
    "교육", "예술·디자인", "융합",
]
SUBJECT_ENUM = [
    "국어", "영어", "수학", "물리", "화학", "생명과학", "지구과학",
    "사회문화", "정치와법", "경제", "윤리", "한국사", "세계사", "지리",
]

_PROMPT = """너는 학생 진단 답변에서 사실만 추출하는 파서다.
추론·창작·점수 산정을 하지 마라. 답변에 명시된 내용만 사용하라.
입력은 (문항번호, 질문, 선택지텍스트) 목록이다.

아래 JSON 만 출력하라. 마크다운·설명 금지.
{{
 "strong_subjects": [SUBJECT_ENUM 부분집합],
 "weak_subjects": [SUBJECT_ENUM 부분집합],
 "subject_preference_order": [선호 순서가 명시된 경우만, 순서대로],
 "career_clusters": [CLUSTER_ENUM 부분집합, 최대 3개],
 "is_fusion": true/false,
 "evidence": [{{"idx": 정수, "field": "위 키 중 하나", "quote": "근거 일부"}}]
}}
SUBJECT_ENUM = {subjects}
CLUSTER_ENUM = {clusters}
규칙: 답변에 없으면 빈 배열. 추측 절대 금지.
evidence 없는 항목은 출력하지 마라.
career_clusters 는 진로/전공/직업/목표 관련 문항에서만 도출하라.
단일 계열로 환원 불가하면 is_fusion=true.
"""


def _validate(raw: Dict) -> Optional[Dict]:
    if not isinstance(raw, dict):
        return None
    ev = raw.get("evidence", [])
    if not isinstance(ev, list):
        ev = []
    ev_fields = {e.get("field") for e in ev if isinstance(e, dict)}
    out = {
        "strong_subjects": [], "weak_subjects": [],
        "subject_preference_order": [], "career_clusters": [],
        "is_fusion": bool(raw.get("is_fusion", False)),
        "evidence": [e for e in ev if isinstance(e, dict) and "idx" in e][:40],
        "source": "llm",
    }
    for k, enum in [("strong_subjects", SUBJECT_ENUM),
                    ("weak_subjects", SUBJECT_ENUM),
                    ("subject_preference_order", SUBJECT_ENUM),
                    ("career_clusters", CLUSTER_ENUM)]:
        vals = raw.get(k, [])
        if not isinstance(vals, list):
            continue
        # 순서 슬롯 외에는 evidence 에 해당 field 가 있어야 채택
        if k == "subject_preference_order" or k in ev_fields:
            out[k] = [v for v in vals if v in enum][:6]
    return out


def structure_with_llm(normalized: Dict) -> Optional[Dict]:
    """규칙이 약한 슬롯의 답변만 추려 LLM 에 전달."""
    if genai is None:
        return None
    api_key = get_secret_value("GEMINI_API_KEY")
    if not api_key:
        return None

    # 나열형/복합/진로 슬롯만 선별 → 토큰 절약 + 노이즈 차단
    target_slots = [
        "subject_pref_order", "sci_track_interest", "hum_track_interest",
        "desired_field", "career_motive", "social_subject_pref",
        "science_subject_pref", "strong_subject", "weak_subject",
    ]
    rows: List[str] = []
    for s in target_slots:
        for a in normalized.get("slots", {}).get(s, []):
            rows.append(f"[{a['idx']}] Q:{a['question']} / A:{a['choice_text']}")
    if not rows:
        return None

    prompt = _PROMPT.format(subjects=SUBJECT_ENUM, clusters=CLUSTER_ENUM) \
        + "\n\n=== 학생 답변 ===\n" + "\n".join(rows[:60])

    try:
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={"response_mime_type": "application/json", "temperature": 0},
        )
        return _validate(json.loads(resp.text))
    except Exception:
        return None
