"""
student_profile.py
─────────────────────────────────────────────────────────────────────
학생 프로파일 4슬롯 합성 — '핵심 키워드'를 대체하는 정직한 진단 카드.

설계 원칙
- 결정론적: 동일 입력 → 동일 출력. LLM 자유 생성 금지.
- 진로 미정 학생도 의미 있는 슬롯 채움 (옵션 ③ 분기 처리).
- 답변 JSON 1차 신호 우선, HTML 보조 신호 후순위.

4슬롯
- 강점(strengths): 학생의 명확한 자산
- 약점(weaknesses): 보완 필요한 영역
- 관심(interests): 진로·학과·직업 자기 진술
- 위험(risks): 입시 관점에서 알람이 필요한 신호
"""
from __future__ import annotations
import re
import json
from typing import Dict, List, Optional


# ── 답변 텍스트에서 검출할 직업·관심 키워드 ─────────────
INTEREST_OCCUPATIONS = [
    "변리사", "의사", "약사", "치과의사", "한의사", "수의사",
    "교사", "교수", "연구원", "공무원",
    "변호사", "검사", "판사", "회계사", "세무사",
    "기자", "PD", "프로듀서", "아나운서", "방송작가",
    "디자이너", "건축가", "엔지니어", "프로그래머", "개발자",
    "데이터사이언티스트", "AI 엔지니어",
    "간호사", "물리치료사", "임상병리사",
    "경영자", "창업", "사업가",
    "외교관", "통역사", "번역가",
    "예술가", "작가", "소설가", "시인",
]

# ── 위험 신호 검출 패턴 ────────────────────────────
RISK_PATTERNS = {
    "사교육 의존": [
        r"학원\s*(?:없으면|끊으면)\s*(?:불안|걱정)",
        r"학원[에은이가가]\s*의존",
        r"사교육\s*없으면",
        r"인강\s*없으면",
    ],
    "벼락치기": [
        r"벼락치기",
        r"미루[다어어서지는]",
        r"시험\s*직전",
        r"마감\s*임박",
    ],
    "학습 위기": [
        r"공부\s*(?:가|을)\s*안",
        r"성적이\s*안\s*올",
        r"막막",
        r"집중\s*안",
        r"포기",
    ],
    "진로 변동성": [
        r"진로[가는이을]?\s*(?:바뀌|변하|흔들|왔다 갔다)",
        r"진로\s*결정\s*못",
        r"갈팡질팡",
        r"확신\s*없",
    ],
    "비교과 부족": [
        r"비교과[가는이을]?\s*(?:없|부족|미흡|약)",
        r"동아리\s*활동\s*(?:없|안)",
        r"생기부[가는이을]?\s*(?:비|부실|부족)",
        r"수상\s*(?:없|안 한)",
    ],
    "자기주도성 부족": [
        r"스스로\s*(?:안|못|어렵)",
        r"누가\s*시켜야",
        r"부모님이\s*(?:시키|챙)",
        r"수동적",
    ],
}


def _scan_answers_text(answers_text: str) -> Dict:
    """답변 JSON 전체 텍스트에서 직업·위험 신호 정규식 스캔."""
    out = {"interest_jobs": [], "risk_flags": []}
    if not answers_text:
        return out
    try:
        data = json.loads(answers_text) if isinstance(answers_text, str) else answers_text
    except Exception:
        return out

    # 모든 choice_text 합치기
    all_text = ""
    for r in data.get("responses", []):
        all_text += " " + (r.get("choice_text") or "")

    # 직업 키워드 매칭
    found_jobs = []
    for job in INTEREST_OCCUPATIONS:
        if job in all_text:
            found_jobs.append(job)
    out["interest_jobs"] = found_jobs[:5]  # 최대 5개

    # 위험 신호 매칭
    risk_flags = []
    for label, patterns in RISK_PATTERNS.items():
        for p in patterns:
            if re.search(p, all_text):
                risk_flags.append(label)
                break
    out["risk_flags"] = risk_flags

    return out


