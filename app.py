# 1. 표준 라이브러리 (내장 모듈)
import re
from collections import Counter, defaultdict
from typing import Dict, List, Tuple, Optional

# 2. 서드파티 라이브러리 (외부 설치 패키지)
import streamlit as st
try:
    from google import genai
except ImportError:
    genai = None

from constants import *
from extractHTML import *
from utils import *
from password import *
from renderUI import *

def parse_grade_band(s: str) -> Tuple[Optional[float], Optional[float]]:
    if not s:
        return None, None
    m = re.match(r"\s*([0-9.]+)\s*-\s*([0-9.]+)\s*", str(s))
    if not m:
        return None, None
    return float(m.group(1)), float(m.group(2))

def extract_best_admission_band(univ: Dict, target_departments: List[str]) -> Tuple[Optional[str], Optional[Dict]]:
    best = None
    best_dep = None
    for dep in univ.get("departments", []):
        dep_name = dep.get("name", "")
        if not any(t in dep_name or dep_name in t for t in target_departments):
            continue
        for adm in dep.get("admissions", []):
            band = adm.get("min_grade_band")
            if band:
                lo, hi = parse_grade_band(band)
                if lo is None:
                    continue
                if best is None or lo < parse_grade_band(best)[0]:
                    best = band
                    best_dep = {
                        "department": dep_name,
                        "track_name": adm.get("track_name"),
                        "fitcluster": dep.get("fit_cluster") or dep.get("fitcluster"),
                        "band": band,
                    }
    return best, best_dep

def admission_band_score(overall_grade: Optional[float], grade_band: Optional[str]) -> float:
    if overall_grade is None or not grade_band:
        return 55.0
    lo, hi = parse_grade_band(grade_band)
    if lo is None:
        return 55.0

    if overall_grade < lo:
        return 92.0   # 학생이 합격선보다 좋음 → 안정
    if lo <= overall_grade <= hi:
        return 80.0   # 합격선 범위 안 → 적정
    if overall_grade <= hi + 0.7:
        return 65.0   # 합격선 약간 위 → 상향(도전)
    return 45.0       # 합격선 많이 위 → 어려움


def classify_support_level(overall_grade: Optional[float],
                            grade_band: Optional[str]) -> Tuple[str, str]:
    """
    A2 — 학생 등급 vs 합격선 비교로 지원군 분류 (한국 입시 컨설팅 표준 용어).
    반환: (라벨, 한 줄 설명)

    등급은 낮을수록 좋다는 점을 반영.
    """
    if overall_grade is None or not grade_band:
        return ("정보부족", "학생 등급 또는 합격선 데이터가 없습니다.")
    lo, hi = parse_grade_band(grade_band)
    if lo is None:
        return ("정보부족", "합격선 데이터 형식을 해석할 수 없습니다.")

    # 학생 등급이 합격선 하한보다 0.3 이상 좋음
    if overall_grade <= lo - 0.3:
        return ("안정", f"학생 등급 {overall_grade} ≤ 합격선 {lo}-{hi}")
    # 학생 등급이 합격선 범위 안 (약간 좋음 포함)
    if overall_grade <= hi:
        return ("적정", f"학생 등급 {overall_grade} ∈ 합격선 {lo}-{hi}")
    # 합격선 약간 위
    if overall_grade <= hi + 0.3:
        return ("상향", f"학생 등급 {overall_grade} 가 합격선 {lo}-{hi} 보다 0.3 이내로 못함")
    if overall_grade <= hi + 0.7:
        return ("상향(도전)", f"학생 등급 {overall_grade} 가 합격선 {lo}-{hi} 보다 0.4~0.7 못함")
    return ("재고", f"학생 등급 {overall_grade} 가 합격선 {lo}-{hi} 보다 0.7 이상 못함")


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

def career_match_score(target_departments: List[str], university: Dict) -> Tuple[float, int]:
    """
    진로 일치도: 학생 추천 학과 1·2·3순위가 그 대학에 있는지 우선순위 가중.
    1순위 매칭 = 50점, 2순위 = 30점, 3순위 = 20점 → 합 최대 100점.
    학과명 매칭은 별칭(DEPT_ALIAS)을 통한 유연 매칭.
    """
    if not target_departments:
        return 0.0, 0

    from constants import DEPT_ALIAS
    weights = [50.0, 30.0, 20.0]  # 1·2·3순위 가중치
    score = 0.0
    matched_count = 0

    dept_names = []
    for dept in university.get("departments", []):
        n = dept.get("name", "")
        if n:
            dept_names.append(n)
            for alias in (dept.get("aliases") or []):
                dept_names.append(alias)

    for rank, target in enumerate(target_departments[:3]):
        # 별칭까지 포함한 매칭
        target_aliases = [target] + list(DEPT_ALIAS.get(target, []))
        for n in dept_names:
            if any(a in n or n in a for a in target_aliases):
                score += weights[rank]
                matched_count += 1
                break  # 한 순위당 1개만 카운트
    return min(100.0, score), matched_count


