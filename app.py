# -*- coding: utf-8 -*-
import os
import re
import json
import hmac
import hashlib
import secrets
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple
from difflib import SequenceMatcher

import streamlit as st
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

try:
    from google import genai
except Exception:
    genai = None


GEMINI_MODEL = "gemini-3-flash"
JSON_DB_PATH = "merged_university_db_v2.json"

CATEGORY_KEYWORDS = {
    "인문": ["국어", "문학", "언어", "역사", "철학", "독해", "비평", "서사", "글쓰기", "윤리", "고전"],
    "사회": ["사회", "경제", "경영", "정치", "행정", "미디어", "광고", "홍보", "심리", "소통", "기획", "콘텐츠", "법률", "국제"],
    "자연": ["수학", "과학", "생명", "화학", "물리", "통계", "탐구", "실험", "지구과학", "천문", "환경"],
    "공학": ["공학", "컴퓨터", "소프트웨어", "AI", "전자", "기계", "설계", "코딩", "데이터", "기술", "반도체", "에너지", "로봇"],
    "의학": ["의료", "질병", "해부", "임상", "인체", "약리", "면역", "보건", "신경", "유전", "생명윤리", "수술", "진단"],
    "치의학": ["구강", "치아", "치과학", "치주", "교정"],
    "한의학": ["한방", "동양의학", "본초학", "경혈", "체질", "침구"],
    "수의학": ["동물", "반려동물", "가축", "방역", "수의", "야생동물"],
    "간호": ["케어", "간호", "임상실습", "환자관리", "기초간호"],
    "교육": ["학습", "교수", "수업", "교육공학", "아동", "청소년", "발달", "상담"],
}

DEPT_ALIAS = {
    "미디어": ["미디어커뮤니케이션학", "언론정보학", "콘텐츠디자인"],
    "경영": ["경영학", "경제학", "국제통상학", "빅데이터경영"],
    "심리": ["심리학", "사회학", "상담심리학"],
    "컴퓨터": ["컴퓨터공학", "소프트웨어학", "인공지능학과", "데이터사이언스"],
    "생명": ["생명과학", "생명공학", "생명시스템학", "의생명공학"],
    "의학": ["의예과", "의과학", "임상의학"],
    "치의학": ["치의예과", "구강보건학"],
    "한의학": ["한의예과"],
    "수의학": ["수의예과", "동물자원학"],
    "약학": ["약학과", "제약공학", "바이오의약"],
    "간호": ["간호학과"],
    "보건": ["보건행정학", "임상병리학", "방사선학", "물리치료학"],
    "사범": ["국어교육", "수학교육", "영어교육", "교육학"],
    "환경": ["환경공학", "에너지공학", "기후에너지"],
    "미래차": ["자동차공학", "미래모빌리티", "스마트모빌리티"],
}

SPECIAL_PATTERNS = {
    "grade": [r"([0-9.]+)등급", r"내신\s*([0-9.]+)", r"모평\s*([0-9.]+)등급"],
}

SUBJECT_PATTERNS = {
    "국어": [r"국어[^0-9]{0,20}([1-9](?:\.\d)?)등급", r"국어[^0-9]{0,20}([0-9]{1,3}(?:\.\d+)?)점"],
    "수학": [r"수학[^0-9]{0,20}([1-9](?:\.\d)?)등급", r"수학[^0-9]{0,20}([0-9]{1,3}(?:\.\d+)?)점"],
    "영어": [r"영어[^0-9]{0,20}([1-9](?:\.\d)?)등급", r"영어[^0-9]{0,20}([0-9]{1,3}(?:\.\d+)?)점"],
    "사회": [r"사회[^0-9]{0,20}([1-9](?:\.\d)?)등급", r"사회문화[^0-9]{0,20}([1-9](?:\.\d)?)등급"],
    "과학": [r"과학[^0-9]{0,20}([1-9](?:\.\d)?)등급", r"생명과학[^0-9]{0,20}([1-9](?:\.\d)?)등급"],
}

STOPWORDS = ["학생", "분석", "결과", "응답", "진단", "영역", "전형", "활동", "학과", "대학", "추천", "적합도"]


class StudentProfileSchema(BaseModel):
    overall_grade: Optional[float] = Field(default=None)
    target_university: Optional[str] = Field(default=None)
    preferred_track: Optional[str] = Field(default=None)
    admission_preference: Optional[str] = Field(default=None)
    target_departments: List[str] = Field(default_factory=list)
    subjects: Dict[str, Optional[float]] = Field(default_factory=dict)
    top_keywords: List[str] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    notable_activities: List[str] = Field(default_factory=list)
    is_student_record_heavy: Optional[bool] = Field(default=None)
    essay_strength: Optional[bool] = Field(default=None)
    math_risk: Optional[bool] = Field(default=None)
    humanities_media_fit: Optional[bool] = Field(default=None)
    extraction_confidence: Optional[float] = Field(default=None)


def get_secret_value(key: str, default: Optional[str] = None) -> Optional[str]:
    try:
        if hasattr(st, "secrets") and key in st.secrets:
            value = st.secrets[key]
            return default if value is None else str(value).strip()
    except Exception:
        pass
    value = os.getenv(key)
    return default if value is None else str(value).strip()


def hash_password(password: str, iterations: int = 240000) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algo, iter_str, salt_hex, digest_hex = stored_hash.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iter_str)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(candidate, expected)
    except Exception:
        return False