def build_student_profile(signals: Dict,
                           answer_result: Optional[Dict] = None,
                           answers_text: Optional[str] = None) -> Dict:
    """
    학생 신호로부터 4슬롯 프로파일 합성.
    반환: { strengths, weaknesses, interests, risks, mode }
      mode: 'clear' (진로 명확) | 'exploring' (진로 탐색 중)
    """
    rs = (answer_result or {}).get("rule_signals", {}) or {}
    answer_scan = _scan_answers_text(answers_text) if answers_text else {"interest_jobs": [], "risk_flags": []}

    strong_subjects = rs.get("strong_subjects") or []
    weak_subjects = rs.get("weak_subjects") or []
    career_clusters = rs.get("career_clusters") or []
    target_tier = rs.get("target_tier_text") or ""

    # 답변 클러스터로부터 결정 — 모순 해소용 마스터 플래그
    has_med = "의약학" in career_clusters
    has_sci = any(c in career_clusters for c in
                  ["컴퓨터·AI", "공학", "수리·통계", "자연과학"])
    has_hum = any(c in career_clusters for c in
                  ["인문·언어", "미디어·콘텐츠", "사회·정치"])
    # 위험 신호 사전 파악 (강점에서 충돌하는 신호 제외용)
    risk_flags_set = set(answer_scan["risk_flags"])
    has_self_directed_risk = "자기주도성 부족" in risk_flags_set
    has_extracur_risk = "비교과 부족" in risk_flags_set

    # ─── 강점 ──────────────────────────────────────────
    # 원칙: 답변 1차 신호 우선. HTML 추론 신호는 답변과 모순되지 않을 때만 통과.
    strengths = []
    strong_set = set(strong_subjects)

    # 답변에서 추출된 강점 과목 (1차 신호 — 가장 신뢰)
    for s in strong_subjects:
        strengths.append(f"{s} 강점")

    # 논술/글쓰기: 답변에 국어가 strong subject 일 때만 인정
    if "국어" in strong_set and signals.get("essay_strength"):
        strengths.append("논술/글쓰기")

    # 자기주도성: 위험 신호 없을 때만
    if signals.get("self_directed") and not has_self_directed_risk:
        strengths.append("자기주도성")

    # 비교과 풍부: 위험 신호 없을 때만 + HTML이 명시적으로 True 일 때
    if signals.get("extracurricular_strong") is True and not has_extracur_risk:
        strengths.append("비교과 풍부")

    # 계열 적합: 답변 메인 클러스터(첫 항목)와 일치하는 신호만 통과
    main_cluster = career_clusters[0] if career_clusters else None
    main_is_med = main_cluster == "의약학"
    main_is_sci = main_cluster in ("컴퓨터·AI", "공학", "수리·통계", "자연과학")
    main_is_hum = main_cluster in ("인문·언어", "미디어·콘텐츠", "사회·정치")

    if signals.get("med_track_fit") and main_is_med:
        strengths.append("의약학 적합")
    elif signals.get("sci_track_fit") and main_is_sci:
        strengths.append("이공 분석")
    elif signals.get("humanities_media_fit") and main_is_hum:
        strengths.append("인문·미디어 적합")

    # ─── 약점 ──────────────────────────────────────────
    weaknesses = []
    for w in weak_subjects:
        weaknesses.append(f"{w} 약점")
    if signals.get("math_risk") and "수학 약점" not in weaknesses:
        weaknesses.append("수학 위험")
    if signals.get("science_risk") and "과학 약점" not in weaknesses:
        weaknesses.append("과학 위험")
    if signals.get("extracurricular_strong") is False or has_extracur_risk:
        weaknesses.append("비교과 부족")
    if signals.get("self_directed") is False or has_self_directed_risk:
        weaknesses.append("자기주도성 부족")

    # ─── 관심 ──────────────────────────────────────────
    interests = []
    cluster_label = {
        "의약학": "의약학",
        "컴퓨터·AI": "컴퓨터·AI",
        "공학": "공학",
        "수리·통계": "수학·통계",
        "인문·언어": "인문·언어",
        "미디어·콘텐츠": "미디어·콘텐츠",
        "사회·정치": "사회과학",
        "교육": "교육",
        "예술·체육": "예술·체육",
        "경영·경제": "경영·경제",
    }
    for c in career_clusters:
        interests.append(cluster_label.get(c, c))
    # 답변에서 검출된 구체적 직업
    for job in answer_scan["interest_jobs"][:3]:
        interests.append(job)
    # 목표 대학 (긴 자기 진술이면 단축)
    target_univ = signals.get("target_university")
    if target_univ:
        interests.append(f"목표: {target_univ}")
    elif target_tier:
        # 자기 진술 첫 단어/구절만 (전체 문장 X)
        short = target_tier.strip()
        # 첫 어절 단위로 자르되 최대 12자
        if len(short) > 12:
            short = short[:12] + "…"
        interests.append(f"목표: {short}")
    # 선호 트랙
    tracks = signals.get("detected_tracks") or []
    for t in tracks[:2]:
        if t not in interests:
            interests.append(t)

    # ─── 위험 ──────────────────────────────────────────
    risks = list(answer_scan["risk_flags"])

    # 결정론적 위험 추가
    if not career_clusters and not interests:
        risks.append("진로 미정")
    elif not career_clusters:
        # 직업 관심은 있지만 클러스터 합의 안 됨 (분산된 관심)
        risks.append("진로 탐색 중")

    if signals.get("admission_orientation") == "수시 중심" and \
       not signals.get("extracurricular_strong"):
        if "비교과 부족" not in risks:
            risks.append("학종 약점")

    overall_grade = signals.get("overall_grade")
    if overall_grade is not None and overall_grade >= 3.5:
        risks.append("등급 약점")

    # ─── 모드 판정 ────────────────────────────────────
    if career_clusters and len(career_clusters) >= 1:
        mode = "clear"
    else:
        mode = "exploring"

    # 중복 제거 + 길이 제한
    def dedupe(lst, n=6):
        seen = set(); out = []
        for x in lst:
            if x and x not in seen:
                seen.add(x); out.append(x)
            if len(out) >= n: break
        return out

    return {
        "strengths": dedupe(strengths, 6),
        "weaknesses": dedupe(weaknesses, 5),
        "interests": dedupe(interests, 6),
        "risks": dedupe(risks, 5),
        "mode": mode,
    }
