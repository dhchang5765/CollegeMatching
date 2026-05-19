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
        return 92.0   # 상향
    if lo <= overall_grade <= hi:
        return 80.0   # 적정
    if overall_grade <= hi + 0.7:
        return 65.0   # 안정/경계
    return 45.0       # 불리

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

    # 학생 본인 이름은 키워드에서 동적으로 제외
    student_name = meta.get("student_name") if isinstance(meta, dict) else None
    extra_stop = {student_name} if student_name else set()
    top_keywords_all = extract_keywords_kiwi(text_for_keywords, top_n=60)
    top_keywords = [k for k in top_keywords_all if k not in extra_stop][:40]

    # 4) 전체 텍스트에서 등급 후보 수집 (기존 로직 재사용)
    grade_candidates = collect_all_floats(text_for_keywords, SPECIAL_PATTERNS["grade"])
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

def get_diag10_text(signals: Dict) -> str:
    for d in signals.get("diagnosis_sections", []):
        if d.get("diag_no") == 10:
            parts = [
                d.get("title", ""),
                d.get("banner_title", ""),
                d.get("prose_text", ""),
                " ".join(d.get("direct_quotes", [])),
                " ".join(d.get("banner_tags", [])),
            ]
            return " ".join([p for p in parts if p])
    return ""

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


def keyword_fit_score(signals: Dict, talent_keywords: List[str]) -> float:
    text = signals['raw_text']
    hits = sum(1 for kw in talent_keywords if kw in text)
    base = 40 + hits * 10
    if signals.get('admission_preference') == '학생부종합' and any(k in talent_keywords for k in ['창의', '소통', '실천', '리더십', '융합']):
        base += 8
    if signals.get('is_student_record_heavy') and any(k in talent_keywords for k in ['표현', '실천', '창의']):
        base += 6
    return base


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


