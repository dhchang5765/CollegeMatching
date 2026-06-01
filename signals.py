"""
signals.py
─────────────────────────────────────────────────────────────────────
app.py 에서 분리 — HTML 보고서에서 학생 신호를 추출하고, 계열 점수와
추천 학과 후보를 산출하는 결정론적 로직.

분리 이유: app.py(1,778행)가 너무 커 추천 로직(recommender)·리포트
빌더(report_builder)·UI(main)와 한 파일에 뒤섞여 유지보수가 어려웠음.
함수 본문은 원본과 동일(동작 보존). 임포트 경계만 명시화함.
"""
from __future__ import annotations
import re
from collections import defaultdict
from typing import Dict, List, Optional

from constants import *
from extractHTML import parse_report_html
from utils import extract_keywords_kiwi, strip_text


def pick_first_float(text: str, patterns: List[str]) -> Optional[float]:
    for p in patterns:
        m = re.search(p, text)
        if m:
            try:
                return float(m.group(1))
            except Exception:
                pass
    return None

def collect_all_floats(text: str, patterns: List[str]) -> List[float]:
    vals = []
    for p in patterns:
        for m in re.findall(p, text):
            try:
                vals.append(float(m[0] if isinstance(m, tuple) else m))
            except Exception:
                pass
    return vals

def infer_subjects_from_text(text: str) -> Dict[str, Optional[float]]:
    subject_scores = {}
    subject_patterns = {
        '국어': [r'국어[^0-9]{0,20}([1-9](?:\.\d)?)등급', r'국어[^0-9]{0,20}([0-9]{1,3}(?:\.\d+)?)점'],
        '수학': [r'수학[^0-9]{0,20}([1-9](?:\.\d)?)등급', r'수학[^0-9]{0,20}([0-9]{1,3}(?:\.\d+)?)점'],
        '영어': [r'영어[^0-9]{0,20}([1-9](?:\.\d)?)등급', r'영어[^0-9]{0,20}([0-9]{1,3}(?:\.\d+)?)점'],
        '사회': [r'사회[^0-9]{0,20}([1-9](?:\.\d)?)등급', r'사회문화[^0-9]{0,20}([1-9](?:\.\d)?)등급'],
        '과학': [r'과학[^0-9]{0,20}([1-9](?:\.\d)?)등급', r'생명과학[^0-9]{0,20}([1-9](?:\.\d)?)등급']
    }
    for subj, patterns in subject_patterns.items():
        subject_scores[subj] = pick_first_float(text, patterns)
    return subject_scores

