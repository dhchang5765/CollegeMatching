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


def build_extraction_context(html_text: str) -> Dict[str, str]:
    soup = BeautifulSoup(html_text, "html.parser")
    title = strip_text(soup.title.get_text(" ", strip=True)) if soup.title else ""

    tables: List[str] = []
    for table in soup.find_all("table")[:8]:
        rows: List[str] = []
        for tr in table.find_all("tr")[:20]:
            cells = [strip_text(td.get_text(" ", strip=True)) for td in tr.find_all(["th", "td"])]
            cells = [c for c in cells if c]
            if cells:
                rows.append(" | ".join(cells))
        if rows:
            tables.append("TABLE\n" + "\n".join(rows))

    lists: List[str] = []
    for ul in soup.find_all(["ul", "ol"])[:10]:
        items = [strip_text(li.get_text(" ", strip=True)) for li in ul.find_all("li")[:15]]
        items = [x for x in items if x]
        if items:
            lists.append("LIST\n" + "\n".join(f"- {x}" for x in items))

    return {
        "title": title,
        "tables": "\n\n".join(tables),
        "lists": "\n\n".join(lists),
        "structured_text": extract_structured_text(html_text),
    }


class StudentCoreSchema(BaseModel):
    overall_grade: Optional[float] = Field(default=None)
    target_university: Optional[str] = Field(default=None)
    preferred_track: Optional[str] = Field(default=None)
    admission_preference: Optional[str] = Field(default=None)
    target_departments: List[str] = Field(default_factory=list)
    subjects: Dict[str, Optional[float]] = Field(default_factory=dict)
    top_keywords: List[str] = Field(default_factory=list)


class StudentExtendedSchema(BaseModel):
    strengths: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    notable_activities: List[str] = Field(default_factory=list)
    is_student_record_heavy: Optional[bool] = Field(default=None)
    essay_strength: Optional[bool] = Field(default=None)
    math_risk: Optional[bool] = Field(default=None)
    humanities_media_fit: Optional[bool] = Field(default=None)


def extract_signals_with_gemini_multi_stage(html_text: str) -> Tuple[Optional[Dict[str, Any]], str]:
    api_key = get_secret_value("GEMINI_API_KEY")
    if not api_key or genai is None:
        return None, "regex-only"

    ctx = build_extraction_context(html_text)
    client = genai.Client(api_key=api_key)

    core_prompt = f"""다음은 학생 분석 HTML에서 정리한 정보다.
추측하지 말고 근거가 있는 정보만 JSON으로 추출하라.
특히 overall_grade, target_departments, subjects, admission_preference, top_keywords를 우선 추출하라.

[TITLE]
{ctx['title']}

[TABLES]
{ctx['tables'][:9000]}

[LISTS]
{ctx['lists'][:5000]}

[TEXT]
{ctx['structured_text'][:12000]}
"""

    ext_prompt = f"""다음 학생 HTML 구조화 텍스트에서 강점, 위험요인, 활동, 학생부 중심 여부를 JSON으로 추출하라.
추측하지 말고 근거가 약하면 빈 값으로 둬라.

[TEXT]
{ctx['structured_text'][:14000]}
"""

    try:
        core = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=core_prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": StudentCoreSchema,
                "temperature": 0.05,
            },
        )
        ext = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=ext_prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": StudentExtendedSchema,
                "temperature": 0.05,
            },
        )
        core_json = json.loads(core.text) if getattr(core, "text", None) else {}
        ext_json = json.loads(ext.text) if getattr(ext, "text", None) else {}
        merged = dict(core_json)
        merged.update(ext_json)
        return merged, "gemini-multistage"
    except Exception:
        return None, "regex-only"