def track_match_score(track_recs: Optional[List[Dict]], university: Dict,
                       dep_match: Optional[Dict]) -> float:
    """
    전형 적합도: 학생의 추천 전형 Top1 점수를 기반으로,
    그 대학의 admissions 트랙에 해당 전형이 있으면 100% 반영, 없으면 70%만.
    """
    if not track_recs:
        return 55.0
    top_track = track_recs[0]
    student_track_id = top_track.get("id", "")
    student_score = float(top_track.get("score", 0))

    # 대학 admissions 트랙 명에서 해당 전형 식별
    track_keyword_map = {
        "haksang": ["학종", "학생부종합", "종합"],
        "gyogwa":  ["교과", "학생부교과"],
        "nonsul":  ["논술"],
        "jeongsi": ["정시", "수능"],
        "balanced":["지역균형", "학교장추천", "고른기회"],
        "regional":["지역인재"],
        "teukgi":  ["특기자", "실기"],
    }
    target_kws = track_keyword_map.get(student_track_id, [])
    if not target_kws:
        return student_score * 0.85

    # 대학 학과의 admissions 에서 매칭 트랙 검색
    has_track = False
    for dept in university.get("departments", []):
        for adm in dept.get("admissions", []):
            tname = (adm.get("track_name") or "") + " " + (adm.get("type") or "")
            if any(k in tname for k in target_kws):
                has_track = True
                break
        if has_track:
            break

    return student_score if has_track else student_score * 0.7


def major_match_score(target_departments: List[str], university: Dict) -> Tuple[float, List[str]]:
    score = 0.0
    matched = []

    targets = [normalize_major_name(t) for t in target_departments if t]

    for dep in university.get("departments", []):
        dep_name = dep.get("name", "")
        dep_aliases = dep.get("aliases", []) or []
        candidates = [dep_name] + dep_aliases
        norm_candidates = [normalize_major_name(x) for x in candidates if x]

        for target, raw_target in zip(targets, target_departments):
            for cand, raw_cand in zip(norm_candidates, candidates):
                if not cand:
                    continue
                if target == cand:
                    score += 30
                    matched.append(dep_name)
                    break
                elif target in cand or cand in target:
                    score += 22
                    matched.append(dep_name)
                    break
                elif (
                    ("인공지능" in raw_target and any(k in raw_cand for k in ["AI", "인공지능", "지능정보", "컴퓨터"]))
                    or ("데이터" in raw_target and any(k in raw_cand for k in ["데이터", "통계", "컴퓨터", "AI"]))
                    or ("소프트웨어" in raw_target and any(k in raw_cand for k in ["소프트웨어", "컴퓨터", "정보통신"]))
                ):
                    score += 18
                    matched.append(dep_name)
                    break

    return score, list(dict.fromkeys(matched))


def talent_fit_score_v2(signals: Dict, univ_name: str,
                         talent_keywords: List[str],
                         answer_result: Optional[Dict] = None) -> Tuple[float, str]:
    """
    워드 임베딩 기반 인재상 적합도 (v2).
    임베딩 모델 가용 시 의미 유사도, 미가용 시 키워드 부분 일치로 자동 fallback.
    추가 규칙 보너스(전형 일치, 학생부종합 가중치)는 유지.
    """
    from embeddings import build_student_profile_text, talent_similarity

    student_text = build_student_profile_text(signals, answer_result)
    base, backend = talent_similarity(student_text, univ_name, talent_keywords)

    # 도메인 규칙 보너스 (임베딩 단독으로 잡기 어려운 신호)
    if signals.get('admission_preference') == '학생부종합' and any(
        k in talent_keywords for k in ['창의', '소통', '실천', '리더십', '융합']
    ):
        base += 6
    if signals.get('is_student_record_heavy') and any(
        k in talent_keywords for k in ['표현', '실천', '창의']
    ):
        base += 4
    return min(100.0, base), backend


def grade_fit_score(overall_grade: Optional[float]) -> float:
    if overall_grade is None:
        return 55.0
    if overall_grade <= 2.0:
        return 90.0
    if overall_grade <= 2.5:
        return 82.0
    if overall_grade <= 3.0:
        return 74.0
    if overall_grade <= 3.5:
        return 66.0
    if overall_grade <= 4.0:
        return 58.0
    return 50.0


def target_bonus(university_name: str, signals: Dict) -> float:
    target = signals.get("target_university")
    if not target:
        return 0.0

    normalized_name = university_name.lower()

    alias_map = {
        "KAIST": ["kaist", "카이스트", "한국과학기술원"],
        "DGIST": ["dgist", "디지스트", "대구경북과학기술원"],
        "GIST": ["gist", "지스트", "광주과학기술원"],
        "UNIST": ["unist", "유니스트", "울산과학기술원"],
    }

    if target in alias_map:
        if any(alias in normalized_name for alias in [a.lower() for a in alias_map[target]]):
            return 12.0
    elif target.lower() in normalized_name:
        return 12.0

    return 0.0