def detect_target_university(text: str) -> Optional[str]:
    lower_text = text.lower()

    # 1) IST 계열 별칭 우선 탐지
    for canonical, aliases in IST_UNIVERSITY_ALIASES.items():
        if any(alias.lower() in lower_text for alias in aliases):
            return canonical

    # 2) 일반 대학명 패턴 탐지
    patterns = [
        r"([가-힣A-Za-z0-9]{2,20}대학교)",
        r"([가-힣A-Za-z0-9]{2,20}대학)"
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            return strip_text(m.group(1))

    return None

def extract_example_specific_signals(html_text: str) -> Dict:
    # 1) 구조 파싱
    report = parse_report_html(html_text)

    raw_text = report.get("raw_text", "")
    meta = report.get("meta", {})
    diag_sections = report.get("diagnosis_sections", [])
    final_conclusion = report.get("final_conclusion", {})
    simulation = report.get("simulation", {})

    # 2) 분석 대상 텍스트: 진단 섹션 + 결론 위주로 합치기
    focused_chunks = []
    for d in diag_sections:
        focused_chunks.append(d.get("prose_text", ""))
        focused_chunks.extend(d.get("direct_quotes", []))
    for c in final_conclusion.get("cards", []):
        focused_chunks.append(c.get("body", ""))
    focused_text = " ".join(ch for ch in focused_chunks if ch)

    # 3) 상위 키워드는 focused_text 기반 - Kiwi 형태소 분석 사용
    text_for_keywords = focused_text if focused_text.strip() else raw_text
    lines = [ln.strip() for ln in re.split(r"[.!?]", text_for_keywords) if ln.strip()]

    # 학생 본인 이름은 키워드에서 동적으로 제외 (조사 결합형 포함)
    student_name = meta.get("student_name") if isinstance(meta, dict) else None
    extra_stop = set()
    if student_name:
        extra_stop.add(student_name)
        # 이혜진의·이혜진은·이혜진이 같은 조사 결합형도 함께 제외
        for particle in ["은", "는", "이", "가", "을", "를", "의", "에", "도", "만"]:
            extra_stop.add(student_name + particle)
        for particle in ["에서", "에게", "으로", "처럼", "까지"]:
            extra_stop.add(student_name + particle)
    top_keywords_all = extract_keywords_kiwi(text_for_keywords, top_n=60)
    top_keywords = [k for k in top_keywords_all if k not in extra_stop][:25]

    # 4) 전체 텍스트에서 등급 후보 수집 (raw_text 전체 사용 — 시뮬레이션/카드 영역의 등급도 포함)
    grade_candidates = collect_all_floats(raw_text, SPECIAL_PATTERNS["grade"])
    reasonable = [g for g in grade_candidates if 1 <= g <= 9]
    overall_grade_num = None
    if 3.5 in reasonable:
        overall_grade_num = 3.5
    elif reasonable:
        overall_grade_num = reasonable[0]

    # 5) 과목별 점수 추정
    subjects = infer_subjects_from_text(text_for_keywords)

    # 6) 목표 대학/트랙 추론
    detected_tracks_raw: list[tuple[str, int]] = []
    lower_text = text_for_keywords.lower()
    for track, keywords in TRACK_DETECTION_RULES.items():
        # 트랙별 키워드 매칭 횟수 합계로 강도 측정
        hit_strength = sum(lower_text.count(kw.lower()) for kw in keywords)
        if hit_strength > 0:
            detected_tracks_raw.append((track, hit_strength))

    # 매칭 강도 내림차순으로 정렬 → 단순한 dict 순서가 아닌 실제 신호 강도 기반
    detected_tracks_raw.sort(key=lambda x: -x[1])
    detected_tracks: list[str] = [t for t, _ in detected_tracks_raw]
    detected_track_strengths: dict[str, int] = dict(detected_tracks_raw)
    
    target_university = detect_target_university(lower_text)

    is_student_record_heavy = any(
        k in raw_text for k in ["학교생활기록부", "세특", "내신", "성적", "세부능력", "특기사항", "학생부", "생활기록부"]
    )
    admission_preference = (
        "학종" if "학생부종합" in raw_text or "종합전형" in raw_text else
        "수시" if "수시" in raw_text else
        "정시" if "정시" in raw_text else
        "교과" if "교과전형" in raw_text or "내신 위주" in raw_text else
        None
    )
    essay_strength = (
        ("논리" in raw_text and "글쓰기" in raw_text) or
        ("에세이" in raw_text and "첨삭" in raw_text)
    )
    math_risk = any(k in raw_text for k in ["수학이 약점", "수학이 부족", "수학 4등급", "수학 5등급"])
    humanities_media_fit = any(
        k in raw_text for k in ["글쓰기", "콘텐츠", "미디어", "기획", "스토리텔링"]
    )

    # ── 확장 신호 ──
    science_risk = any(k in raw_text for k in [
        "과학이 약점", "과학이 부족", "과학 4등급", "과학 5등급", "이과 약점"
    ])
    english_strength = any(k in raw_text for k in [
        "영어 강점", "영어 1등급", "영어 우수", "영어 능통"
    ])
    # 수시 vs 정시 성향 추론
    susi_signal = sum(raw_text.count(k) for k in ["수시", "학종", "교과전형", "학생부종합", "내신 위주"])
    jeongsi_signal = sum(raw_text.count(k) for k in ["정시", "수능 위주", "수능 집중", "모평"])
    if susi_signal >= jeongsi_signal + 2:
        admission_orientation = "수시 중심"
    elif jeongsi_signal >= susi_signal + 2:
        admission_orientation = "정시 중심"
    elif susi_signal > 0 or jeongsi_signal > 0:
        admission_orientation = "수시/정시 병행"
    else:
        admission_orientation = "미탐지"

    # 이과/문과 적합도
    sci_track_fit = any(k in raw_text for k in [
        "이과", "이공계", "공학", "STEM", "자연계열", "이과형"
    ])
    humanities_track_fit = any(k in raw_text for k in [
        "문과", "인문계열", "사회계열", "문과형"
    ])
    # 의약학 지향
    med_track_fit = any(k in raw_text for k in [
        "의대", "의예", "약대", "치대", "한의대", "수의대", "MMI", "의학"
    ])
    # 비교과 활동 충실도
    extracurricular_strong = any(k in raw_text for k in [
        "동아리 적극", "비교과 우수", "수상", "탐구보고서", "프로젝트", "발표"
    ])
    # 자기주도성
    self_directed = any(k in raw_text for k in [
        "자기주도", "자기 주도", "주체적", "스스로 학습", "자율 학습"
    ])

    return {
        "raw_text": raw_text,
        "overall_grade": overall_grade_num,
        "subjects": subjects,
        "top_keywords": top_keywords,
        "topkeywords": top_keywords,  # 호환성 유지
        "detected_tracks": detected_tracks,
        "detected_track_strengths": detected_track_strengths,
        "preferred_track": detected_tracks[0] if detected_tracks else None,
        "target_university": target_university,
        "is_student_record_heavy": is_student_record_heavy,
        "admission_preference": admission_preference,
        "essay_strength": essay_strength,
        "math_risk": math_risk,
        "humanities_media_fit": humanities_media_fit,
        "science_risk": science_risk,
        "english_strength": english_strength,
        "admission_orientation": admission_orientation,
        "sci_track_fit": sci_track_fit,
        "humanities_track_fit": humanities_track_fit,
        "med_track_fit": med_track_fit,
        "extracurricular_strong": extracurricular_strong,
        "self_directed": self_directed,
        "lines_samples": lines[:50],
        "report_meta": meta,
        "diagnosis_sections": diag_sections,
        "simulation": simulation,
        "final_conclusion": final_conclusion,
    }

def normalize_subject(v: Optional[float]) -> float:
    if v is None:
        return 50.0
    if v > 9:
        return max(0.0, min(100.0, v))
    # 1등급 ≈ 100, 2등급 ≈ 87.5, ... 식으로 역변환
    return max(0.0, 100 - (v - 1) * 12.5)


def infer_category_scores(signals: Dict) -> Dict[str, float]:
    text = signals["raw_text"]
    scores: Dict[str, float] = {k: 0.0 for k in CATEGORY_KEYWORDS}

    # 1) 카테고리 키워드 매칭
    for cat, kws in CATEGORY_KEYWORDS.items():
        for kw in kws:
            if kw in text:
                scores[cat] += 2.5

    subjects = signals.get("subjects", {})

    # 2) 과목 기반 가중치 (세분 카테고리 기준 배치)
    scores["수학·통계"] += normalize_subject(subjects.get("수학")) * 0.35
    scores["물리·화학·기초과학"] += normalize_subject(subjects.get("과학")) * 0.30
    scores["생명과학·바이오"] += normalize_subject(subjects.get("과학")) * 0.30
    scores["환경·지구과학"] += normalize_subject(subjects.get("과학")) * 0.20

    scores["컴퓨터·소프트웨어"] += normalize_subject(subjects.get("수학")) * 0.25
    scores["인공지능·데이터사이언스"] += normalize_subject(subjects.get("수학")) * 0.30
    scores["전기·전자·반도체"] += normalize_subject(subjects.get("수학")) * 0.25

    scores["의학"] += normalize_subject(subjects.get("과학")) * 0.30
    scores["치의학"] += normalize_subject(subjects.get("과학")) * 0.25
    scores["한의학"] += normalize_subject(subjects.get("과학")) * 0.25
    scores["약학"] += normalize_subject(subjects.get("과학")) * 0.30
    scores["간호"] += normalize_subject(subjects.get("과학")) * 0.20
    scores["보건·재활"] += normalize_subject(subjects.get("과학")) * 0.20
    scores["수의학"] += normalize_subject(subjects.get("과학")) * 0.25

    scores["국어국문·언어"] += normalize_subject(subjects.get("국어")) * 0.20
    scores["역사·철학·윤리"] += normalize_subject(subjects.get("사회")) * 0.15
    scores["사회과학"] += normalize_subject(subjects.get("사회")) * 0.25
    scores["경영·경제"] += normalize_subject(subjects.get("사회")) * 0.20
    scores["미디어·광고·콘텐츠"] += normalize_subject(subjects.get("사회")) * 0.15

    # 3) 인문/미디어 친화·수학 리스크 보정
    if signals.get("humanities_media_fit"):
        scores["국어국문·언어"] += 25
        scores["미디어·광고·콘텐츠"] += 35
    if signals.get("math_risk"):
        scores["수학·통계"] -= 20
        scores["인공지능·데이터사이언스"] -= 10

    # 4) 트랙 기반 가산점
    for track in signals.get("detected_tracks", []):
        for cat, bonus in TRACK_KEYWORD_MAP.get(track, {}).items():
            if cat in scores:
                scores[cat] += bonus

    return scores




def choose_target_departments(signals: Dict, category_scores: Dict[str, float], max_n: int = 3) -> List[str]:
    text = signals.get("raw_text", "") or ""
    detected_tracks = signals.get("detected_tracks", [])
    target_university = signals.get("target_university")
    final_conclusion = signals.get("final_conclusion", {}) or {}

    # 카테고리 1위 ─ 트랙 가중치 결정에 사용
    top_category = None
    top_cat_score = 0.0
    if category_scores:
        ranked_cats = sorted(category_scores.items(), key=lambda x: -x[1])
        top_category, top_cat_score = ranked_cats[0]

    # AI/데이터/SW 트랙은 명백한 STEM/공학 학생일 때만 강하게 반영
    # 카테고리 1위가 의약학/인문/미디어/교육 계열이면 약하게 처리
    NON_TECH_DOMINANT_CATS = {
        "의학", "치의학", "한의학", "약학", "간호", "보건·재활", "수의학",
        "미디어·광고·콘텐츠", "국어국문·언어", "역사·철학·윤리",
        "교육", "심리·상담", "사회과학", "예술·디자인",
    }
    is_non_tech_dominant = top_category in NON_TECH_DOMINANT_CATS

    dept_scores = defaultdict(float)

    def add_departments(departments: List[str], score: float):
        for d in departments:
            if d:
                dept_scores[d] += score

    # 1) 트랙 우선 (카테고리-인지형)
    # detected_tracks는 이미 강도 내림차순으로 정렬됨
    if detected_tracks and detected_tracks[0] in TRACK_TO_DEPARTMENTS:
        preferred_track = detected_tracks[0]
        track_weight = 8.0
        # AI/데이터/SW 트랙은 비-STEM 1위일 때 약화
        if preferred_track in {"AI", "데이터", "SW"} and is_non_tech_dominant:
            track_weight = 2.0
        add_departments(TRACK_TO_DEPARTMENTS[preferred_track], track_weight)

    # 2) 직접 시드 언급
    for seed, departments in DEPT_ALIAS.items():
        hit_count = text.count(seed)
        if hit_count <= 0:
            continue
        # 한글 여부로 base 점수 결정 (영어 약어는 오탐 위험으로 패널티)
        is_korean = bool(re.search(r"[가-힣]", seed))
        if is_korean:
            base = 6.0 if len(seed) >= 4 else 4.0
        else:
            base = 2.0  # AI, SW 같은 영어 약어는 base 낮춤
        add_departments(departments, base + min(hit_count - 1, 3) * 1.5)

    # 3) 최종 결론/시뮬레이션 단서 반영
    conclusion_text = " ".join(
        [c.get("title", "") + " " + c.get("body", "") for c in final_conclusion.get("cards", [])]
    )

    # 결론에 강한 비-STEM 신호가 있으면 AI 보정 약화
    strong_nontech_in_conclusion = any(k in conclusion_text for k in [
        "의대", "의예", "약학", "치의학", "한의학", "간호", "수의학",
        "미디어", "콘텐츠", "방송", "기획", "글쓰기",
        "교사", "교직", "심리", "상담",
    ])

    # AI 보정 (중복 제거, 한 번만 실행)
    if ("AI" in conclusion_text or "인공지능" in conclusion_text):
        ai_weight = 2.0 if strong_nontech_in_conclusion else 6.0
        add_departments(TRACK_TO_DEPARTMENTS.get("AI", []), ai_weight)

    if "데이터" in conclusion_text:
        data_weight = 1.5 if strong_nontech_in_conclusion else 5.5
        add_departments(TRACK_TO_DEPARTMENTS.get("데이터", []), data_weight)

    if "소프트웨어" in conclusion_text or "코딩" in conclusion_text:
        sw_weight = 1.5 if strong_nontech_in_conclusion else 5.0
        add_departments(TRACK_TO_DEPARTMENTS.get("SW", []), sw_weight)

    # IST 대학 목표 보정 (이공계 명시 목표일 때만)
    if target_university in {"KAIST", "DGIST", "GIST", "UNIST"} and not is_non_tech_dominant:
        add_departments([
            "인공지능학과", "데이터사이언스학과", "컴퓨터공학과",
            "전기전자공학과", "지능정보공학과", "소프트웨어학과",
        ], 4.5)

    # 의약학·교육 결론 보정 (강화)
    if any(k in conclusion_text for k in ["의대", "의예", "의학", "의료", "MMI"]):
        add_departments(["의예과", "의과학과"], 12.0)
        add_departments(TRACK_TO_DEPARTMENTS.get("MMI", []), 5.0)

    if "약학" in conclusion_text or "제약" in conclusion_text:
        add_departments(["약학과", "제약학과"] + DEPT_ALIAS.get("약학", []), 9.0)

    if "치의학" in conclusion_text or "치과" in conclusion_text:
        add_departments(["치의예과", "치의학과"], 9.0)

    if "한의" in conclusion_text:
        add_departments(["한의예과", "한의학과"], 9.0)

    if "간호" in conclusion_text or "보건" in conclusion_text:
        add_departments(DEPT_ALIAS.get("보건·재활", []) + DEPT_ALIAS.get("간호", []), 4.0)

    if "교사" in conclusion_text or "교직" in conclusion_text:
        add_departments(DEPT_ALIAS.get("교육", []), 6.0)

    if "미디어" in conclusion_text or "콘텐츠" in conclusion_text or "방송" in conclusion_text:
        add_departments(DEPT_ALIAS.get("미디어·광고·콘텐츠", []) + DEPT_ALIAS.get("미디어", []), 6.0)

    # 4) 상위 카테고리 fallback
    sorted_cats = sorted(category_scores.items(), key=lambda x: x[1], reverse=True)
    top_score_val = sorted_cats[0][1] if sorted_cats else 0.0
    for cat, score in sorted_cats[:5]:
        if score <= 0:
            continue
        if top_score_val > 0 and score < top_score_val * 0.55:
            continue
        # 카테고리 1위에는 더 큰 가중치를 줘서 변별력 확보
        weight_base = 3.5 if cat == top_category else 2.5
        weight = weight_base + min(score / 40.0, 3.5)
        add_departments(CATEGORY_TO_DEPARTMENTS.get(cat, []), weight)

    # 5) 보정 규칙
    if category_scores.get("의학", 0) > 0 and category_scores.get("간호", 0) > 0:
        if category_scores["의학"] >= category_scores["간호"] + 15:
            for d in DEPT_ALIAS.get("의학", []):
                dept_scores[d] += 2.0

    if category_scores.get("약학", 0) > 0:
        for d in DEPT_ALIAS.get("약학", []):
            dept_scores[d] += 2.0

    if category_scores.get("보건·재활", 0) > 0:
        for d in DEPT_ALIAS.get("보건·재활", []):
            dept_scores[d] += 1.5

    if category_scores.get("인공지능·데이터사이언스", 0) > 0 and not is_non_tech_dominant:
        for d in DEPT_ALIAS.get("인공지능·데이터사이언스", []):
            dept_scores[d] += 2.0

    if category_scores.get("컴퓨터·소프트웨어", 0) > 0 and not is_non_tech_dominant:
        for d in DEPT_ALIAS.get("컴퓨터·소프트웨어", []):
            dept_scores[d] += 1.5

    # 6) 비-STEM 카테고리 1위인데 AI/데이터 학과가 상위에 끼어든 경우 패널티
    if is_non_tech_dominant:
        TECH_DEPT_PENALTY = {
            "인공지능학과", "AI학과", "데이터사이언스학과", "지능정보공학과",
            "컴퓨터공학과", "소프트웨어학과", "정보통신학과",
        }
        for d in TECH_DEPT_PENALTY:
            if d in dept_scores:
                dept_scores[d] *= 0.35  # 65% 감점

    # 7) 너무 범용적인 학과는 약간 감점
    generic_penalty = {
        "교육학과": 0.5,
        "사회학과": 0.5,
        "경영학과": 0.5,
        "경제학과": 0.5,
    }
    for dept, penalty in generic_penalty.items():
        if dept in dept_scores:
            dept_scores[dept] -= penalty

    # 8) 최종 정렬
    ranked = sorted(dept_scores.items(), key=lambda x: (-x[1], x[0]))
    return [dept for dept, _ in ranked[:max_n]]