def regex_extract_signals_v2(html_text: str) -> Dict[str, Any]:
    text = extract_structured_text(html_text)
    result: Dict[str, Any] = {
        "overall_grade": None,
        "target_university": None,
        "preferred_track": None,
        "admission_preference": None,
        "target_departments": [],
        "subjects": {},
        "top_keywords": [],
        "strengths": [],
        "risks": [],
        "notable_activities": [],
        "is_student_record_heavy": None,
        "essay_strength": None,
        "math_risk": None,
        "humanities_media_fit": None,
    }

    grade_patterns = [
        r"전체\s*등급[^0-9]{0,10}([1-9](?:\.[0-9])?)",
        r"내신\s*등급[^0-9]{0,10}([1-9](?:\.[0-9])?)",
        r"평균\s*등급[^0-9]{0,10}([1-9](?:\.[0-9])?)",
        r"([1-9](?:\.[0-9])?)\s*등급",
    ]
    for pat in grade_patterns:
        m = re.search(pat, text)
        if m:
            try:
                result["overall_grade"] = float(m.group(1))
                break
            except Exception:
                pass

    dept_candidates: List[str] = []
    dept_keywords = ["학과", "학부", "전공", "의예과", "간호학과", "미디어", "경영", "경제", "심리", "생명과학", "컴퓨터", "소프트웨어", "전자공학", "통계학"]
    for line in text.splitlines():
        s = strip_text(line)
        if any(k in s for k in dept_keywords) and len(s) <= 30:
            dept_candidates.append(s)
    result["target_departments"] = list(dict.fromkeys(dept_candidates))[:5]

    subj_map = {"국어": ["국어"], "영어": ["영어"], "수학": ["수학"], "과학": ["과학", "과탐"], "사회": ["사회", "사탐"]}
    for canon, keys in subj_map.items():
        for key in keys:
            m = re.search(rf"{key}[^0-9]{{0,8}}([1-9](?:\.[0-9])?)", text)
            if m:
                result["subjects"][canon] = float(m.group(1))
                break

    if any(x in text for x in ["학생부종합", "학종"]):
        result["admission_preference"] = "학생부종합"
    elif any(x in text for x in ["학생부교과", "교과전형"]):
        result["admission_preference"] = "학생부교과"
    elif "논술" in text:
        result["admission_preference"] = "논술"
    elif "정시" in text:
        result["admission_preference"] = "정시"

    keyword_pool: List[str] = []
    for kw in ["탐구", "창의", "리더십", "봉사", "협업", "표현", "분석", "연구", "의사소통", "문제해결", "국제", "미디어", "수학", "과학"]:
        if kw in text:
            keyword_pool.append(kw)
    result["top_keywords"] = keyword_pool[:10]

    result["is_student_record_heavy"] = any(x in text for x in ["세특", "창체", "동아리", "수상", "봉사", "활동"])
    result["essay_strength"] = any(x in text for x in ["논술", "서술", "글쓰기"])
    result["math_risk"] = any(x in text for x in ["수학 약점", "수학 위험", "수학 보완"])
    result["humanities_media_fit"] = any(x in text for x in ["미디어", "언론", "광고", "홍보", "커뮤니케이션"])
    return result


def merge_signals(primary: Dict[str, Any], fallback: Dict[str, Any], parser_mode: str) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    keys = set(primary.keys()) | set(fallback.keys())
    for k in keys:
        pv = primary.get(k)
        fv = fallback.get(k)
        if isinstance(pv, list):
            merged[k] = list(dict.fromkeys((pv or []) + (fv or [])))
        elif isinstance(pv, dict):
            tmp = dict(fv or {})
            tmp.update(pv or {})
            merged[k] = tmp
        else:
            merged[k] = pv if pv not in [None, "", []] else fv
    merged["parser_mode"] = parser_mode
    return merged


def parsing_confidence(signals: Dict[str, Any]) -> float:
    score = 0.0
    if signals.get("overall_grade") is not None:
        score += 0.30
    if signals.get("target_departments"):
        score += 0.25
    if signals.get("subjects"):
        score += 0.20
    if signals.get("top_keywords"):
        score += 0.15
    if signals.get("admission_preference"):
        score += 0.10
    return round(score, 2)


def recommendation_readiness(signals: Dict[str, Any]) -> float:
    essential = 0
    if signals.get("overall_grade") is not None:
        essential += 1
    if signals.get("target_departments"):
        essential += 1
    if signals.get("subjects") or signals.get("top_keywords"):
        essential += 1
    return round(essential / 3, 2)