def recommend_universities(db: Dict, signals: Dict, target_departments: List[str],
                            top_n: int = 5,
                            answer_result: Optional[Dict] = None,
                            track_recs: Optional[List[Dict]] = None) -> List[Dict]:
    """
    새 적합도 산출 (4축 + 보너스):
      - 합격선 적합도 35% (객관)
      - 진로 일치도 25% (학생 추천 학과 1·2·3 우선순위 가중)
      - 전형 적합도 25% (학생 추천 전형 × 대학 트랙 가용성)
      - 인재상 유사도 15% (상대 percentile 임베딩)
      - 보너스 최대 +25 (목표대학 가산)
      - 100점 상한
    """
    overall_grade = signals.get("overall_grade")

    # 1) 후보 대학 필터링 (학과 매칭 0인 대학 제외)
    candidates = []
    for u in db.get("universities", []):
        mscore_raw, matched = major_match_score(target_departments, u)
        if mscore_raw <= 0:
            continue
        candidates.append((u, mscore_raw, matched))

    if not candidates:
        return []

    # 2) 인재상 유사도 — 학생 1명에 대해 모든 후보 대학 한 번에 percentile 계산
    from embeddings import (
        compute_talent_similarities_normalized,
        build_student_profile_text,
    )
    student_profile = build_student_profile_text(signals, answer_result)
    talent_scores_map = compute_talent_similarities_normalized(
        student_profile, [u for u, _, _ in candidates]
    )
    talent_backend_used = "embedding(percentile)" if talent_scores_map else "keyword(fallback)"

    # 3) 각 대학 점수 산출
    recs = []
    for u, mscore_raw, matched in candidates:
        univ_name = u.get("name", "")

        # ── 4축 적합도 ───────────────────────────────
        # (A) 합격선 적합도 (35%)
        band, dep_match = extract_best_admission_band(u, target_departments)
        band_score = admission_band_score(overall_grade, band)

        # (B) 진로 일치도 (25%) — 추천 학과 1·2·3 우선순위 가중
        career_score, career_matched_count = career_match_score(target_departments, u)

        # (C) 전형 적합도 (25%)
        trk_score = track_match_score(track_recs, u, dep_match)

        # (D) 인재상 유사도 (15%) — percentile 상대 점수
        if talent_scores_map and univ_name in talent_scores_map:
            talent_score = talent_scores_map[univ_name]
        else:
            # 임베딩 미가용 시 키워드 부분 일치 fallback (절대값)
            from embeddings import talent_similarity
            talent_score, _ = talent_similarity(
                student_profile, univ_name, u.get("talent_keywords", []) or []
            )

        # ── 보너스 (최대 +25) ────────────────────────
        bonus = target_bonus(univ_name, signals)  # 목표 대학 가산

        # 진로 클러스터 일치 보너스 (의약학 지망 → 의예과 보유 대학 등)
        fitcluster_bonus = 0.0
        fitcluster = (dep_match or {}).get("fitcluster")
        if fitcluster:
            top_cats = sorted(infer_category_scores(signals).items(),
                              key=lambda x: x[1], reverse=True)[:2]
            top_fitclusters = []
            for cat, _ in top_cats:
                top_fitclusters.extend(CATEGORY_TO_FITCLUSTER.get(cat, []))
            if fitcluster in top_fitclusters:
                fitcluster_bonus = 8.0

        # 다수 학과 매칭 보너스 (2개 이상 매칭 시)
        multi_match_bonus = 5.0 if career_matched_count >= 2 else 0.0

        # 최종 산출
        base_score = (
            band_score   * 0.35 +
            career_score * 0.25 +
            trk_score    * 0.25 +
            talent_score * 0.15
        )
        bonus_total = min(25.0, bonus + fitcluster_bonus + multi_match_bonus)
        total = round(min(100.0, base_score + bonus_total), 2)

        # A2: 지원군 분류
        support_level, support_reason = classify_support_level(overall_grade, band)

        recs.append({
            "university": univ_name,
            "region": u.get("region"),
            "fit_score": total,
            "matched_departments": matched[:6],
            "talent_keywords": u.get("talent_keywords", []),
            "notes": u.get("notes", ""),
            "target_bonus": bonus,
            # 새 4축 점수
            "band_score": round(band_score, 1),
            "career_score": round(career_score, 1),
            "track_score": round(trk_score, 1),
            "talent_score": round(talent_score, 1),
            "talent_backend": talent_backend_used,
            "career_matched_count": career_matched_count,
            "matched_admission_band": band,
            "matched_department_detail": dep_match,
            "fitcluster_bonus": fitcluster_bonus,
            "multi_match_bonus": multi_match_bonus,
            "support_level": support_level,
            "support_reason": support_reason,
        })

    recs.sort(key=lambda x: x["fit_score"], reverse=True)
    return _distribute_by_support_level(recs, total=top_n)


def _distribute_by_support_level(scored_recs: List[Dict], total: int = 5) -> List[Dict]:
    """
    한국 입시 컨설팅 표준 분배 (안정 1 + 적정 2 + 상향 2 = 5).
    fit_score 내림차순으로 정렬된 입력을 받아 지원군별로 의도적으로 분배한다.

    원칙
    - 분배 목표(plan)를 우선 채움
    - 특정 그룹이 비면 fallback 순서에 따라 인접 그룹에서 보충
    - 최종 결과는 fit_score 내림차순으로 다시 정렬해 카드 순서 유지
    """
    if not scored_recs:
        return []

    # 지원군별 목표 개수 (한국 입시 컨설팅 표준 비율)
    plan = {"안정": 1, "적정": 2, "상향": 2}

    # 그룹화 (이미 fit_score 내림차순)
    groups: Dict[str, List[Dict]] = {}
    for r in scored_recs:
        lv = r.get("support_level") or "정보부족"
        groups.setdefault(lv, []).append(r)

    selected: List[Dict] = []
    # 1단계: plan 그대로 채움
    for lv, n in plan.items():
        if lv in groups:
            picks = groups[lv][:n]
            selected.extend(picks)
            groups[lv] = groups[lv][n:]

    # 2단계: 부족분을 fallback 순서로 채움
    # 적정 > 상향 > 상향(도전) > 안정 > 재고 > 정보부족 순
    fallback_order = ["적정", "상향", "상향(도전)", "안정", "재고", "정보부족"]
    while len(selected) < total:
        added = False
        for lv in fallback_order:
            if lv in groups and groups[lv]:
                selected.append(groups[lv].pop(0))
                added = True
                if len(selected) >= total:
                    break
        if not added:
            break  # 더 채울 후보가 없음

    # 최종 정렬: fit_score 내림차순
    selected.sort(key=lambda x: -x.get("fit_score", 0))
    return selected[:total]