def recommend_universities(db: Dict, signals: Dict, target_departments: List[str], top_n: int = 5) -> List[Dict]:
    recs = []
    overall_grade = signals.get("overall_grade")
    gscore = grade_fit_score(overall_grade)

    for u in db.get("universities", []):
        mscore_raw, matched = major_match_score(target_departments, u)
        if mscore_raw <= 0:
            continue

        tscore = keyword_fit_score(signals, u.get("talent_keywords", []))
        bonus = target_bonus(u.get("name", ""), signals)

        band, dep_match = extract_best_admission_band(u, target_departments)
        bscore = admission_band_score(overall_grade, band)

        fitcluster_bonus = 0.0
        fitcluster = (dep_match or {}).get("fitcluster")
        if fitcluster:
            top_cats = sorted(infer_category_scores(signals).items(), key=lambda x: x[1], reverse=True)[:2]
            top_fitclusters = []
            for cat, _ in top_cats:
                top_fitclusters.extend(CATEGORY_TO_FITCLUSTER.get(cat, []))
            if fitcluster in top_fitclusters:
                fitcluster_bonus += 8.0

        # ── 알고리즘 개선 ──
        # 1) mscore 정규화 (0~100 스케일)
        #    - 학과당 30점이 최대인데, 1개 학과 매칭만으로도 60점 이상 받도록 곡선 강화
        #    - sqrt 변환으로 1~3개 매칭의 차이를 완만하게 보정
        import math
        mscore_norm = min(100.0, math.sqrt(mscore_raw) * 14.0)

        # 2) 가중치 재조정 (합 1.0 유지, 학과 일치도 비중 확대)
        #    학과 매칭 50% + 등급 23% + 인재상 15% + 성적 12%
        base_score = (
            mscore_norm * 0.50 +
            bscore      * 0.23 +
            tscore      * 0.15 +
            gscore      * 0.12
        )

        # 3) 보너스는 base 위에 가산 (최대 +25점)
        bonus_total = min(25.0, fitcluster_bonus + bonus)

        # 4) 최종: base에 보너스 더하되 100점 상한
        total = round(min(100.0, base_score + bonus_total), 2)

        recs.append({
            "university": u.get("name"),
            "region": u.get("region"),
            "campus": u.get("campus"),
            "fit_score": total,
            "matched_departments": matched[:6],
            "talent_keywords": u.get("talent_keywords", []),
            "notes": u.get("notes", ""),
            "target_bonus": bonus,
            "major_score": round(mscore_norm, 1),  # 정규화된 값 표시
            "major_score_raw": round(mscore_raw, 1),
            "talent_score": round(tscore, 1),
            "grade_score": round(gscore, 1),
            "admission_band_score": round(bscore, 1),
            "matched_admission_band": band,
            "matched_department_detail": dep_match,
            "fitcluster_bonus": fitcluster_bonus,
        })

    recs.sort(key=lambda x: x["fit_score"], reverse=True)
    return recs[:top_n]


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
                merged = dict(category_scores)
                for cat, v in dec_scores.items():
                    merged[cat] = merged.get(cat, 0.0) + v
                category_scores = merged
            st.success(
                f"HTML + 답변 JSON 결합 분석 (질문지 {answer_result['version']}, "
                f"{answer_result['n_questions']}문항). "
                f"판정 엔진 v{answer_result['decision']['decision_version']} · "
                f"LLM 보강 {'사용' if answer_result['llm_used'] else '규칙 단독'}"
            )
        except Exception as e:
            st.warning(f"답변 JSON 처리 실패 — HTML 신호만 사용합니다: {e}")

        target_departments = choose_target_departments(signals, category_scores, max_n=2)
        recs = recommend_universities(db, signals, target_departments, top_n=5)
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


        m1, m2, m3, m4 = st.columns(4)
        with m1:
            render_metric_card('추천 학과 수', str(len(target_departments)), '요청 조건에 맞춰 최대 2개까지 제시합니다.')
        with m2:
            render_metric_card('추천 대학 수', str(len(recs)), '추천 결과는 최대 5개 대학까지 노출합니다.')
        with m3:
            render_metric_card('추정 전체 등급', str(signals.get('overall_grade') or '-'), '리포트 또는 답변에서 탐지한 대표 등급 값입니다.')
        with m4:
            render_metric_card('전형 적합도', signals.get('admission_preference') or '미탐지', '전형 서술 또는 수시/정시 응답을 반영합니다.')

        left, right = st.columns([1.05, 1.35])
        with left:
            render_chip_row('우선 추천 학과', target_departments, dept=True)
            render_chip_row('핵심 키워드', signals.get('top_keywords', [])[:12])

            # ── 학생 신호 ─────────────────────────────────────
            tracks = signals.get("detected_tracks") or []
            track_label = f"선호 트랙: {', '.join(tracks)}" if tracks else "선호 트랙: 미탐지"
            target_univ = signals.get('target_university')
            target_label = f"목표 대학: {target_univ}" if target_univ else "목표 대학: 미탐지"

            student_signals = [
                track_label,
                target_label,
                f"전형 성향: {signals.get('admission_orientation', '미탐지')}",
                '논술/글쓰기 강점' if signals.get('essay_strength') else '논술 강점 미탐지',
                '영어 강점' if signals.get('english_strength') else '영어 강점 미탐지',
                '수학 위험 신호' if signals.get('math_risk') else '수학 위험 없음',
                '과학 위험 신호' if signals.get('science_risk') else '과학 위험 없음',
                '인문·미디어 적합' if signals.get('humanities_media_fit') else '인문·미디어 약함',
                '이공계 적합' if signals.get('sci_track_fit') else None,
                '인문계 적합' if signals.get('humanities_track_fit') else None,
                '의·약학 지향' if signals.get('med_track_fit') else None,
                '비교과 활동 충실' if signals.get('extracurricular_strong') else None,
                '자기주도성 강함' if signals.get('self_directed') else None,
            ]
            student_signals = [s for s in student_signals if s]
            render_chip_row('학생 신호', student_signals)

            st.markdown(f"<div class='glass-card'><div class='section-title'>요약 분석</div><div class='subtle' style='font-size:0.96rem; line-height:1.7; color:#334155;'>{summary}</div></div>", unsafe_allow_html=True)

            # ── 계열 적합도 (원그래프) ────────────────────────
            render_category_donut(category_scores)

        with right:
            st.markdown("<div class='section-title'>추천 대학</div>", unsafe_allow_html=True)
            with st.expander("적합도 점수 산출 방식 안내", expanded=False):
                render_score_methodology()
            if not target_departments:
                st.warning("HTML에서 추천용 학과 후보를 충분히 구성하지 못했습니다. 키워드 사전 또는 최종 결론 반영 규칙을 점검해야 합니다.")
            elif not recs: 
                st.warning("추천 학과 후보는 추출되었지만, 현재 DB 학과명과의 매칭이 충분하지 않아 대학 추천이 생성되지 않았습니다.")
            for i, rec in enumerate(recs, start=1):
                render_university_card(rec, i)

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