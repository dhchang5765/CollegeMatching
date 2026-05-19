"""
answer_pipeline.py
─────────────────────────────────────────────────────────────────────
3층 파이프라인 오케스트레이터.

Layer 1: 규칙 추출(extractAnswers) + LLM 구조화(answerLLM, 선택)
Layer 2: 결정론 판정(decisionEngine)  ← 최종 판정자
Layer 3: 검증 루프 기록 + ML 교차검증(자문)

app.py 는 run_answer_pipeline() 하나만 호출하면 된다.
"""
from __future__ import annotations
from typing import Dict, Optional

from answer_schema import normalize_responses, build_feature_vector
from extractAnswers import extract_rule_signals
from answerLLM import structure_with_llm
from decisionEngine import decide
from mlJudge import cross_check, ml_status
from validationLoop import record_prediction


def synthesize_signals_from_answers(answer_result: Dict) -> Dict:
    """
    HTML 없이 답변 JSON만 들어왔을 때, 기존 recommend_universities /
    choose_target_departments 가 기대하는 signals 객체를 합성한다.
    """
    rs = answer_result.get("rule_signals", {})
    dec = answer_result.get("decision", {})

    text_parts = []
    text_parts += rs.get("career_cluster_hints", [])
    text_parts += rs.get("career_clusters", [])
    text_parts += [f"{s} 강점" for s in rs.get("strong_subjects", [])]
    if rs.get("target_tier_text"):
        text_parts.append(rs["target_tier_text"])
    text_parts += dec.get("top_categories", [])

    # 판정 Top 카테고리를 학과 시드 단어로 증폭 (raw_text 매칭 강화)
    CAT_SEED_WORDS = {
        "미디어·광고·콘텐츠": ["미디어", "콘텐츠", "광고", "언론", "방송"],
        "국어국문·언어": ["국어국문", "문예창작", "글쓰기", "문학"],
        "사회과학": ["사회", "정치외교", "행정", "법학"],
        "경영·경제": ["경영", "경제", "회계"],
        "인공지능·데이터사이언스": ["인공지능", "데이터사이언스", "AI"],
        "컴퓨터·소프트웨어": ["컴퓨터", "소프트웨어", "프로그래밍"],
        "수학·통계": ["수학", "통계"],
        "의학": ["의대", "의예과", "의학", "의료"],
        "약학": ["약학", "제약"],
        "생명과학·바이오": ["생명과학", "바이오", "유전"],
        "교육": ["교육", "교직"],
        "디자인·예술": ["디자인", "예술", "미술"],
    }
    for c in dec.get("top_categories", [])[:2]:
        # 상위 2개 카테고리는 시드 단어를 3회 반복해 매칭 가중↑
        text_parts += CAT_SEED_WORDS.get(c, []) * 3
    raw_text = " ".join(p for p in text_parts if p)

    grade = None
    import re as _re
    g_src = (rs.get("grade_goal_text") or "") + " " + (rs.get("target_tier_text") or "")
    m = _re.search(r"([1-9](?:\.\d)?)\s*등급", g_src)
    if m:
        try:
            grade = float(m.group(1))
        except Exception:
            grade = None

    weak = set(rs.get("weak_subjects", []))
    strong = set(rs.get("strong_subjects", []))

    return {
        "raw_text": raw_text,
        "overall_grade": grade,
        "subjects": {},
        "top_keywords": dec.get("top_categories", []),
        "topkeywords": dec.get("top_categories", []),
        "detected_tracks": [],
        "detected_track_strengths": {},
        "preferred_track": None,
        "target_university": None,
        "is_student_record_heavy": False,
        "admission_preference": rs.get("admission_pref"),
        "essay_strength": "국어" in strong,
        "math_risk": "수학" in weak,
        "humanities_media_fit": any(
            c in dec.get("top_categories", [])
            for c in ["미디어·광고·콘텐츠", "국어국문·언어"]
        ),
        "science_risk": any(s in weak for s in ["과학", "물리", "화학", "생명과학"]),
        "english_strength": "영어" in strong,
        "admission_orientation": rs.get("admission_pref") or "미탐지",
        "sci_track_fit": rs.get("track_hint") == "sci",
        "humanities_track_fit": rs.get("track_hint") == "hum",
        "med_track_fit": "의약학" in rs.get("career_clusters", []),
        "extracurricular_strong": False,
        "self_directed": False,
        "lines_samples": [],
        "report_meta": {},
        "diagnosis_sections": [],
        "simulation": {},
        "final_conclusion": {},
        "_source": "answers_json_only",
    }


def run_answer_pipeline(answers_json_text: str,
                        base_category_scores: Optional[Dict] = None,
                        use_llm: bool = True,
                        log_prediction: bool = False) -> Dict:
    # Layer 0: 정규화 (버전 인식, idx 비의존)
    norm = normalize_responses(answers_json_text)
    feature_vector = build_feature_vector(norm)

    # Layer 1: 규칙(필수) + LLM(선택, 실패 시 None)
    rule_sig = extract_rule_signals(norm)
    llm_sig = structure_with_llm(norm) if use_llm else None

    # Layer 2: 최종 판정 (순수 결정론)
    decision = decide(rule_sig, llm_sig, base_category_scores)

    # Layer 3: ML 교차검증(자문 only) + 예측 로깅
    student_key = f"{norm['version']}::{hash(answers_json_text) & 0xffffffff}"
    ml = cross_check(feature_vector, decision["top_categories"])
    if log_prediction:
        try:
            record_prediction(student_key, decision, feature_vector)
        except Exception:
            pass

    return {
        "version": norm["version"],
        "n_questions": norm["n_questions"],
        "persona_display_only": norm.get("persona_display_only"),
        "rule_signals": rule_sig,
        "llm_used": llm_sig is not None,
        "decision": decision,                 # 최종 판정 결과
        "ml_crosscheck": ml,                  # 자문(비판정)
        "ml_status": ml_status(),
        "feature_vector": feature_vector,
    }