def fallback_summary(signals: Dict, target_departments: List[str], recs: List[Dict]) -> str:
    dept_text = ', '.join(target_departments)
    univ_text = ', '.join(r['university'] for r in recs[:5])
    parts = [f'현재 예시 HTML 기준 우선 추천 학과는 {dept_text}입니다.']
    if signals.get('admission_preference'):
        parts.append(f"학생은 {signals['admission_preference']} 중심 전략에 더 적합한 패턴으로 해석됩니다.")
    if signals.get('math_risk'):
        parts.append('수학 약점과 회피 신호가 반복되어 공학계열보다 인문·사회계열 추천 우선순위가 높습니다.')
    if signals.get('target_university'):
        parts.append(f"HTML 내 목표 대학 신호는 {signals['target_university']}로 해석되었습니다.")
    if univ_text:
        parts.append(f'추천 대학은 {univ_text}입니다.')
    return ' '.join(parts)


def summarize_with_gemini(signals: Dict, target_departments: List[str], recs: List[Dict]) -> str:
    api_key = get_secret_value("GEMINI_API_KEY")
    if not api_key or genai is None:
        return fallback_summary(signals, target_departments, recs)
    try:
        client = genai.Client(api_key=api_key)
        prompt = (
            f"학생 핵심 키워드: {signals.get('top_keywords', [])[:15]}\n"
            f"전체 등급 추정: {signals.get('overall_grade')}\n"
            f"목표 대학 신호: {signals.get('target_university')}\n"
            f"추천 학과: {target_departments}\n"
            f"추천 대학: {[r['university'] for r in recs]}\n"
            "한국어 plain text로 5문장 이내 요약. 과장 금지."
        )
        resp = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        if getattr(resp, 'text', None):
            return resp.text.strip()
    except Exception:
        pass
    return fallback_summary(signals, target_departments, recs)