def require_login() -> None:
    stored_hash = get_secret_value("APP_PASSWORD_HASH", "")
    if not stored_hash:
        st.warning("APP_PASSWORD_HASH가 설정되지 않았습니다. Streamlit Cloud의 Secrets를 확인하십시오.")
        st.stop()

    if st.session_state.get("authenticated"):
        return

    st.markdown('<div class="login-wrap">', unsafe_allow_html=True)
    st.subheader("로그인")
    password = st.text_input("비밀번호", type="password", placeholder="앱 비밀번호 입력")
    submitted = st.button("로그인", use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    if submitted:
        if verify_password(password, stored_hash):
            st.session_state["authenticated"] = True
            st.success("인증되었습니다.")
            st.rerun()
        st.error("비밀번호가 일치하지 않습니다.")
    st.stop()


def load_json_db(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"JSON DB 파일이 없습니다: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_all_departments(db: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for university in db.get("universities", []):
        for department in university.get("departments", []):
            row = dict(department)
            row["university_name"] = university.get("name")
            row["university_region"] = university.get("region")
            row["university_type"] = university.get("type")
            row["university_campus"] = university.get("campus")
            row["talent_keywords"] = university.get("talent_keywords", [])
            row["selectivity_band"] = university.get("selectivity_band")
            row["university_notes"] = university.get("notes", "")
            rows.append(row)
    return rows


def score_against_grade_band(overall_grade: Optional[float], grade_band: Optional[str]) -> float:
    if overall_grade is None or not grade_band:
        return 60.0
    m = re.match(r"([0-9.]+)\s*[-~]\s*([0-9.]+)", str(grade_band))
    if not m:
        return 60.0
    low, high = float(m.group(1)), float(m.group(2))
    if low <= overall_grade <= high:
        return 92.0
    if overall_grade < low:
        gap = low - overall_grade
        return max(55.0, 92.0 - gap * 20)
    gap = overall_grade - high
    return max(20.0, 88.0 - gap * 22)


def score_selectivity_band(selectivity_band: Optional[str], overall_grade: Optional[float]) -> float:
    if overall_grade is None:
        return 55.0
    band_rules = {
        "high": 2.5,
        "mid": 3.5,
        "mid_low": 4.5,
        "regional": 5.5,
    }
    cutoff = band_rules.get(selectivity_band or "", 4.0)
    if overall_grade <= cutoff:
        return 86.0
    gap = overall_grade - cutoff
    return max(15.0, 82.0 - gap * 24)


def department_name_match_score(target_departments: List[str], department_name: str, aliases: List[str]) -> float:
    variants = [department_name] + (aliases or [])
    best = 0.0
    for target in target_departments:
        for variant in variants:
            sim = text_similarity(target, variant)
            if target == variant:
                best = max(best, 100.0)
            elif target in variant or variant in target:
                best = max(best, 90.0)
            elif sim >= 0.85:
                best = max(best, 82.0)
            elif sim >= 0.72:
                best = max(best, 70.0)
            elif any(k in target for k in ["미디어", "광고", "언론"]) and any(k in variant for k in ["미디어", "광고", "언론", "방송"]):
                best = max(best, 68.0)
    return best


def weighted_subject_score(signals: Dict[str, Any], weights: Dict[str, float]) -> float:
    subjects = signals.get("subjects", {}) or {}
    total = 0.0
    weight_sum = 0.0
    for subject, weight in (weights or {}).items():
        if subject == "활동":
            activity_score = 75.0 if signals.get("is_student_record_heavy") else 55.0
            total += activity_score * weight
            weight_sum += weight
            continue
        total += normalize_subject(subjects.get(subject)) * weight
        weight_sum += weight
    if weight_sum == 0:
        return 55.0
    return round(total / weight_sum, 1)


def admission_preference_score(signals: Dict[str, Any], admission_type: str) -> float:
    pref = signals.get("admission_preference")
    if not pref:
        return 55.0
    if pref == admission_type:
        return 92.0
    if pref == "학생부종합" and admission_type == "학생부교과":
        return 62.0
    if pref == "학생부교과" and admission_type == "학생부종합":
        return 62.0
    return 50.0


def recommend_programs(db: Dict[str, Any], signals: Dict[str, Any], target_departments: List[str], top_n: int = 6) -> List[Dict[str, Any]]:
    if not target_departments:
        return []

    rows = get_all_departments(db)
    recs: List[Dict[str, Any]] = []
    confidence_weight = evidence_weight(signals)
    overall_grade = signals.get("overall_grade")

    for row in rows:
        dept_match = department_name_match_score(target_departments, row.get("name", ""), row.get("aliases", []))
        if dept_match < 68:
            continue

        for admission in row.get("admissions", []):
            subject_score = weighted_subject_score(signals, admission.get("subject_weights", {}))
            band_score = score_against_grade_band(overall_grade, admission.get("min_grade_band"))
            selectivity_score = score_selectivity_band(row.get("selectivity_band"), overall_grade)
            talent_score = keyword_fit_score(signals, row.get("talent_keywords", []))
            pref_score = admission_preference_score(signals, admission.get("type", ""))
            bonus = target_bonus(row.get("university_name", ""), signals)

            total = (
                dept_match * 0.28
                + subject_score * 0.22
                + band_score * 0.18
                + selectivity_score * 0.12
                + talent_score * 0.10
                + pref_score * 0.10
                + bonus
            ) * confidence_weight
            total = round(total, 2)

            recs.append({
                "university": row.get("university_name"),
                "department": row.get("name"),
                "admission_type": admission.get("type"),
                "track_name": admission.get("track_name"),
                "region": row.get("university_region"),
                "campus": row.get("campus") or row.get("university_campus"),
                "fit_score": total,
                "department_match": round(dept_match, 1),
                "subject_score": round(subject_score, 1),
                "grade_band_score": round(band_score, 1),
                "selectivity_score": round(selectivity_score, 1),
                "talent_score": round(talent_score, 1),
                "preference_score": round(pref_score, 1),
                "recommendation_confidence": recommendation_confidence(signals, [row.get("name", "")]),
                "target_bonus": bonus,
                "subject_weights": admission.get("subject_weights", {}),
                "grade_band": admission.get("min_grade_band"),
                "csat_minimum": admission.get("csat_minimum"),
                "aliases": row.get("aliases", []),
                "fit_cluster": row.get("fit_cluster"),
                "evidence_level": admission.get("evidence_level") or row.get("evidence_level"),
                "notes": row.get("university_notes", ""),
                "selectivity_band": row.get("selectivity_band"),
            })

    recs.sort(key=lambda x: (x["fit_score"], x["department_match"], x["subject_score"]), reverse=True)

    deduped: List[Dict[str, Any]] = []
    seen = set()
    for rec in recs:
        key = (rec["university"], rec["department"], rec["admission_type"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(rec)
        if len(deduped) >= top_n:
            break
    return deduped


def summarize_program_recommendations(programs: List[Dict[str, Any]]) -> List[str]:
    return [f"{x['university']} · {x['department']} · {x['admission_type']}" for x in programs]


def strip_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def pick_first_float(text: str, patterns: List[str]) -> Optional[float]:
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                return float(match.group(1))
            except Exception:
                continue
    return None


def collect_all_floats(text: str, patterns: List[str]) -> List[float]:
    values: List[float] = []
    for pattern in patterns:
        for match in re.findall(pattern, text):
            try:
                values.append(float(match[0] if isinstance(match, tuple) else match))
            except Exception:
                continue
    return values


def infer_subjects_from_text(text: str) -> Dict[str, Optional[float]]:
    subject_scores: Dict[str, Optional[float]] = {}
    for subject, patterns in SUBJECT_PATTERNS.items():
        subject_scores[subject] = pick_first_float(text, patterns)
    return subject_scores


def safe_json_loads(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    text = text.strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def extract_structured_text(html_text: str) -> str:
    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    blocks: List[str] = []
    for node in soup.find_all(["title", "h1", "h2", "h3", "h4", "th", "td", "dt", "dd", "li", "strong", "b", "p", "span", "div"]):
        txt = strip_text(node.get_text(" ", strip=True))
        if txt and len(txt) >= 2:
            blocks.append(txt)

    deduped: List[str] = []
    seen = set()
    for txt in blocks:
        key = re.sub(r"\s+", " ", txt).strip()
        if key and key not in seen:
            seen.add(key)
            deduped.append(key)

    focus_terms = ["등급", "내신", "희망", "학과", "학부", "전공", "진로", "교과", "종합", "논술", "정시", "세특", "수상", "활동", "강점", "약점", "추천"]
    focused = [x for x in deduped if any(t in x for t in focus_terms)]
    combined = focused + [x for x in deduped if x not in focused]
    return "\n".join(combined[:1200])


def regex_extract_signals(text: str) -> Dict[str, Any]:
    lines = [line.strip() for line in re.split(r"[\n.!?]+", text) if line.strip()]
    top_keywords = Counter(re.findall(r"[가-힣A-Za-z]{2,20}", text))
    for stopword in STOPWORDS:
        top_keywords.pop(stopword, None)

    evidence_flags = {
        "grade": False,
        "track": False,
        "university": False,
        "department": False,
        "activities": False,
    }

    overall_grade = None
    grade_candidates = collect_all_floats(text, SPECIAL_PATTERNS["grade"])
    reasonable = [g for g in grade_candidates if 1 <= g <= 9]
    if reasonable:
        overall_grade = sorted(reasonable)[0]
        evidence_flags["grade"] = True

    preferred_track = None
    explicit_track_patterns = [
        r"희망\s*학과\s*[:：]?\s*([가-힣A-Za-z0-9\s]{2,30})",
        r"관심\s*학과\s*[:：]?\s*([가-힣A-Za-z0-9\s]{2,30})",
        r"진로\s*희망\s*[:：]?\s*([가-힣A-Za-z0-9\s]{2,30})",
        r"희망\s*계열\s*[:：]?\s*([가-힣A-Za-z0-9\s]{2,30})",
    ]
    for pattern in explicit_track_patterns:
        match = re.search(pattern, text)
        if match:
            preferred_track = strip_text(match.group(1))
            evidence_flags["track"] = True
            break

    target_university = None
    for pattern in [
        r"목표\s*대학\s*[:：]?\s*([가-힣A-Za-z0-9\s]{2,30})",
        r"희망\s*대학\s*[:：]?\s*([가-힣A-Za-z0-9\s]{2,30})",
        r"1지망\s*[:：]?\s*([가-힣A-Za-z0-9\s]{2,30})",
    ]:
        match = re.search(pattern, text)
        if match:
            target_university = strip_text(match.group(1))
            evidence_flags["university"] = True
            break

    explicit_department_patterns = [
        r"희망\s*학과\s*[:：]?\s*([가-힣A-Za-z0-9\s,\/]{2,50})",
        r"관심\s*학과\s*[:：]?\s*([가-힣A-Za-z0-9\s,\/]{2,50})",
        r"지원\s*학과\s*[:：]?\s*([가-힣A-Za-z0-9\s,\/]{2,50})",
    ]
    target_departments: List[str] = []
    for pattern in explicit_department_patterns:
        match = re.search(pattern, text)
        if match:
            raw = strip_text(match.group(1))
            candidates = re.split(r"[,/·]|\s{2,}", raw)
            target_departments.extend([strip_text(x) for x in candidates if strip_text(x)])
            evidence_flags["department"] = True
            break

    if not target_departments and preferred_track:
        for seed, departments in DEPT_ALIAS.items():
            if seed in preferred_track:
                target_departments.extend(departments[:2])
        if target_departments:
            evidence_flags["department"] = True

    target_departments = list(dict.fromkeys(target_departments))[:2]

    strengths: List[str] = []
    risks: List[str] = []
    notable_activities = [line for line in lines if any(k in line for k in ["동아리", "대회", "탐구", "활동", "프로젝트", "연구"])][:8]
    if notable_activities:
        evidence_flags["activities"] = True

    if "글쓰기" in text or "논술" in text:
        strengths.append("글쓰기/논술")
    if any(keyword in text for keyword in ["방송반", "생기부", "대회", "기획", "연구", "프로젝트"]):
        strengths.append("비교과 활동")
    if any(keyword in text for keyword in ["수학 회피", "수학 4등급", "모평 5등급", "수학은 진짜 못 하겠어요"]):
        risks.append("수학 약점")

    confidence = round(sum(1 for v in evidence_flags.values() if v) / len(evidence_flags), 2)

    return {
        "raw_text": text,
        "overall_grade": overall_grade,
        "subjects": infer_subjects_from_text(text),
        "top_keywords": [word for word, _ in top_keywords.most_common(40)],
        "preferred_track": preferred_track,
        "target_university": target_university,
        "target_departments": target_departments,
        "strengths": strengths,
        "risks": risks,
        "notable_activities": notable_activities,
        "is_student_record_heavy": any(k in text for k in ["방송반", "글쓰기 대회", "생기부", "수행평가"]),
        "admission_preference": "학생부종합" if ("학생부종합전형" in text or "학종" in text) else None,
        "essay_strength": ("논술" in text and "자신" in text) or ("글쓰기" in text),
        "math_risk": "수학 약점" in risks,
        "humanities_media_fit": any(k in text for k in ["인문계", "미디어 진로", "콘텐츠", "광고 기획"]),
        "line_samples": lines[:50],
        "evidence_flags": evidence_flags,
        "extraction_confidence": confidence,
    }


def extract_signals_with_gemini(structured_text: str) -> Optional[Dict[str, Any]]:
    api_key = get_secret_value("GEMINI_API_KEY")
    if not api_key or genai is None:
        return None

    prompt = f"""다음은 학생 분석 HTML에서 추출한 구조화 텍스트다.
학생의 학업 성적, 희망 학과/계열, 목표 대학, 전형 성향, 강점/위험요인을 JSON으로만 추출하라.
추측하지 말고 텍스트 근거가 있는 정보만 채워라.
subjects 값은 과목명별 등급 또는 점수 숫자만 넣어라.
output schema keys:
overall_grade, target_university, preferred_track, admission_preference, target_departments, subjects, top_keywords, strengths, risks, notable_activities, is_student_record_heavy, essay_strength, math_risk, humanities_media_fit

[TEXT]
{structured_text[:18000]}
"""
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": StudentProfileSchema,
                "temperature": 0.1,
            },
        )
        return safe_json_loads(getattr(response, "text", "") or "")
    except Exception:
        return None


def merge_signals(base: Dict[str, Any], extracted: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not extracted:
        return base

    merged = dict(base)
    for key, value in extracted.items():
        if value in (None, "", [], {}):
            continue
        if key in ["top_keywords", "target_departments", "strengths", "risks", "notable_activities"]:
            previous = merged.get(key, []) or []
            merged[key] = list(dict.fromkeys(previous + value))
        elif key == "subjects":
            subjects = dict(merged.get("subjects", {}))
            for subject, score in value.items():
                if score is not None:
                    subjects[subject] = score
            merged["subjects"] = subjects
        else:
            merged[key] = value

    merged["essay_strength"] = bool(
        merged.get("essay_strength") or any(token in item for item in merged.get("strengths", []) for token in ["글쓰기", "논술"])
    )
    merged["math_risk"] = bool(
        merged.get("math_risk") or any("수학" in item for item in merged.get("risks", []))
    )
    merged["humanities_media_fit"] = bool(
        merged.get("humanities_media_fit")
        or any(token in " ".join(merged.get("target_departments", [])) for token in ["미디어", "광고", "언론"])
    )
    return merged


def extract_student_signals(html_text: str) -> Dict[str, Any]:
    structured_text = extract_structured_text(html_text)
    regex_signals = regex_extract_signals(structured_text)
    ai_signals = extract_signals_with_gemini(structured_text)
    signals = merge_signals(regex_signals, ai_signals)
    signals["raw_text"] = structured_text
    signals["line_samples"] = [line for line in structured_text.splitlines() if line.strip()][:50]
    signals["parser_mode"] = "gemini+regex" if ai_signals else "regex-only"
    return signals



def text_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def classify_grade_band(overall_grade: Optional[float]) -> str:
    if overall_grade is None:
        return "unknown"
    if overall_grade <= 1.8:
        return "high"
    if overall_grade <= 2.8:
        return "upper_mid"
    if overall_grade <= 3.8:
        return "mid"
    return "low"


def evidence_weight(signals: Dict[str, Any]) -> float:
    confidence = signals.get("extraction_confidence")
    if confidence is None:
        return 0.7
    return max(0.4, min(1.0, float(confidence)))


def department_candidates_from_signals(signals: Dict[str, Any], max_n: int = 2) -> List[Dict[str, Any]]:
    candidates: Dict[str, Dict[str, Any]] = {}

    explicit_departments = signals.get("target_departments", []) or []
    for dept in explicit_departments:
        dept = strip_text(dept)
        if dept:
            candidates[dept] = {"name": dept, "score": 1.0, "source": "explicit"}

    preferred_track = strip_text(signals.get("preferred_track") or "")
    if preferred_track:
        for seed, departments in DEPT_ALIAS.items():
            if seed in preferred_track or preferred_track in seed:
                for idx, dept in enumerate(departments[:2]):
                    candidates.setdefault(dept, {"name": dept, "score": 0.85 - idx * 0.05, "source": "track-alias"})

    top_keywords = signals.get("top_keywords", [])[:15]
    keyword_text = " ".join(top_keywords)
    for seed, departments in DEPT_ALIAS.items():
        if seed in keyword_text:
            for idx, dept in enumerate(departments[:1]):
                current = candidates.get(dept)
                if not current or current["score"] < 0.6:
                    candidates[dept] = {"name": dept, "score": 0.6 - idx * 0.05, "source": "keyword"}

    ranked = sorted(candidates.values(), key=lambda x: x["score"], reverse=True)
    return ranked[:max_n]


def academic_strength_score(signals: Dict[str, Any], dept_name: str) -> float:
    subjects = signals.get("subjects", {}) or {}
    dept = dept_name
    score = 55.0

    if any(k in dept for k in ["컴퓨터", "전자", "공학", "통계"]):
        score = normalize_subject(subjects.get("수학")) * 0.55 + normalize_subject(subjects.get("과학")) * 0.25 + normalize_subject(subjects.get("영어")) * 0.2
    elif any(k in dept for k in ["생명", "의", "약", "간호", "보건"]):
        score = normalize_subject(subjects.get("과학")) * 0.45 + normalize_subject(subjects.get("수학")) * 0.2 + normalize_subject(subjects.get("영어")) * 0.2 + normalize_subject(subjects.get("국어")) * 0.15
    elif any(k in dept for k in ["미디어", "광고", "언론", "경영", "심리", "사회", "행정"]):
        score = normalize_subject(subjects.get("국어")) * 0.35 + normalize_subject(subjects.get("영어")) * 0.25 + normalize_subject(subjects.get("사회")) * 0.25 + normalize_subject(subjects.get("수학")) * 0.15
    elif any(k in dept for k in ["교육", "국문", "영문", "철학", "역사"]):
        score = normalize_subject(subjects.get("국어")) * 0.45 + normalize_subject(subjects.get("영어")) * 0.25 + normalize_subject(subjects.get("사회")) * 0.2 + normalize_subject(subjects.get("수학")) * 0.1

    if signals.get("math_risk") and any(k in dept for k in ["컴퓨터", "전자", "공학", "통계"]):
        score -= 12
    if signals.get("essay_strength") and any(k in dept for k in ["미디어", "광고", "언론", "국문", "영문", "교육"]):
        score += 8

    return round(max(0.0, min(100.0, score)), 1)


def university_selectivity_penalty(university_name: str, overall_grade: Optional[float]) -> float:
    if overall_grade is None:
        return 0.0

    high_selective = ["서울대학교", "연세대학교", "고려대학교", "성균관대학교", "한양대학교", "중앙대학교", "경희대학교", "이화여자대학교", "한국외국어대학교", "서강대학교"]
    mid_selective = ["건국대학교", "동국대학교", "홍익대학교", "숙명여자대학교", "국민대학교", "숭실대학교", "서울시립대학교", "아주대학교", "인하대학교"]

    if university_name in high_selective:
        if overall_grade > 4.0:
            return -22.0
        if overall_grade > 3.3:
            return -15.0
        if overall_grade > 2.7:
            return -8.0
    if university_name in mid_selective:
        if overall_grade > 4.5:
            return -14.0
        if overall_grade > 3.8:
            return -8.0
    return 0.0


def recommendation_confidence(signals: Dict[str, Any], matched_departments: List[str]) -> float:
    base = evidence_weight(signals) * 100
    if matched_departments:
        base += 10
    if signals.get("overall_grade") is not None:
        base += 5
    return round(max(0.0, min(100.0, base)), 1)

def normalize_subject(value: Optional[float]) -> float:
    if value is None:
        return 50.0
    if value <= 9:
        return max(0.0, 100 - (value - 1) * 12.5)
    return max(0.0, min(100.0, value))


def infer_category_scores(signals: Dict[str, Any]) -> Dict[str, float]:
    text = signals["raw_text"]
    scores = {category: 0.0 for category in CATEGORY_KEYWORDS}

    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            scores[category] += text.count(keyword) * 2.5

    subjects = signals.get("subjects", {})
    scores["인문"] += normalize_subject(subjects.get("국어")) * 0.30
    scores["사회"] += normalize_subject(subjects.get("사회")) * 0.35
    scores["사회"] += normalize_subject(subjects.get("영어")) * 0.15
    scores["자연"] += normalize_subject(subjects.get("과학")) * 0.25
    scores["공학"] += normalize_subject(subjects.get("수학")) * 0.30
    scores["공학"] += normalize_subject(subjects.get("과학")) * 0.10

    if signals.get("humanities_media_fit"):
        scores["인문"] += 25
        scores["사회"] += 35
    if signals.get("math_risk"):
        scores["공학"] -= 20
        scores["자연"] -= 10
    if signals.get("essay_strength"):
        scores["인문"] += 15
        scores["사회"] += 10
    return scores


def choose_target_departments(signals: Dict[str, Any], category_scores: Dict[str, float], max_n: int = 2) -> List[str]:
    dept_candidates = department_candidates_from_signals(signals, max_n=max_n)
    if dept_candidates:
        return [item["name"] for item in dept_candidates][:max_n]

    if evidence_weight(signals) < 0.55:
        return []

    sorted_categories = sorted(category_scores.items(), key=lambda item: item[1], reverse=True)
    mapping = {
        "인문": ["국어국문학", "영어영문학"],
        "사회": ["경영학", "심리학"],
        "자연": ["생명과학", "통계학"],
        "공학": ["컴퓨터공학", "전자공학"],
        "의학": ["의예과", "의과학"],
        "치의학": ["치의예과", "구강보건학"],
        "한의학": ["한의예과"],
        "수의학": ["수의예과", "동물자원학"],
        "간호": ["간호학과"],
        "교육": ["교육학", "영어교육"],
    }

    recommendations: List[str] = []
    for category, score in sorted_categories:
        if score < 35:
            continue
        for department in mapping.get(category, []):
            if department not in recommendations:
                recommendations.append(department)
            if len(recommendations) >= max_n:
                return recommendations
    return recommendations[:max_n]



def major_match_score(target_departments: List[str], major_categories: Dict[str, List[str]]) -> Tuple[float, List[str]]:
    majors_flat: List[str] = []
    for values in major_categories.values():
        majors_flat.extend(values)

    best_scores: Dict[str, float] = {}
    for target in target_departments:
        for major in majors_flat:
            sim = text_similarity(target, major)
            score = 0.0
            if target == major:
                score = 34.0
            elif target in major or major in target:
                score = 26.0
            elif sim >= 0.82:
                score = 22.0
            elif sim >= 0.68:
                score = 16.0
            elif any(token in target for token in ["미디어", "광고", "언론"]) and any(token in major for token in ["미디어", "광고", "언론", "방송"]):
                score = 14.0
            if score > 0:
                best_scores[major] = max(best_scores.get(major, 0.0), score)

    matched = sorted(best_scores.keys(), key=lambda x: best_scores[x], reverse=True)
    total_score = round(sum(best_scores.values()), 1)
    return total_score, matched[:6]



def keyword_fit_score(signals: Dict[str, Any], talent_keywords: List[str]) -> float:
    text_blob = signals["raw_text"]
    keywords = talent_keywords or []
    if not keywords:
        return 45.0

    hits = sum(1 for keyword in keywords if keyword and keyword in text_blob)
    coverage = hits / max(1, len(keywords))
    base = 40 + coverage * 35

    if signals.get("admission_preference") == "학생부종합" and any(k in keywords for k in ["창의", "소통", "실천", "리더십", "융합"]):
        base += 6
    if signals.get("is_student_record_heavy") and any(k in keywords for k in ["표현", "실천", "창의", "탐구"]):
        base += 5
    return round(max(0.0, min(100.0, base)), 1)



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


def target_bonus(university_name: str, signals: Dict[str, Any]) -> float:
    target_university = signals.get("target_university")
    if target_university and target_university in university_name:
        return 12.0
    return 0.0


def recommend_universities(db: Dict[str, Any], signals: Dict[str, Any], target_departments: List[str], top_n: int = 6) -> List[Dict[str, Any]]:
    recommendations: List[Dict[str, Any]] = []
    overall_grade = signals.get("overall_grade")
    gscore = grade_fit_score(overall_grade)
    confidence_weight = evidence_weight(signals)

    if not target_departments:
        return []

    for university in db.get("universities", []):
        major_score, matched = major_match_score(target_departments, university.get("major_categories", {}))
        if major_score < 14:
            continue

        dept_strength = max(academic_strength_score(signals, dept) for dept in target_departments)
        talent_score = keyword_fit_score(signals, university.get("talent_keywords", []))
        bonus = target_bonus(university["name"], signals)
        selectivity = university_selectivity_penalty(university["name"], overall_grade)
        total = (
            major_score * 0.42
            + talent_score * 0.18
            + gscore * 0.16
            + dept_strength * 0.18
            + bonus
            + selectivity
        ) * confidence_weight
        total = round(total, 2)

        recommendations.append(
            {
                "university": university["name"],
                "region": university.get("region"),
                "campus": university.get("campus"),
                "fit_score": total,
                "matched_departments": matched[:6],
                "talent_keywords": university.get("talent_keywords", []),
                "notes": university.get("notes", ""),
                "target_bonus": bonus,
                "major_score": round(major_score, 1),
                "talent_score": round(talent_score, 1),
                "grade_score": round(gscore, 1),
                "academic_score": round(dept_strength, 1),
                "selectivity_adjustment": round(selectivity, 1),
                "recommendation_confidence": recommendation_confidence(signals, matched),
            }
        )

    recommendations.sort(key=lambda item: (item["fit_score"], item["recommendation_confidence"], item["major_score"]), reverse=True)
    return recommendations[:top_n]



def fallback_summary(signals: Dict[str, Any], target_departments: List[str], recommendations: List[Dict[str, Any]]) -> str:
    department_text = ", ".join(target_departments) or "미탐지"
    university_text = ", ".join(item["university"] for item in recommendations[:6])
    parts = [f"우선 추천 학과는 {department_text}입니다."]

    if signals.get("admission_preference"):
        parts.append(f"전형 성향은 {signals['admission_preference']} 중심으로 해석됩니다.")
    if signals.get("math_risk"):
        parts.append("수학 약점 신호가 있어 공학계열보다 인문·사회계열 우선순위가 높습니다.")
    if signals.get("target_university"):
        parts.append(f"HTML 내 목표 대학 신호는 {signals['target_university']}입니다.")
    if university_text:
        parts.append(f"추천 대학은 {university_text}입니다.")
    return " ".join(parts)


def summarize_with_gemini(signals: Dict[str, Any], target_departments: List[str], recommendations: List[Dict[str, Any]]) -> str:
    api_key = get_secret_value("GEMINI_API_KEY")
    if not api_key or genai is None:
        return fallback_summary(signals, target_departments, recommendations)

    try:
        client = genai.Client(api_key=api_key)
        prompt = (
            f"학생 핵심 키워드: {signals.get('top_keywords', [])[:15]}\n"
            f"전체 등급 추정: {signals.get('overall_grade')}\n"
            f"목표 대학 신호: {signals.get('target_university')}\n"
            f"추천 학과: {target_departments}\n"
            f"추천 대학: {[item['university'] for item in recommendations]}\n"
            "한국어 plain text로 5문장 이내 요약. 과장 금지. 확실한 것만 서술."
        )
        response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        if getattr(response, "text", None):
            return response.text.strip()
    except Exception:
        pass
    return fallback_summary(signals, target_departments, recommendations)


def inject_css() -> None:
    st.markdown(
        """
        <style>
        .stApp { background: linear-gradient(180deg, #f5f7fb 0%, #edf2f7 100%); }
        .hero-box { padding: 1.4rem 1.6rem; border-radius: 22px; background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 55%, #2563eb 100%); color: white; box-shadow: 0 20px 40px rgba(37, 99, 235, 0.18); margin-bottom: 1rem; }
        .hero-title { font-size: 1.75rem; font-weight: 800; margin-bottom: 0.35rem; }
        .hero-sub { font-size: 0.98rem; opacity: 0.9; }
        .glass-card { background: rgba(255,255,255,0.82); border: 1px solid rgba(148,163,184,0.18); border-radius: 18px; padding: 1rem 1.1rem; box-shadow: 0 12px 30px rgba(15,23,42,0.06); }
        .metric-card { background: white; border-radius: 18px; padding: 1rem 1rem 0.9rem 1rem; border: 1px solid #e5e7eb; box-shadow: 0 10px 20px rgba(15,23,42,0.05); min-height: 120px; }
        .metric-label { color: #64748b; font-size: 0.82rem; margin-bottom: 0.4rem; }
        .metric-value { font-size: 1.4rem; font-weight: 800; color: #0f172a; margin-bottom: 0.35rem; }
        .metric-desc { color: #475569; font-size: 0.9rem; line-height: 1.4; }
        .section-title { font-size: 1.1rem; font-weight: 800; color: #0f172a; margin: 0.2rem 0 0.8rem 0; }
        .dept-chip { display: inline-block; background: #dbeafe; color: #1d4ed8; border: 1px solid #bfdbfe; padding: 0.45rem 0.7rem; border-radius: 999px; margin: 0.2rem 0.35rem 0.2rem 0; font-weight: 700; font-size: 0.9rem; }
        .tag-chip { display: inline-block; background: #f8fafc; color: #334155; border: 1px solid #e2e8f0; padding: 0.35rem 0.6rem; border-radius: 999px; margin: 0.18rem 0.32rem 0.18rem 0; font-size: 0.84rem; }
        .recommend-card { background: white; border-radius: 22px; padding: 1.15rem 1.2rem; border: 1px solid #e2e8f0; box-shadow: 0 18px 32px rgba(15,23,42,0.06); margin-bottom: 1rem; }
        .recommend-head { display: flex; justify-content: space-between; align-items: center; gap: 1rem; margin-bottom: 0.75rem; }
        .recommend-title { font-size: 1.12rem; font-weight: 800; color: #0f172a; }
        .score-pill { background: linear-gradient(135deg, #1d4ed8, #2563eb); color: white; padding: 0.45rem 0.8rem; border-radius: 999px; font-weight: 800; font-size: 0.9rem; white-space: nowrap; }
        .subtle { color: #64748b; font-size: 0.9rem; }
        .score-bar-wrap { margin-top: 0.4rem; margin-bottom: 0.55rem; }
        .score-bar-label { font-size: 0.82rem; color: #475569; margin-bottom: 0.2rem; }
        .score-bar { width: 100%; height: 10px; background: #e2e8f0; border-radius: 999px; overflow: hidden; }
        .score-fill { height: 10px; border-radius: 999px; background: linear-gradient(90deg, #60a5fa, #1d4ed8); }
        .login-wrap { max-width: 420px; margin: 2rem auto 0 auto; padding: 1rem; background: rgba(255,255,255,0.82); border-radius: 20px; border: 1px solid rgba(148,163,184,0.18); box-shadow: 0 12px 30px rgba(15,23,42,0.08); }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hero() -> None:
    st.markdown(
        """
        <div class='hero-box'>
          <div class='hero-title'>학생 HTML 기반 대학 추천 대시보드</div>
          <div class='hero-sub'>AI 구조화 추출과 규칙 기반 보정을 함께 사용해 학생의 성적, 희망 학과, 목표 대학 신호를 분석합니다.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_metric_card(label: str, value: str, desc: str) -> None:
    st.markdown(
        f"""
        <div class='metric-card'>
          <div class='metric-label'>{label}</div>
          <div class='metric-value'>{value}</div>
          <div class='metric-desc'>{desc}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_chip_row(title: str, items: List[str], dept: bool = False) -> None:
    chip_class = "dept-chip" if dept else "tag-chip"
    chips = "".join([f'<span class="{chip_class}">{item}</span>' for item in items if item])
    empty = '<div class="subtle">표시할 항목이 없습니다.</div>'
    st.markdown(
        f"<div class='glass-card'><div class='section-title'>{title}</div>{chips if chips else empty}</div>",
        unsafe_allow_html=True,
    )


def render_university_card(rec: Dict[str, Any], rank: int) -> None:
    fit_pct = max(0, min(100, int(rec["fit_score"])))
    major_pct = max(0, min(100, int(rec["major_score"] * 2.5)))
    talent_pct = max(0, min(100, int(rec["talent_score"])))
    grade_pct = max(0, min(100, int(rec["grade_score"])))
    matched = "".join([f'<span class="tag-chip">{x}</span>' for x in rec["matched_departments"]])
    talents = "".join([f'<span class="tag-chip">{x}</span>' for x in rec["talent_keywords"]])
    bonus_text = f"목표대학 가중치 +{rec['target_bonus']}" if rec.get("target_bonus") else "목표대학 가중치 없음"

    st.markdown(
        f"""
        <div class='recommend-card'>
          <div class='recommend-head'>
            <div>
              <div class='subtle'>추천 {rank}</div>
              <div class='recommend-title'>{rec['university']}</div>
              <div class='subtle'>{rec['region']} · {rec['campus'] if rec['campus'] else '단일 캠퍼스/미표기'}</div>
            </div>
            <div class='score-pill'>적합도 {rec['fit_score']}</div>
          </div>
          <div class='score-bar-wrap'><div class='score-bar-label'>총 적합도</div><div class='score-bar'><div class='score-fill' style='width:{fit_pct}%'></div></div></div>
          <div class='score-bar-wrap'><div class='score-bar-label'>학과 일치도</div><div class='score-bar'><div class='score-fill' style='width:{major_pct}%'></div></div></div>
          <div class='score-bar-wrap'><div class='score-bar-label'>인재상 적합도</div><div class='score-bar'><div class='score-fill' style='width:{talent_pct}%'></div></div></div>
          <div class='score-bar-wrap'><div class='score-bar-label'>기본 성적 적합도</div><div class='score-bar'><div class='score-fill' style='width:{grade_pct}%'></div></div></div>
          <div class='subtle' style='margin-top:0.25rem;'>추천 신뢰도 {rec.get('recommendation_confidence', '-')}</div>
          <div class='section-title'>일치 학과군</div>
          <div>{matched if matched else '<span class="subtle">없음</span>'}</div>
          <div class='section-title' style='margin-top:0.8rem;'>인재상 키워드</div>
          <div>{talents if talents else '<span class="subtle">없음</span>'}</div>
          <div class='subtle' style='margin-top:0.9rem;'>{bonus_text}</div>
          <div class='subtle' style='margin-top:0.3rem;'>선택도 보정 {rec.get('selectivity_adjustment', 0)}</div>
          <div class='subtle' style='margin-top:0.3rem;'>{rec.get('notes', '')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def env_help_panel() -> None:
    st.markdown("### .env 설정 안내")
    st.code(
        """GEMINI_API_KEY=여기에_API_KEY
APP_PASSWORD_HASH=pbkdf2_sha256$240000$<salt_hex>$<hash_hex>""",
        language="bash",
    )
    st.write("비밀번호 해시는 앱 내부 도구 또는 아래 스크립트로 생성할 수 있습니다.")
    st.code(
        """python -c "import secrets,hashlib; p='your_password'; s=secrets.token_bytes(16); i=240000; d=hashlib.pbkdf2_hmac('sha256', p.encode(), s, i); print(f'pbkdf2_sha256${i}${s.hex()}${d.hex()}')""",
        language="bash",
    )


def main() -> None:
    st.set_page_config(page_title="학생 HTML 기반 대학 추천기", page_icon="🎓", layout="wide")
    inject_css()
    render_hero()

    with st.sidebar:
        st.header("설정")
        env_help_panel()
        st.markdown("### 비밀번호 해시 생성기")
        generated_password = st.text_input("새 비밀번호", type="password")
        if st.button("해시 생성", use_container_width=True) and generated_password:
            st.code(hash_password(generated_password), language="text")

    require_login()

    try:
        db = load_json_db(JSON_DB_PATH)
    except Exception as exc:
        st.error(str(exc))
        st.stop()

    top1, top2, top3 = st.columns(3)
    with top1:
        render_metric_card("연결 DB", f"{len(db.get('universities', []))}개 대학", "서울·경기권 대학 데이터가 로드되었습니다.")
    with top2:
        render_metric_card("입력 형식", "학생 HTML", "AI 추출 + 규칙 기반 보정 파서가 함께 동작합니다.")
    with top3:
        render_metric_card("분석 방식", "JSON + HTML", "대학 DB와 학생 HTML 리포트를 결합해 적합도를 계산합니다.")

    uploaded_html = st.file_uploader("학생 분석 HTML 업로드", type=["html", "htm"])
    if uploaded_html is None:
        return

    html_text = uploaded_html.read().decode("utf-8", errors="ignore")
    signals = extract_student_signals(html_text)
    category_scores = infer_category_scores(signals)
    target_departments = choose_target_departments(signals, category_scores, max_n=2)
    recommendations = recommend_universities(db, signals, target_departments, top_n=6)
    summary = summarize_with_gemini(signals, target_departments, recommendations)

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        render_metric_card("추천 학과 수", str(len(target_departments)), "AI와 규칙 추출 결과를 합쳐 최대 2개까지 제시합니다.")
    with m2:
        render_metric_card("추천 대학 수", str(len(recommendations)), "근거가 부족하면 추천 수가 줄어들 수 있으며, 최대 6개 대학까지만 노출합니다.")
    with m3:
        render_metric_card("추정 전체 등급", str(signals.get("overall_grade") or "-"), "HTML 서술에서 탐지한 대표 등급 값입니다.")
    with m4:
        render_metric_card("파싱 완전성", str(signals.get("extraction_confidence") or "-"), "핵심 필드가 얼마나 안정적으로 추출되었는지 보여 줍니다.")

    left, right = st.columns([1.05, 1.35])
    with left:
        render_chip_row("우선 추천 학과", target_departments, dept=True)
        render_chip_row("핵심 키워드", signals.get("top_keywords", [])[:12])
        render_chip_row(
            "학생 신호",
            [
                signals.get("preferred_track") or "희망 트랙 미탐지",
                signals.get("target_university") or "목표 대학 미탐지",
                "논술/글쓰기 강점" if signals.get("essay_strength") else "논술 강점 미탐지",
                "수학 위험 신호" if signals.get("math_risk") else "수학 위험 미탐지",
                "인문·미디어 적합" if signals.get("humanities_media_fit") else "계열 적합도 일반 추정",
            ],
        )

        if signals.get("strengths"):
            render_chip_row("강점 신호", signals.get("strengths", []))
        if signals.get("risks"):
            render_chip_row("위험 신호", signals.get("risks", []))

        st.markdown(
            f"<div class='glass-card'><div class='section-title'>요약 분석</div><div class='subtle' style='font-size:0.96rem; line-height:1.7; color:#334155;'>{summary}</div></div>",
            unsafe_allow_html=True,
        )

        score_items = "".join(
            [
                f"<div class='score-bar-wrap'><div class='score-bar-label'>{k}</div><div class='score-bar'><div class='score-fill' style='width:{max(0, min(100, int(v)))}%'></div></div></div>"
                for k, v in sorted(category_scores.items(), key=lambda x: x[1], reverse=True)
            ]
        )
        st.markdown(f"<div class='glass-card'><div class='section-title'>계열 적합도</div>{score_items}</div>", unsafe_allow_html=True)

    with right:
        st.markdown("<div class='section-title'>추천 대학</div>", unsafe_allow_html=True)
        if not recommendations:
            st.warning("현재 HTML에서 학과 또는 대학 적합 신호를 충분히 추출하지 못했습니다.")
        for idx, recommendation in enumerate(recommendations, start=1):
            render_university_card(recommendation, idx)

    with st.expander("세부 추출 정보", expanded=False):
        st.json(
            {
                "parser_mode": signals.get("parser_mode"),
                "overall_grade": signals.get("overall_grade"),
                "subjects": signals.get("subjects"),
                "preferred_track": signals.get("preferred_track"),
                "target_university": signals.get("target_university"),
                "admission_preference": signals.get("admission_preference"),
                "target_departments": target_departments,
                "strengths": signals.get("strengths"),
                "risks": signals.get("risks"),
                "notable_activities": signals.get("notable_activities"),
                "essay_strength": signals.get("essay_strength"),
                "math_risk": signals.get("math_risk"),
                "humanities_media_fit": signals.get("humanities_media_fit"),
                "category_scores": category_scores,
                "extraction_confidence": signals.get("extraction_confidence"),
                "evidence_flags": signals.get("evidence_flags"),
                "top_keywords": signals.get("top_keywords", [])[:20],
            }
        )

    with st.expander("원시 텍스트 미리보기", expanded=False):
        st.text_area("HTML 추출 텍스트", signals["raw_text"][:5000], height=280)


if __name__ == "__main__":
    main()
