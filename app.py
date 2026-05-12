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
from dotenv import load_dotenv
load_dotenv()  # .env 파일을 환경변수로 로드

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
    
    # 3) 전체 텍스트에서 핵심 키워드 수집
    text_for_keywords = focused_text if focused_text.strip() else raw_text
    lines = [ln.strip() for ln in re.split(r"[.!?]", text_for_keywords) if ln.strip()]
    topkeywords = Counter(re.findall(r"[A-Za-z가-힣]{2,20}", text_for_keywords))
    for stop in STOPWORDS:
        topkeywords.pop(stop, None)
    # 추가: 2~3자 영어 약어 중 의미 없는 것 제거
    for key in list(topkeywords.keys()):
        if re.fullmatch(r"[A-Z]{1,3}", key):  # 1~3자 대문자만으로 된 토큰 제거
            topkeywords.pop(key, None)
    

    # 4) 전체 텍스트에서 등급 후보 수집
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
    detected_tracks: list[str] = []
    lower_text = text_for_keywords.lower()
    for track, keywords in TRACK_DETECTION_RULES.items():
        if any(kw.lower() in lower_text for kw in keywords):
            detected_tracks.append(track)
    
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

    return {
        "raw_text": raw_text,
        "overall_grade": overall_grade_num,
        "subjects": subjects,
        "topkeywords": [w for w, _ in topkeywords.most_common(40)],
        "top_keywords": [w for w, _ in topkeywords.most_common(40)],
        "detected_tracks": detected_tracks,
        "preferred_track": detected_tracks[0] if detected_tracks else None,
        "target_university": target_university,
        "is_student_record_heavy": is_student_record_heavy,
        "admission_preference": admission_preference,
        "essay_strength": essay_strength,
        "math_risk": math_risk,
        "humanities_media_fit": humanities_media_fit,
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



# 계열별 핵심 키워드와 가중치: 일반 키워드(1.0)보다 고가중치 키워드를 우선 적용
CATEGORY_KEYWORD_WEIGHTS: Dict[str, Dict[str, float]] = {
    "인공지능·데이터사이언스": {
        "인공지능": 5.0, "AI": 5.0, "머신러닝": 4.5, "딥러닝": 4.5,
        "데이터사이언스": 4.0, "자연어처리": 3.5, "컴퓨터비전": 3.5,
    },
    "컴퓨터·소프트웨어": {
        "소프트웨어": 4.5, "프로그래밍": 4.0, "코딩": 3.5,
        "알고리즘": 3.5, "개발": 3.0, "컴퓨터": 3.0,
    },
    "미디어·광고·콘텐츠": {
        "미디어": 4.5, "콘텐츠": 4.0, "스토리텔링": 4.0, "기획": 3.5,
        "광고": 3.0, "홍보": 3.0, "저널리즘": 3.5, "방송": 3.0,
    },
    "국어국문·언어": {
        "글쓰기": 4.5, "문학": 4.0, "국어": 3.5, "언어": 3.0,
        "문예": 3.5, "번역": 3.0, "비평": 3.0,
    },
    "사회과학": {
        "정치": 4.0, "법률": 4.0, "행정": 3.5, "국제관계": 4.0,
        "외교": 3.5, "사회문제": 3.0, "인권": 3.0,
    },
    "경영·경제": {
        "경영": 4.0, "경제": 4.0, "창업": 4.0, "금융": 3.5,
        "마케팅": 3.5, "무역": 3.0, "투자": 3.0,
    },
    "수학·통계": {
        "수학": 4.0, "통계": 4.5, "미적분": 4.0, "확률": 3.5,
        "선형대수": 4.0, "알고리즘": 3.5, "최적화": 3.5,
    },
    "생명과학·바이오": {
        "생명과학": 5.0, "유전": 4.5, "DNA": 4.5, "바이오": 4.0,
        "세포": 3.5, "분자생물": 4.0, "면역": 3.5,
    },
    "의학": {
        "의료": 4.5, "임상": 4.5, "진단": 4.0, "해부": 4.5,
        "약리": 4.0, "병태생리": 4.5, "수술": 4.0,
    },
    "약학": {
        "약학": 5.0, "제약": 4.5, "신약": 4.5, "약물": 4.0,
        "의약품": 4.0, "약사": 4.5,
    },
}

def infer_category_scores(signals: Dict) -> Dict[str, float]:
    text = signals["raw_text"]
    scores: Dict[str, float] = {k: 0.0 for k in CATEGORY_KEYWORDS}

    # 1) 가중치 키워드 우선 적용
    for cat, kw_weights in CATEGORY_KEYWORD_WEIGHTS.items():
        if cat not in scores:
            continue
        for kw, weight in kw_weights.items():
            if kw in text:
                scores[cat] += weight

    # 2) 일반 카테고리 키워드 매칭 (가중치 키워드에 없는 나머지)
    for cat, kws in CATEGORY_KEYWORDS.items():
        weighted_kws = set(CATEGORY_KEYWORD_WEIGHTS.get(cat, {}).keys())
        for kw in kws:
            if kw not in weighted_kws and kw in text:
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
    preferred_track = detected_tracks[0] if detected_tracks else None
    target_university = signals.get("target_university")
    final_conclusion = signals.get("final_conclusion", {}) or {}

    dept_scores = defaultdict(float)

    def add_departments(departments: List[str], score: float):
        for d in departments:
            if d:
                dept_scores[d] += score

    # 1) 트랙 우선: 가장 강한 신호
    if preferred_track and preferred_track in TRACK_TO_DEPARTMENTS:
        add_departments(TRACK_TO_DEPARTMENTS[preferred_track], 8.0)

    # 2) 직접 시드 언급: 키워드 길이와 등장 횟수 반영
    for seed, departments in DEPT_ALIAS.items():
        hit_count = text.count(seed)
        is_korean = bool(re.search(r'[가-힣]', seed))
        if hit_count > 0:
            base = 6.0 if (len(seed) >= 4 or is_korean) else 3.0
            add_departments(departments, base + min(hit_count - 1, 3) * 1.5)

    # 3) 최종 결론/시뮬레이션 단서 반영
    conclusion_text = " ".join(
        [c.get("title", "") + " " + c.get("body", "") for c in final_conclusion.get("cards", [])]
    )

    if "AI" in conclusion_text and "인공지능" in conclusion_text:
        add_departments(TRACK_TO_DEPARTMENTS.get("AI", []), 6.0)
    if "데이터" in conclusion_text:
        add_departments(TRACK_TO_DEPARTMENTS.get("데이터", []), 5.5)
    if "소프트웨어" in conclusion_text or "코딩" in conclusion_text:
        add_departments(TRACK_TO_DEPARTMENTS.get("SW", []), 5.0)

    # IST 대학 목표 보정
    if target_university in {"KAIST", "DGIST", "GIST", "UNIST"}:
        add_departments([
            "인공지능학과",
            "데이터사이언스학과",
            "컴퓨터공학과",
            "전기전자공학과",
            "지능정보공학과",
            "소프트웨어학과"
        ], 4.5)
    
    if "MMI" in conclusion_text:
        add_departments(TRACK_TO_DEPARTMENTS.get("MMI", []), 5.0)

    if "약학" in conclusion_text or "제약" in conclusion_text:
        add_departments(DEPT_ALIAS.get("약학", []), 4.5)

    if "간호" in conclusion_text or "보건" in conclusion_text:
        add_departments(DEPT_ALIAS.get("보건·재활", []) + DEPT_ALIAS.get("간호", []), 4.0)

    if "의학" in conclusion_text or "의료" in conclusion_text:
        add_departments(DEPT_ALIAS.get("의학", []), 4.5)

    # 4) 상위 카테고리 fallback: 점수 높은 카테고리만 반영
    sorted_cats = sorted(category_scores.items(), key=lambda x: x[1], reverse=True)

    top_score = sorted_cats[0][1] if sorted_cats else 0.0
    for cat, score in sorted_cats[:5]:
        if score <= 0:
            continue
        if top_score > 0 and score < top_score * 0.55:
            continue

        # 카테고리 점수를 완만하게 학과 점수로 변환
        weight = 2.5 + min(score / 40.0, 3.5)
        add_departments(CATEGORY_TO_DEPARTMENTS.get(cat, []), weight)

    # 5) 보정 규칙: 의약학/보건 분리
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

    if category_scores.get("인공지능·데이터사이언스", 0) > 0:
        for d in DEPT_ALIAS.get("인공지능·데이터사이언스", []):
            dept_scores[d] += 2.0

    if category_scores.get("컴퓨터·소프트웨어", 0) > 0:
        for d in DEPT_ALIAS.get("컴퓨터·소프트웨어", []):
            dept_scores[d] += 1.5

    # 6) 너무 범용적인 학과는 약간 감점
    generic_penalty = {
        "교육학과": 0.5,
        "사회학과": 0.5,
        "경영학과": 0.5,
        "경제학과": 0.5,
    }
    for dept, penalty in generic_penalty.items():
        if dept in dept_scores:
            dept_scores[dept] -= penalty

    # 7) 최종 정렬: 점수 우선, 동점이면 이름순
    ranked = sorted(dept_scores.items(), key=lambda x: (-x[1], x[0]))

    return [dept for dept, _ in ranked[:max_n]]

def major_match_score(target_departments: List[str], university: Dict) -> Tuple[float, List[str]]:
    score = 0.0
    matched = []

    targets = [normalize_major_name(t) for t in target_departments if t]

    for dep in university.get("departments", []):
        dep_name = dep.get("name", "")
        dep_aliases = dep.get("aliases", []) or []
        # 학과명 + aliases 모두 후보로
        candidates = [dep_name] + dep_aliases
        norm_candidates = [normalize_major_name(x) for x in candidates if x]

        for target, raw_target in zip(targets, target_departments):
            best_score_for_dep = 0.0
            for cand, raw_cand in zip(norm_candidates, candidates):
                if not cand:
                    continue
                if target == cand:
                    best_score_for_dep = max(best_score_for_dep, 30)
                elif target in cand or cand in target:
                    best_score_for_dep = max(best_score_for_dep, 22)
                elif (
                    ("인공지능" in raw_target and any(k in raw_cand for k in ["AI", "인공지능", "지능정보", "컴퓨터"]))
                    or ("데이터" in raw_target and any(k in raw_cand for k in ["데이터", "통계", "컴퓨터", "AI"]))
                    or ("소프트웨어" in raw_target and any(k in raw_cand for k in ["소프트웨어", "컴퓨터", "정보통신"]))
                    or ("미디어" in raw_target and any(k in raw_cand for k in ["미디어", "언론", "커뮤니케이션", "콘텐츠"]))
                ):
                    best_score_for_dep = max(best_score_for_dep, 18)

            if best_score_for_dep > 0:
                score += best_score_for_dep
                matched.append(dep_name)

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


def _build_reason(mscore: float, tscore: float, bscore: float,
                  fitcluster_bonus: float, bonus: float, band: Optional[str]) -> str:
    parts = []
    if mscore >= 28:
        parts.append("학과 직접 매칭 강함")
    elif mscore >= 18:
        parts.append("학과 부분 매칭")
    if bscore >= 80:
        parts.append(f"등급대 적정({band})" if band else "등급대 적정")
    elif bscore >= 62:
        parts.append(f"등급대 경계({band})" if band else "등급대 경계")
    if fitcluster_bonus > 0:
        parts.append("계열 적합 클러스터 일치")
    if bonus > 0:
        parts.append("목표대학 가산")
    if tscore >= 60:
        parts.append("인재상 키워드 다수 매칭")
    return " · ".join(parts) if parts else "복합 점수 기준"


def data_quality_diagnosis(signals: Dict) -> Dict:
    """분석 신뢰도를 상태별로 진단."""
    grade_ok = signals.get("overall_grade") is not None
    subjects_ok = any(v is not None for v in (signals.get("subjects") or {}).values())
    tracks_ok = bool(signals.get("detected_tracks"))
    keywords_ok = len(signals.get("top_keywords") or signals.get("topkeywords") or []) >= 5

    score = sum([grade_ok, subjects_ok, tracks_ok, keywords_ok])
    if score >= 3:
        status = "분석 가능"
        color = "#16a34a"
    elif score == 2:
        status = "부분 분석 가능"
        color = "#d97706"
    else:
        status = "분석 신뢰 낮음"
        color = "#dc2626"

    return {
        "status": status,
        "color": color,
        "grade_ok": grade_ok,
        "subjects_ok": subjects_ok,
        "tracks_ok": tracks_ok,
        "keywords_ok": keywords_ok,
    }


def recommend_universities(db: Dict, signals: Dict, target_departments: List[str], topn: int = 6) -> List[Dict]:
    recs = []
    overall_grade = signals.get("overall_grade")
    gscore = grade_fit_score(overall_grade)

    for u in db.get("universities", []):
        mscore, matched = major_match_score(target_departments, u)
        if mscore <= 0:
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

        total = round(
            mscore * 0.40 +
            tscore * 0.18 +
            gscore * 0.12 +
            bscore * 0.22 +
            fitcluster_bonus +
            bonus,
            2
        )

        recs.append({
            "university": u.get("name"),
            "region": u.get("region"),
            "campus": u.get("campus"),
            "fit_score": total,
            "matched_departments": matched[:6],
            "talent_keywords": u.get("talent_keywords", []),
            "notes": u.get("notes", ""),
            "target_bonus": bonus,
            "major_score": round(mscore, 1),
            "talent_score": round(tscore, 1),
            "grade_score": round(gscore, 1),
            "admission_band_score": round(bscore, 1),
            "matched_admission_band": band,
            "matched_department_detail": dep_match,
            "fitcluster_bonus": fitcluster_bonus,
            "support_level": (
                "상향" if bscore >= 90
                else "적정" if bscore >= 78
                else "안정/경계" if bscore >= 62
                else "재고"
            ),
            "recommend_reason": _build_reason(mscore, tscore, bscore, fitcluster_bonus, bonus, band),
        })

    recs.sort(key=lambda x: x["fit_score"], reverse=True)
    return recs[:topn]


def fallback_summary(signals: Dict, target_departments: List[str], recs: List[Dict]) -> str:
    dept_text = ', '.join(target_departments)
    univ_text = ', '.join(r['university'] for r in recs[:6])
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
    st.set_page_config(page_title='학생 HTML 기반 대학 추천기', page_icon='🎓', layout='wide')
    inject_css()
    render_hero()

    with st.sidebar:
        st.header('설정')
        env_help_panel()
        st.markdown('### 비밀번호 해시 생성기')
        gen_pw = st.text_input('새 비밀번호', type='password')
        if st.button('해시 생성', use_container_width=True) and gen_pw:
            st.code(hash_password(gen_pw), language='text')

    if not require_login():
        st.stop()

    try:
        db = load_json_db(JSON_DB_PATH)
    except Exception as e:
        st.error(str(e))
        st.stop()

    top1, top2, top3 = st.columns(3)
    with top1:
        render_metric_card('연결 DB', f"{len(db.get('universities', []))}개 대학", '모든 대학 데이터가 로드되었습니다.')
    with top2:
        render_metric_card('입력 형식', '학생 HTML', '현재 예시 리포트 구조에 맞춘 파서가 동작합니다.')
    with top3:
        render_metric_card('분석 방식', 'JSON + HTML', '구조화된 대학 DB와 학생 리포트를 사용합니다.')

    uploaded_html = st.file_uploader('학생 분석 HTML 업로드', type=['html', 'htm'])

    if uploaded_html is not None:
        html_text = uploaded_html.read().decode('utf-8', errors='ignore')
        signals = extract_example_specific_signals(html_text)

        # ── 패치 6: 추출 정보 검증 / 수동 보정 ──────────────────────────────
        with st.expander("추출 정보 검증 (등급·목표대학 수동 보정)", expanded=True):
            col_v1, col_v2 = st.columns(2)
            with col_v1:
                override_grade = st.number_input(
                    "전체 등급 보정 (추출값: {})".format(signals.get("overall_grade") or "미탐지"),
                    min_value=1.0, max_value=9.0, step=0.1,
                    value=float(signals.get("overall_grade") or 3.0),
                    key="override_grade"
                )
            with col_v2:
                override_target = st.text_input(
                    "목표 대학 보정 (추출값: {})".format(signals.get("target_university") or "미탐지"),
                    value=signals.get("target_university") or "",
                    key="override_target"
                )
            if st.button("보정값으로 재분석", key="btn_reanalyze"):
                st.session_state["grade_override"] = override_grade
                st.session_state["target_override"] = override_target
                st.rerun()

        # 세션 보정값 반영
        if "grade_override" in st.session_state:
            signals["overall_grade"] = st.session_state["grade_override"]
        if "target_override" in st.session_state and st.session_state["target_override"]:
            signals["target_university"] = st.session_state["target_override"]
        # ────────────────────────────────────────────────────────────────────
        category_scores = infer_category_scores(signals)
        target_departments = choose_target_departments(signals, category_scores, max_n=2)
        recs = recommend_universities(db, signals, target_departments, topn=6)
        summary = summarize_with_gemini(signals, target_departments, recs)

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            render_metric_card('추천 학과 수', str(len(target_departments)), '요청 조건에 맞춰 최대 2개까지 제시합니다.')
        with m2:
            render_metric_card('추천 대학 수', str(len(recs)), '추천 결과는 최대 6개 대학까지 노출합니다.')
        with m3:
            render_metric_card('추정 전체 등급', str(signals.get('overall_grade') or '-'), '리포트 서술에서 탐지한 대표 등급 값입니다.')
        with m4:
            render_metric_card('전형 적합도', signals.get('admission_preference') or '미탐지', '예시 HTML의 전형 서술을 우선 반영합니다.')

        # 패치 8: 데이터 품질 진단 배지
        dq = data_quality_diagnosis(signals)
        st.markdown(
            f"<div style='margin:0.5rem 0 1rem 0; padding:0.5rem 1rem; border-radius:10px; "
            f"background:{dq['color']}18; border:1px solid {dq['color']}44; color:{dq['color']}; font-weight:700;'>"
            f"📊 데이터 품질: {dq['status']} &nbsp;|&nbsp; "
            f"등급 {'✅' if dq['grade_ok'] else '❌'} &nbsp;"
            f"과목점수 {'✅' if dq['subjects_ok'] else '❌'} &nbsp;"
            f"트랙탐지 {'✅' if dq['tracks_ok'] else '❌'} &nbsp;"
            f"키워드 {'✅' if dq['keywords_ok'] else '❌'}"
            f"</div>",
            unsafe_allow_html=True
        )

        left, right = st.columns([1.05, 1.35])
        with left:
            render_chip_row('우선 추천 학과', target_departments, dept=True)
            render_chip_row('핵심 키워드', signals.get('top_keywords', [])[:12])
            render_chip_row('학생 신호', [
                signals.get("detected_tracks") or '희망 트랙 미탐지',
                signals.get('target_university') or '목표 대학 미탐지',
                '논술/글쓰기 강점' if signals.get('essay_strength') else '논술 강점 미탐지',
                '수학 위험 신호' if signals.get('math_risk') else '수학 위험 미탐지',
                '인문·미디어 적합' if signals.get('humanities_media_fit') else '계열 적합도 일반 추정'
            ])
            st.markdown(f"<div class='glass-card'><div class='section-title'>요약 분석</div><div class='subtle' style='font-size:0.96rem; line-height:1.7; color:#334155;'>{summary}</div></div>", unsafe_allow_html=True)
            score_items = ''.join([
                f"<div class='score-bar-wrap'><div class='score-bar-label'>{k}</div><div class='score-bar'><div class='score-fill' style='width:{max(0,min(100,int(v)))}%'></div></div></div>"
                for k, v in sorted(category_scores.items(), key=lambda x: x[1], reverse=True)
            ])
            st.markdown(f"<div class='glass-card'><div class='section-title'>계열 적합도</div>{score_items}</div>", unsafe_allow_html=True)

        with right:
            st.markdown("<div class='section-title'>추천 대학</div>", unsafe_allow_html=True)
            if not target_departments:
                st.warning("HTML에서 추천용 학과 후보를 충분히 구성하지 못했습니다. 키워드 사전 또는 최종 결론 반영 규칙을 점검해야 합니다.")
            elif not recs:
                st.warning("추천 학과 후보는 추출되었지만, 현재 DB 학과명과의 매칭이 충분하지 않아 대학 추천이 생성되지 않았습니다.")
            else:
                # 패치 7: 상향/적정/안정 지원군 분리
                groups = {"상향": [], "적정": [], "안정/경계": [], "재고": []}
                for rec in recs:
                    groups[rec.get("support_level", "재고")].append(rec)

                rank = 1
                for level, label_emoji in [
                    ("상향", "🔼 상향 지원"),
                    ("적정", "🎯 적정 지원"),
                    ("안정/경계", "🛡 안정/경계 지원"),
                    ("재고", "⚠️ 재고 필요"),
                ]:
                    grp = groups[level]
                    if not grp:
                        continue
                    st.markdown(
                        f"<div style='font-size:0.88rem; font-weight:700; color:#64748b; "
                        f"margin: 0.8rem 0 0.4rem 0; letter-spacing:0.03em;'>{label_emoji}</div>",
                        unsafe_allow_html=True
                    )
                    for rec in grp:
                        # recommend_reason을 notes에 보조로 표시
                        if rec.get("recommend_reason") and not rec.get("notes"):
                            rec = {**rec, "notes": rec["recommend_reason"]}
                        elif rec.get("recommend_reason"):
                            rec = {**rec, "notes": rec["notes"] + " · " + rec["recommend_reason"]}
                        render_university_card(rec, rank)
                        rank += 1

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
                'top_keywords': signals.get('top_keywords', [])[:20],
                'data_quality': data_quality_diagnosis(signals),
                'rec_support_levels': {r['university']: r.get('support_level') for r in recs},
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