def build_recommendation_html(recs: List[Dict],
                              target_departments: List[str],
                              signals: Dict,
                              summary: str,
                              category_scores: Dict[str, float]) -> str:
    """
    추천 카드 화면을 독립 HTML 파일로 직렬화.
    Streamlit 의존 없이 어떤 브라우저에서도 열림.
    """
    import html as _html
    from datetime import datetime

    def esc(s):
        return _html.escape(str(s)) if s is not None else ""

    meta = signals.get("report_meta", {}) or {}
    student = esc(meta.get("student_name") or "학생")
    today = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 학생 신호 칩
    tracks = signals.get("detected_tracks") or []
    track_label = f"선호 트랙: {', '.join(tracks)}" if tracks else "선호 트랙: 미탐지"
    target_univ = signals.get('target_university')
    target_label = f"목표 대학: {target_univ}" if target_univ else "목표 대학: 미탐지"
    raw_chips = [
        track_label, target_label,
        f"전형 성향: {signals.get('admission_orientation', '미탐지')}",
        '논술/글쓰기 강점' if signals.get('essay_strength') else '논술 강점 미탐지',
        '영어 강점' if signals.get('english_strength') else '영어 강점 미탐지',
        '수학 위험 신호' if signals.get('math_risk') else '수학 위험 없음',
        '과학 위험 신호' if signals.get('science_risk') else '과학 위험 없음',
        '이공계 적합' if signals.get('sci_track_fit') else None,
        '인문계 적합' if signals.get('humanities_track_fit') else None,
        '의·약학 지향' if signals.get('med_track_fit') else None,
    ]
    chips_html = "".join(
        f"<span class='chip'>{esc(c)}</span>" for c in raw_chips if c
    )

    # 추천 카드들
    card_blocks = []
    for i, r in enumerate(recs, start=1):
        fit = int(round(r.get("fit_score", 0)))
        band_pct = max(0, min(100, int(r.get("band_score", 0))))
        career_pct = max(0, min(100, int(r.get("career_score", 0))))
        track_pct = max(0, min(100, int(r.get("track_score", 0))))
        talent_pct = max(0, min(100, int(r.get("talent_score", 0))))
        talent_kws = ", ".join(r.get("talent_keywords", [])[:5]) or "—"
        band = r.get("matched_admission_band") or "—"
        notes = r.get("notes", "") or ""
        support = r.get("support_level") or ""
        card_blocks.append(f"""
        <div class='card'>
          <div class='card-head'>
            <div>
              <div class='rank'>추천 {i} {('· ' + esc(support)) if support else ''}</div>
              <div class='univ'>{esc(r.get("university"))}</div>
              <div class='meta'>{esc(r.get("region") or "")}</div>
            </div>
            <div class='pill'>적합도 {fit}</div>
          </div>
          <div class='bar-label'>총 적합도</div>
          <div class='bar'><div class='fill' style='width:{fit}%'></div></div>
          <div class='bar-label'>합격선 적합도 (35%)</div>
          <div class='bar'><div class='fill' style='width:{band_pct}%'></div></div>
          <div class='bar-label'>진로 일치도 (25%)</div>
          <div class='bar'><div class='fill' style='width:{career_pct}%'></div></div>
          <div class='bar-label'>전형 적합도 (25%)</div>
          <div class='bar'><div class='fill' style='width:{track_pct}%'></div></div>
          <div class='bar-label'>인재상 유사도 (15%)</div>
          <div class='bar'><div class='fill' style='width:{talent_pct}%'></div></div>
          <div class='kv'><b>인재상 키워드</b> {esc(talent_kws)}</div>
          <div class='kv'><b>매칭 등급대</b> {esc(band)}</div>
          {"<div class='note'>"+esc(notes)+"</div>" if notes else ""}
        </div>""")

    cards_html = "\n".join(card_blocks)
    depts_html = ", ".join(target_departments) or "—"

    # 계열 적합도 Top 5(>0)
    cat_top = sorted(
        [(k, v) for k, v in category_scores.items() if v > 0],
        key=lambda x: -x[1]
    )[:5]
    cat_total = sum(v for _, v in cat_top) or 1
    cat_lis = "".join(
        f"<li>{esc(k)} <span class='pct'>{int(v/cat_total*100)}%</span></li>"
        for k, v in cat_top
    ) or "<li>—</li>"

    css = """
    :root {
      --bg-app: #f5f7fb; --bg-card: #ffffff; --bg-panel: #ffffff;
      --bg-chip: #f1f5f9; --bg-dept-chip: #dbeafe; --bg-bar: #f1f5f9;
      --bg-note: #f8fafc; --bg-cats-divider: #f1f5f9;
      --text-primary: #0f172a; --text-body: #334155; --text-meta: #475569;
      --text-subtle: #64748b; --text-faint: #94a3b8;
      --text-chip: #334155; --text-dept-chip: #1d4ed8; --accent: #2563eb;
      --border: #e2e8f0;
    }
    @media (prefers-color-scheme: dark) {
      :root {
        --bg-app: #0b1220; --bg-card: #1e293b; --bg-panel: #1e293b;
        --bg-chip: #1e293b; --bg-dept-chip: #1e3a8a; --bg-bar: #334155;
        --bg-note: #0f172a; --bg-cats-divider: #334155;
        --text-primary: #f1f5f9; --text-body: #cbd5e1; --text-meta: #94a3b8;
        --text-subtle: #94a3b8; --text-faint: #64748b;
        --text-chip: #cbd5e1; --text-dept-chip: #93c5fd; --accent: #60a5fa;
        --border: #334155;
      }
    }
    body { font-family: -apple-system, 'Pretendard', 'Apple SD Gothic Neo', sans-serif;
           background: var(--bg-app); color: var(--text-primary);
           padding: 2rem; line-height: 1.55; }
    .container { max-width: 1200px; margin: 0 auto; }
    .header { background: linear-gradient(135deg,#0f172a,#1e3a8a,#2563eb); color:white;
              padding: 1.4rem 1.6rem; border-radius: 18px; margin-bottom: 1.2rem; }
    .header h1 { margin: 0 0 0.3rem 0; font-size: 1.5rem; color: white; }
    .header .sub { opacity: 0.85; font-size: 0.9rem; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1.2rem; }
    .panel { background: var(--bg-panel); border-radius: 14px; padding: 1.1rem 1.2rem;
             border: 1px solid var(--border); }
    .panel h3 { margin: 0 0 0.6rem 0; font-size: 0.78rem; color: var(--accent);
                text-transform: uppercase; letter-spacing: 0.06em; }
    .chip { display: inline-block; background: var(--bg-chip); color: var(--text-chip);
            border: 1px solid var(--border); padding: 0.3rem 0.6rem; border-radius: 999px;
            margin: 0.15rem 0.25rem 0.15rem 0; font-size: 0.83rem; }
    .dept-chip { background: var(--bg-dept-chip); color: var(--text-dept-chip);
                 border-color: var(--bg-dept-chip); font-weight: 700; padding: 0.4rem 0.7rem; }
    .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; }
    @media (max-width: 1024px) { .grid { grid-template-columns: repeat(2, 1fr); } }
    @media (max-width: 640px) { .grid { grid-template-columns: 1fr; } .row { grid-template-columns: 1fr; } }
    .card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px;
            padding: 1rem 1.1rem; }
    .card-head { display: flex; justify-content: space-between; align-items: flex-start;
                 gap: 0.6rem; margin-bottom: 0.7rem; }
    .rank { font-size: 0.7rem; font-weight: 700; color: var(--text-faint);
            text-transform: uppercase; letter-spacing: 0.05em; }
    .univ { font-size: 1.05rem; font-weight: 800; color: var(--text-primary); }
    .meta { font-size: 0.8rem; color: var(--text-faint); margin-top: 0.1rem; }
    .pill { background: linear-gradient(135deg,#1d4ed8,#3b82f6); color: white;
            padding: 0.4rem 0.7rem; border-radius: 999px; font-weight: 800;
            font-size: 0.85rem; white-space: nowrap; }
    .bar-label { font-size: 0.75rem; color: var(--text-subtle); margin: 0.4rem 0 0.15rem; }
    .bar { height: 8px; background: var(--bg-bar); border-radius: 999px; overflow: hidden; }
    .fill { height: 8px; background: linear-gradient(90deg,#93c5fd,#2563eb); border-radius: 999px; }
    .kv { font-size: 0.82rem; color: var(--text-meta); margin-top: 0.45rem; }
    .kv b { color: var(--text-primary); margin-right: 0.3rem; }
    .note { font-size: 0.8rem; color: var(--text-subtle); margin-top: 0.5rem;
            background: var(--bg-note); padding: 0.4rem 0.55rem; border-radius: 8px; }
    .summary { font-size: 0.92rem; line-height: 1.7; color: var(--text-body); }
    ul.cats { list-style: none; padding: 0; margin: 0; }
    ul.cats li { padding: 0.3rem 0; border-bottom: 1px solid var(--bg-cats-divider);
                 font-size: 0.88rem; display: flex; justify-content: space-between;
                 color: var(--text-body); }
    .pct { color: var(--accent); font-weight: 700; }
    .footer { text-align: center; color: var(--text-faint); font-size: 0.8rem; margin-top: 1.2rem; }
    """

    return f"""<!DOCTYPE html>
<html lang='ko'>
<head>
<meta charset='UTF-8'>
<title>대학 추천 결과 — {student}</title>
<style>{css}</style>
</head>
<body>
  <div class='container'>
    <div class='header'>
      <h1>🎓 대학 추천 결과 — {student}</h1>
      <div class='sub'>생성 시각: {today} · MOS Consulting · CollegeMatching</div>
    </div>

    <div class='row'>
      <div class='panel'>
        <h3>우선 추천 학과</h3>
        <div>{"".join(f"<span class='chip dept-chip'>{esc(d)}</span>" for d in target_departments) or "<span class='chip'>—</span>"}</div>
        <h3 style='margin-top:1rem;'>학생 신호</h3>
        <div>{chips_html}</div>
      </div>
      <div class='panel'>
        <h3>요약 분석</h3>
        <div class='summary'>{esc(summary)}</div>
        <h3 style='margin-top:1rem;'>계열 적합도 (상위)</h3>
        <ul class='cats'>{cat_lis}</ul>
      </div>
    </div>

    <h3 style='font-size:0.78rem; color:var(--accent); text-transform:uppercase;
              letter-spacing:0.06em; margin-bottom:0.6rem;'>추천 대학</h3>
    <div class='grid'>
      {cards_html}
    </div>

    <div class='footer'>
      적합도 = (합격선 0.35 + 진로 0.25 + 전형 0.25 + 인재상 0.15) + 보너스(최대 25점),
      100점 상한 · 결정론적 산출
    </div>
  </div>
</body>
</html>"""


def main():
    st.set_page_config(
        page_title='학생 HTML 기반 대학 추천기',
        page_icon='🎓',
        layout='wide',
        initial_sidebar_state='collapsed'
    )
    inject_css()
    render_hero()

    if not require_login():
        st.stop()

    try:
        db = load_json_db(JSON_DB_PATH)
    except Exception as e:
        st.error(str(e))
        st.stop()

    # DB 통계 집계
    univs = db.get('universities', [])
    n_univ = len(univs)
    n_dept = sum(len(u.get('departments', [])) for u in univs)
    n_adm = sum(len(d.get('admissions', [])) for u in univs for d in u.get('departments', []))

    top1, top2, top3 = st.columns(3)
    with top1:
        render_metric_card(
            '연결 DB',
            f"{n_univ}개 대학",
            f"학과 {n_dept}개 · 전형 {n_adm}개 정보를 로드했습니다."
        )
    with top2:
        render_metric_card(
            '입력 형식',
            '학생 HTML',
            '학생 정보를 담은 MOS 진단 보고서를 삽입하세요.'
        )
    with top3:
        render_metric_card(
            '분석 엔진',
            'Gemini + Kiwi 형태소',
            'AI 요약과 한국어 형태소 분석으로 핵심 신호만 추출합니다.'
        )

    col_up1, col_up2 = st.columns(2)
    with col_up1:
        uploaded_html = st.file_uploader('학생 분석 HTML 업로드', type=['html', 'htm'])
    with col_up2:
        uploaded_answers = st.file_uploader('학생 답변 JSON 업로드', type=['json'])

    # HTML 과 JSON 을 모두 첨부했을 때만 분석 진행.
    # 한쪽만 올리면 분석을 막아 AI API 중복 호출(리소스 낭비)을 방지한다.
    both_uploaded = (uploaded_html is not None) and (uploaded_answers is not None)

    if (uploaded_html is not None) ^ (uploaded_answers is not None):
        missing = "학생 답변 JSON" if uploaded_html is not None else "학생 분석 HTML"
        st.info(
            f"분석을 시작하려면 HTML 과 JSON 을 **모두** 첨부해야 합니다. "
            f"현재 '{missing}' 파일이 없습니다. 두 파일이 모두 업로드되면 "
            f"결합 분석이 1회 실행됩니다 (AI API 중복 호출 방지)."
        )

    if both_uploaded:
        answer_result = None
        answers_text = uploaded_answers.read().decode('utf-8', errors='ignore')

        # ── HTML + JSON 결합 분석 (AI 파이프라인 단일 실행) ──
        html_text = uploaded_html.read().decode('utf-8', errors='ignore')
        signals = extract_example_specific_signals(html_text)
        category_scores = infer_category_scores(signals)

        try:
            from answer_pipeline import run_answer_pipeline
            answer_result = run_answer_pipeline(
                answers_text,
                base_category_scores=category_scores,
                use_llm=True,
                log_prediction=False,
            )
            dec_scores = answer_result["decision"]["category_scores"]
            if dec_scores:
                # HTML 보고서는 AI가 학생 답변을 재가공한 2차 산출물이므로 과해석 위험.
                # 답변 JSON 은 학생의 1인칭 직접 응답이라 더 신뢰도가 높다.
                # → 답변 점수 가중치를 강하게 적용하고, HTML 점수는 절반으로 약화.
                ANSWER_WEIGHT = 3.0   # 답변 JSON 가중치 (HTML 대비 6배 영향)
                HTML_DAMPENING = 0.5  # 답변 JSON 있을 때 HTML 점수 약화
                merged = {cat: v * HTML_DAMPENING for cat, v in category_scores.items()}
                for cat, v in dec_scores.items():
                    merged[cat] = merged.get(cat, 0.0) + v * ANSWER_WEIGHT
                category_scores = merged

            # 학생 등급 보완: HTML 파서가 등급을 못 잡았으면 답변에서 추출
            if signals.get("overall_grade") is None:
                rs = answer_result.get("rule_signals", {}) or {}
                grade_text = (rs.get("grade_goal_text") or "") + " " + (rs.get("target_tier_text") or "")
                import re as _re
                m = _re.search(r"([1-9](?:\.\d)?)\s*등급", grade_text)
                if m:
                    try:
                        signals["overall_grade"] = float(m.group(1))
                    except Exception:
                        pass

            # 답변 JSON 의 신호(강·약점 과목, 비교과·자기주도성)를 signals 에 동기화.
            # 로드맵 갭 분석 + 전형 추천이 더 정확하게 작동하도록 보강.
            rs = answer_result.get("rule_signals", {}) or {}
            answer_strong = set(rs.get("strong_subjects") or [])
            answer_weak = set(rs.get("weak_subjects") or [])
            if answer_weak:
                if any(s in answer_weak for s in ["수학"]):
                    signals["math_risk"] = True
                if any(s in answer_weak for s in ["과학", "물리", "화학", "생명과학", "지구과학", "탐구"]):
                    signals["science_risk"] = True
                if "영어" not in answer_strong and "영어" in answer_weak:
                    signals["english_strength"] = False
            if "국어" in answer_strong:
                signals["essay_strength"] = True
            # 답변 클러스터로 진로 적합 신호도 보강
            ac = set(rs.get("career_clusters") or [])
            if "의약학" in ac:
                signals["med_track_fit"] = True
            if any(c in ac for c in ["컴퓨터·AI", "공학", "수리·통계"]):
                signals["sci_track_fit"] = True
            if any(c in ac for c in ["미디어·콘텐츠", "인문·언어", "사회·정치"]):
                signals["humanities_media_fit"] = True

            st.success(
                f"HTML + 답변 JSON 결합 분석 (질문지 {answer_result['version']}, "
                f"{answer_result['n_questions']}문항). "
                f"판정 엔진 v{answer_result['decision']['decision_version']} · "
                f"LLM 보강 {'사용' if answer_result['llm_used'] else '규칙 단독'}"
            )
        except Exception as e:
            st.warning(f"답변 JSON 처리 실패 — HTML 신호만 사용합니다: {e}")

        target_departments = choose_target_departments(signals, category_scores, max_n=3)

        # 추천 전형은 추천 대학 점수 산출에도 사용되므로 먼저 계산
        from admission_tracks import recommend_tracks, detect_student_region
        track_recs = recommend_tracks(signals, answer_result)
        student_area = detect_student_region(signals)

        recs = recommend_universities(db, signals, target_departments, top_n=5,
                                       answer_result=answer_result,
                                       track_recs=track_recs)
        summary = summarize_with_gemini(signals, target_departments, recs)

        # 답변 파이프라인 상세(설명가능성·거버넌스)
        if answer_result is not None:
            dec = answer_result["decision"]
            ml = answer_result["ml_crosscheck"]
            with st.expander("답변 기반 판정 근거 (설명가능성)", expanded=True):
                st.markdown(f"**최종 판정 Top3**: {' · '.join(dec['top_categories'])}")
                st.caption(
                    f"판정 방식: 결정론 규칙 엔진 (동일 입력→동일 출력) · "
                    f"버전 {dec['decision_version']}"
                )
                rs = answer_result["rule_signals"]
                st.markdown(
                    f"- 강점 과목: {rs['strong_subjects'] or '—'}\n"
                    f"- 약점 과목: {rs['weak_subjects'] or '—'}\n"
                    f"- 규칙 확정 진로 클러스터: {rs['career_clusters'] or '—'}\n"
                    f"- 목표 대학 진술: {rs['target_tier_text'] or '—'}"
                )
                ml_mode = answer_result["ml_status"]["mode"]
                ml_note = (
                    f"ML 교차검증: {ml.get('confidence_flag','-')} "
                    f"(모드 {ml_mode}, 레이블 "
                    f"{answer_result['ml_status']['labeled']}/"
                    f"{answer_result['ml_status']['threshold']}) — "
                    f"ML은 판정자가 아닌 자문입니다."
                )
                st.caption(ml_note)
                with st.expander("점수 변동 감사 추적 (audit trail)", expanded=False):
                    st.json(dec["audit_trail"][:40])


        # ── 상단: 학생 분석 영역 (좌우 2열) ─────────────────────
        st.markdown(
            "<div class='section-title' style='margin-top:1rem;'>학생 분석</div>",
            unsafe_allow_html=True
        )
        left, right = st.columns([1, 1], gap="medium")
        with left:
            render_chip_row('우선 추천 학과', target_departments, dept=True)

            # ── 학생 프로파일 (4슬롯: 강점·약점·관심·위험) ──────
            from student_profile import build_student_profile
            profile = build_student_profile(
                signals, answer_result,
                answers_text=answers_text if both_uploaded else None
            )
            render_student_profile_card(profile)

        with right:
            st.markdown(
                f"<div class='glass-card'><div class='section-title'>요약 분석</div>"
                f"<div class='subtle' style='font-size:0.96rem; line-height:1.7; color:var(--text-body);'>{summary}</div></div>",
                unsafe_allow_html=True
            )
            # 계열 적합도 (원그래프) — 좌측 칩 묶음과 높이 균형 맞추기 좋음
            render_category_donut(category_scores)

        # ── 중간: 추천 전형 (A3) ────────────────────────────────
        render_track_recommendations(track_recs, student_area)

        # ── 하단: 추천 대학 ─────────────────────────────────────
        st.markdown(
            "<div class='section-title' style='margin-top:1.5rem;'>추천 대학</div>",
            unsafe_allow_html=True
        )
        with st.expander("적합도 점수 산출 방식 안내", expanded=False):
            render_score_methodology()

        if not target_departments:
            st.warning("HTML에서 추천용 학과 후보를 충분히 구성하지 못했습니다. 키워드 사전 또는 최종 결론 반영 규칙을 점검해야 합니다.")
        elif not recs:
            st.warning("추천 학과 후보는 추출되었지만, 현재 DB 학과명과의 매칭이 충분하지 않아 대학 추천이 생성되지 않았습니다.")
        else:
            # A2: 추천 대학을 지원군별로 그룹핑하여 표시
            level_order = ["안정", "적정", "상향", "상향(도전)", "재고", "정보부족"]
            grouped: Dict[str, List[Dict]] = {lv: [] for lv in level_order}
            for r in recs:
                lv = r.get("support_level") or "정보부족"
                grouped.setdefault(lv, []).append(r)

            global_rank = 1
            for lv in level_order:
                cards = grouped.get(lv, [])
                if not cards:
                    continue
                render_support_level_header(lv, len(cards))
                row_size = 3
                for row_start in range(0, len(cards), row_size):
                    row = cards[row_start:row_start + row_size]
                    cols = st.columns(row_size)
                    for col_i, rec in enumerate(row):
                        with cols[col_i]:
                            render_university_card(rec, global_rank)
                            # 학습 갭 로드맵 (펼침 패널)
                            from roadmap import build_roadmap
                            roadmap = build_roadmap(rec, signals, answer_result, track_recs)
                            render_roadmap_panel(roadmap, rec['university'])
                            global_rank += 1

            # ── HTML 저장 버튼 ─────────────────────────────────
            st.markdown(
                "<div style='margin-top:1.2rem;'></div>",
                unsafe_allow_html=True
            )
            html_blob = build_recommendation_html(
                recs=recs,
                target_departments=target_departments,
                signals=signals,
                summary=summary,
                category_scores=category_scores,
            )
            student_name_hint = (signals.get("report_meta", {}) or {}).get("student_name") or "학생"
            st.download_button(
                label="📥 추천 카드 화면을 HTML 파일로 저장",
                data=html_blob.encode("utf-8"),
                file_name=f"추천대학_{student_name_hint}.html",
                mime="text/html",
                width='stretch',
            )

        with st.expander('세부 추출 정보', expanded=False):
            st.json({
                'overall_grade': signals.get('overall_grade'),
                'subjects': signals.get('subjects'),
                'preferred_track': signals.get('preferred_track'),
                'target_university': signals.get('target_university'),
                'admission_preference': signals.get('admission_preference'),
                'essay_strength': signals.get('essay_strength'),
                'math_risk': signals.get('math_risk'),
                'humanities_media_fit': signals.get('humanities_media_fit'),
                'category_scores': category_scores,
                'target_departments': target_departments,
                'top_keywords': signals.get('top_keywords', [])[:20]
            })

        with st.expander('원시 텍스트 미리보기', expanded=False):
            st.text_area('HTML 추출 텍스트', signals['raw_text'][:5000], height=280)
        
        with st.expander("디버그: 파싱된 리포트 구조 보기", expanded=False):
            st.json({
                "meta": signals.get("report_meta"),
                "simulation": signals.get("simulation"),
                "final_conclusion": signals.get("final_conclusion"),
            })

if __name__ == '__main__':
    main()
