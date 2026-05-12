import os
import re
import json
import hmac
import math
import hashlib
import secrets
from collections import Counter, defaultdict
from typing import Dict, List, Tuple, Optional, Any

import streamlit as st
from bs4 import BeautifulSoup

try:
    from google import genai
except Exception:
    genai = None

try:
    from pydantic import BaseModel, Field
except Exception:
    BaseModel = object
    def Field(default=None, default_factory=None):
        if default_factory is not None:
            return default_factory()
        return default

GEMINI_MODEL = "gemini-3-flash"
JSON_DB_PATH = "merged_university_db.json"

CATEGORY_KEYWORDS = {
    "인문": ["국어", "문학", "언어", "역사", "철학", "독해", "비평", "서사", "글쓰기", "윤리", "고전"],
    "사회": ["사회", "경제", "경영", "정치", "행정", "미디어", "광고", "홍보", "심리", "소통", "기획", "콘텐츠", "법률", "국제"],
    "자연": ["수학", "과학", "생명", "화학", "물리", "통계", "탐구", "실험", "지구과학", "천문", "환경"],
    "공학": ["공학", "컴퓨터", "소프트웨어", "AI", "인공지능", "전자", "기계", "설계", "코딩", "데이터", "기술", "반도체", "에너지", "로봇"],
    "의학": ["의료", "질병", "해부", "임상", "인체", "약리", "면역", "보건", "신경", "유전", "생명윤리", "수술", "진단"],
    "치의학": ["구강", "치아", "치과학", "치주", "교정"],
    "한의학": ["한방", "동양의학", "본초학", "경혈", "체질", "침구"],
    "수의학": ["동물", "반려동물", "가축", "방역", "수의", "야생동물"],
    "간호": ["케어", "간호", "임상실습", "환자관리", "기초간호"],
    "교육": ["학습", "교수", "수업", "교육공학", "아동", "청소년", "발달", "상담"]
}

DEPT_ALIAS = {
    "미디어": ["미디어커뮤니케이션학", "언론정보학", "콘텐츠디자인", "광고홍보학", "신문방송학"],
    "경영": ["경영학", "경제학", "국제통상학", "빅데이터경영", "회계학", "재무금융학"],
    "심리": ["심리학", "사회학", "상담심리학"],
    "컴퓨터": ["컴퓨터공학", "소프트웨어학", "인공지능학과", "데이터사이언스", "AI학과", "정보보호학"],
    "생명": ["생명과학", "생명공학", "생명시스템학", "의생명공학", "바이오시스템학"],
    "의학": ["의예과", "의과학", "임상의학"],
    "치의학": ["치의예과", "구강보건학"],
    "한의학": ["한의예과"],
    "수의학": ["수의예과", "동물자원학"],
    "약학": ["약학과", "제약공학", "바이오의약"],
    "간호": ["간호학과"],
    "보건": ["보건행정학", "임상병리학", "방사선학", "물리치료학"],
    "사범": ["국어교육", "수학교육", "영어교육", "교육학"],
    "환경": ["환경공학", "에너지공학", "기후에너지"],
    "미래차": ["자동차공학", "미래모빌리티", "스마트모빌리티"]
}

SPECIAL_PATTERNS = {
    "grade": [
        r"([0-9]+(?:\.[0-9]+)?)\s*등급",
        r"내신\s*([0-9]+(?:\.[0-9]+)?)",
        r"모평\s*([0-9]+(?:\.[0-9]+)?)\s*등급",
        r"평균\s*([0-9]+(?:\.[0-9]+)?)\s*등급",
    ]
}

UNIVERSITY_KEYWORDS = [
    "서울대", "연세대", "고려대", "성균관대", "한양대", "서강대", "중앙대", "경희대", "한국외대",
    "서울시립대", "건국대", "동국대", "홍익대", "이화여대", "숙명여대", "국민대", "숭실대",
    "아주대", "인하대", "부산대", "경북대", "전남대", "충남대", "충북대", "전북대",
    "KAIST", "카이스트", "포스텍", "POSTECH", "GIST", "DGIST", "UNIST",
    "가천대", "세종대", "단국대", "명지대", "상명대", "한성대", "서경대", "서울과기대",
    "광운대", "가톨릭대", "인천대", "한림대", "을지대", "차의과학대"
]

UNIVERSITY_CLUSTER_MAP = {
    "SKY": ["서울대", "연세대", "고려대"],
    "의치한약수": ["의학", "치의학", "한의학", "약학", "수의학"],
    "IST": ["KAIST", "GIST", "DGIST", "UNIST"],
}

TRACK_KEYWORD_MAP = {
    "AI": ["AI", "인공지능", "컴퓨터", "소프트웨어", "데이터", "코딩", "IT", "알고리즘", "정보보호", "반도체"],
    "미디어": ["미디어", "SNS", "광고", "홍보", "콘텐츠", "커뮤니케이션", "언론", "브랜딩", "저널리즘"],
    "경영": ["경영", "경제", "금융", "비즈니스", "리더십", "전략", "마케팅", "기획"],
    "생명": ["생명", "바이오", "의생명", "생명과학", "유전", "면역", "의과학"],
    "의학": ["의대", "의학", "의예", "임상", "의료", "질병", "진단"],
    "교육": ["교육", "교직", "아동", "청소년", "수업", "학습"],
}

ACTIVITY_KEYWORDS = ["KMO", "R&E", "RISS", "DBpia", "MMI", "세특", "학생부", "동아리", "탐구", "논문", "올림피아드"]


if BaseModel is not object:
    class StudentProfileSchema(BaseModel):
        overall_grade: Optional[float] = Field(default=None)
        target_university: Optional[str] = Field(default=None)
        target_universities: List[str] = Field(default_factory=list)
        target_clusters: List[str] = Field(default_factory=list)
        preferred_track: Optional[str] = Field(default=None)
        admission_preference: Optional[str] = Field(default=None)
        target_departments: List[str] = Field(default_factory=list)
        subjects: Dict[str, Optional[float]] = Field(default_factory=dict)
        top_keywords: List[str] = Field(default_factory=list)
        strengths: List[str] = Field(default_factory=list)
        risks: List[str] = Field(default_factory=list)
        notable_activities: List[str] = Field(default_factory=list)
        parser_mode: Optional[str] = Field(default=None)
        is_student_record_heavy: Optional[bool] = Field(default=None)
        essay_strength: Optional[bool] = Field(default=None)
        math_risk: Optional[bool] = Field(default=None)
        humanities_media_fit: Optional[bool] = Field(default=None)


def get_secret_value(key: str, default: str | None = None) -> str | None:
    try:
        if hasattr(st, "secrets") and key in st.secrets:
            value = st.secrets[key]
            if value is None:
                return default
            return str(value).strip()
    except Exception:
        pass
    value = os.getenv(key)
    if value is None:
        return default
    return str(value).strip()


def require_secret(key: str) -> str:
    value = get_secret_value(key)
    if not value:
        st.error(f"필수 설정값 누락: {key}")
        st.stop()
    return value


def hash_password(password: str, iterations: int = 240000) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algo, iter_str, salt_hex, digest_hex = stored_hash.split('$', 3)
        if algo != 'pbkdf2_sha256':
            return False
        iterations = int(iter_str)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        candidate = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
        return hmac.compare_digest(candidate, expected)
    except Exception:
        return False


def require_login() -> bool:
    stored_hash = get_secret_value("APP_PASSWORD_HASH", "")
    if not stored_hash:
        st.warning('APP_PASSWORD_HASH가 설정되지 않았습니다. Streamlit Cloud의 Secrets를 확인하십시오.')
        st.stop()

    if st.session_state.get('authenticated'):
        return True

    st.title("학생 맞춤 대학 추천 시스템")
    st.caption("비밀번호 인증 후 사용 가능합니다.")
    password = st.text_input("비밀번호", type="password")

    if st.button("로그인"):
        if verify_password(password, stored_hash):
            st.session_state['authenticated'] = True
            st.rerun()
        else:
            st.error("비밀번호가 올바르지 않습니다.")
    st.stop()
    return False


def strip_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def unique_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        x2 = strip_text(str(x))
        if x2 and x2 not in seen:
            seen.add(x2)
            out.append(x2)
    return out


def safe_float(x: Any) -> Optional[float]:
    try:
        if x is None or x == "":
            return None
        return float(x)
    except Exception:
        return None


def normalize_university_name(name: str) -> str:
    if not name:
        return ""
    name = strip_text(name)
    mapping = {
        "카이스트": "KAIST",
        "포항공대": "POSTECH",
        "포스텍": "POSTECH",
    }
    return mapping.get(name, name)


def extract_text_lines_from_html(html_text: str) -> List[str]:
    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.extract()

    lines = []
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "p", "li", "div", "span", "td", "th"]):
        txt = strip_text(tag.get_text(" ", strip=True))
        if len(txt) >= 2:
            lines.append(txt)
    return unique_keep_order(lines)


def extract_chart_script_text(html_text: str) -> str:
    soup = BeautifulSoup(html_text, "html.parser")
    scripts = []
    for s in soup.find_all("script"):
        txt = s.string if s.string else s.get_text(" ", strip=True)
        txt = strip_text(txt)
        if txt:
            scripts.append(txt)
    return "\n".join(scripts)


def extract_s15_university_cards(html_text: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html_text, "html.parser")
    results = []
    for card in soup.select(".s15-univ"):
        tier = strip_text(card.select_one(".tier").get_text(" ", strip=True)) if card.select_one(".tier") else ""
        name = strip_text(card.select_one(".name").get_text(" ", strip=True)) if card.select_one(".name") else ""
        desc = strip_text(card.select_one(".desc").get_text(" ", strip=True)) if card.select_one(".desc") else ""
        prob_text = strip_text(card.select_one(".s15-univ-prob").get_text(" ", strip=True)) if card.select_one(".s15-univ-prob") else ""
        prob = None
        m = re.search(r"(\d{1,3})", prob_text)
        if m:
            prob = int(m.group(1))
        if name or desc or prob is not None:
            results.append({
                "tier": tier,
                "name": normalize_university_name(name),
                "desc": desc,
                "prob": prob
            })
    return results


def extract_s15_from_script(html_text: str) -> List[Dict[str, Any]]:
    text = extract_chart_script_text(html_text)
    out = []
    for m in re.finditer(r"label\s+([A-Za-z가-힣0-9]+)\s*,\s*data\s+([0-9,\s.]+)", text):
        label = normalize_university_name(m.group(1))
        data = [safe_float(x.strip()) for x in m.group(2).split(",") if x.strip()]
        data = [x for x in data if x is not None]
        if not data:
            continue
        out.append({
            "name": label,
            "prob": int(max(data)),
            "source": "chart_script"
        })
    return out


def extract_explicit_universities(text: str) -> List[str]:
    found = []
    for kw in UNIVERSITY_KEYWORDS:
        if kw in text:
            found.append(normalize_university_name(kw))
    return unique_keep_order(found)


def extract_clusters_and_track_keywords(text: str) -> Tuple[List[str], List[str], List[str]]:
    clusters = []
    track_keywords = []
    activities = []

    for ck in UNIVERSITY_CLUSTER_MAP.keys():
        if ck in text:
            clusters.append(ck)

    for tk, kws in TRACK_KEYWORD_MAP.items():
        for kw in kws:
            if kw.lower() in text.lower():
                track_keywords.append(tk)
                break

    for ak in ACTIVITY_KEYWORDS:
        if ak.lower() in text.lower():
            activities.append(ak)

    return unique_keep_order(clusters), unique_keep_order(track_keywords), unique_keep_order(activities)


def extract_grade_from_text(text: str) -> Optional[float]:
    vals = []
    for pat in SPECIAL_PATTERNS["grade"]:
        for m in re.findall(pat, text):
            try:
                v = float(m)
                if 0.5 <= v <= 9.0:
                    vals.append(v)
            except Exception:
                pass
    return min(vals) if vals else None


def classify_track_from_keywords(keywords: List[str]) -> Optional[str]:
    scores = Counter()
    blob = " ".join(keywords)
    for track, kws in TRACK_KEYWORD_MAP.items():
        for kw in kws:
            if kw.lower() in blob.lower():
                scores[track] += 1
    return scores.most_common(1)[0][0] if scores else None


def infer_category_from_track(track: Optional[str]) -> Optional[str]:
    if not track:
        return None
    mapping = {
        "AI": "공학",
        "미디어": "사회",
        "경영": "사회",
        "생명": "자연",
        "의학": "의학",
        "교육": "교육",
    }
    return mapping.get(track)


def load_university_db() -> List[Dict[str, Any]]:
    if os.path.exists(JSON_DB_PATH):
        try:
            with open(JSON_DB_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
        except Exception:
            pass

    return [
        {"university": "서울대", "department": "경영학과", "category": "사회", "min_grade": 1.3, "keywords": ["경영", "리더십", "경제"]},
        {"university": "연세대", "department": "언론홍보영상학부", "category": "사회", "min_grade": 1.8, "keywords": ["미디어", "콘텐츠", "홍보", "소통"]},
        {"university": "고려대", "department": "미디어학부", "category": "사회", "min_grade": 1.9, "keywords": ["미디어", "언론", "커뮤니케이션"]},
        {"university": "중앙대", "department": "미디어커뮤니케이션학부", "category": "사회", "min_grade": 2.5, "keywords": ["미디어", "광고", "홍보", "콘텐츠"]},
        {"university": "성균관대", "department": "소프트웨어학과", "category": "공학", "min_grade": 1.7, "keywords": ["AI", "소프트웨어", "코딩", "데이터"]},
        {"university": "한양대", "department": "컴퓨터소프트웨어학부", "category": "공학", "min_grade": 2.0, "keywords": ["AI", "컴퓨터", "알고리즘"]},
        {"university": "KAIST", "department": "전산학부", "category": "공학", "min_grade": 1.2, "keywords": ["AI", "수학", "알고리즘", "연구"]},
        {"university": "POSTECH", "department": "컴퓨터공학과", "category": "공학", "min_grade": 1.3, "keywords": ["AI", "컴퓨터", "연구"]},
        {"university": "가톨릭대", "department": "의예과", "category": "의학", "min_grade": 1.1, "keywords": ["의학", "의료", "생명"]},
        {"university": "한림대", "department": "의예과", "category": "의학", "min_grade": 1.2, "keywords": ["의학", "의료", "봉사"]},
    ]


def build_structured_text_for_llm(html_text: str) -> str:
    lines = extract_text_lines_from_html(html_text)
    script_text = extract_chart_script_text(html_text)

    important = []
    for ln in lines:
        if any(key in ln for key in [
            "UNIVERSITY SIMULATION", "FINAL CONSULTANTS CONCLUSION", "DIAGNOSIS",
            "SKY", "KAIST", "SNS", "AI", "KMO", "학생부", "세특", "면접", "논술"
        ]):
            important.append(ln)

    s15_cards = extract_s15_university_cards(html_text)
    important.append("[S15_CARDS]")
    for c in s15_cards:
        important.append(json.dumps(c, ensure_ascii=False))

    important.append("[SCRIPT]")
    important.append(script_text[:6000])

    blob = "\n".join(unique_keep_order(important))
    return blob[:18000]


def extract_signals_with_gemini(html_text: str) -> Optional[Dict[str, Any]]:
    if genai is None or BaseModel is object:
        return None

    api_key = get_secret_value("GEMINI_API_KEY")
    if not api_key:
        return None

    structured_text = build_structured_text_for_llm(html_text)

    prompt = f"""
다음은 학생 진단 HTML에서 추출한 구조화 텍스트다.
반드시 JSON만 출력하라.
추측하지 말고 텍스트 근거가 있을 때만 값 채워라.

필드 의미:
- target_university: 가장 직접적인 1개 학교
- target_universities: 직접 언급된 학교들
- target_clusters: SKY, IST 같은 대학군
- preferred_track: AI, 미디어, 경영, 의학 등
- target_departments: 학과/계열
- notable_activities: KMO, R&E, MMI 등
- strengths, risks: 핵심 강/약점
- parser_mode: gemini

[TEXT]
{structured_text}
"""

    try:
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": StudentProfileSchema,
                "temperature": 0.1,
            },
        )
        data = json.loads(resp.text)
        if isinstance(data, dict):
            data["parser_mode"] = "gemini"
            return data
    except Exception:
        return None
    return None


def extract_example_specific_signals(html_text: str) -> Dict[str, Any]:
    lines = extract_text_lines_from_html(html_text)
    text_blob = "\n".join(lines)
    script_blob = extract_chart_script_text(html_text)

    s15_cards = extract_s15_university_cards(html_text)
    s15_script_univs = extract_s15_from_script(html_text)

    explicit_univs = extract_explicit_universities(text_blob + "\n" + script_blob)
    clusters, track_keywords, activities = extract_clusters_and_track_keywords(text_blob + "\n" + script_blob)

    preferred_track = classify_track_from_keywords(track_keywords + explicit_univs + activities)
    overall_grade = extract_grade_from_text(text_blob)

    target_universities = []
    for card in s15_cards:
        if card.get("name"):
            target_universities.append(card["name"])
    for row in s15_script_univs:
        if row.get("name") and row["name"] not in target_universities:
            target_universities.append(row["name"])
    for u in explicit_univs:
        if u not in target_universities:
            target_universities.append(u)

    target_universities = unique_keep_order(target_universities)

    top_university = None
    s15_named = [c for c in s15_cards if c.get("name")]
    if s15_named:
        s15_named = sorted(s15_named, key=lambda x: (x.get("prob") is None, -(x.get("prob") or 0)))
        top_university = s15_named[0]["name"]
    elif target_universities:
        top_university = target_universities[0]

    target_departments = []
    lower_blob = (text_blob + " " + script_blob).lower()
    for alias_key, dept_list in DEPT_ALIAS.items():
        if alias_key.lower() in lower_blob:
            target_departments.extend(dept_list)

    strengths = []
    risks = []

    if "학생부" in text_blob or "세특" in text_blob:
        strengths.append("학생부 기반 강점")
    if "AI" in text_blob or "인공지능" in text_blob:
        strengths.append("AI/공학 진로 적합 신호")
    if "SNS" in text_blob or "미디어" in text_blob:
        strengths.append("미디어/콘텐츠 진로 적합 신호")
    if "KMO" in text_blob:
        strengths.append("수학/경시 활동 신호")

    if re.search(r"수학[^\n]{0,15}(약점|부족|리스크|불안)", text_blob):
        risks.append("수학 리스크")
    if re.search(r"실행[^\n]{0,15}(부족|낮|미흡)", text_blob):
        risks.append("실행력 리스크")
    if re.search(r"면접[^\n]{0,15}(불안|약점|부족)", text_blob):
        risks.append("면접 리스크")

    return {
        "overall_grade": overall_grade,
        "target_university": top_university,
        "target_universities": target_universities,
        "target_clusters": clusters,
        "preferred_track": preferred_track,
        "admission_preference": "학생부종합" if ("학생부" in text_blob or "세특" in text_blob) else None,
        "target_departments": unique_keep_order(target_departments),
        "subjects": {},
        "top_keywords": unique_keep_order(track_keywords + activities + explicit_univs + clusters),
        "strengths": unique_keep_order(strengths),
        "risks": unique_keep_order(risks),
        "notable_activities": unique_keep_order(activities),
        "parser_mode": "rule-based+s15+s17+script",
        "is_student_record_heavy": ("학생부" in text_blob or "세특" in text_blob),
        "essay_strength": ("논술" in text_blob),
        "math_risk": ("수학" in " ".join(risks)),
        "humanities_media_fit": ("SNS" in text_blob or "미디어" in text_blob),
        "evidence": {
            "s15_cards": s15_cards,
            "s15_script_univs": s15_script_univs,
            "explicit_univs": explicit_univs,
            "clusters": clusters,
            "track_keywords": track_keywords,
            "activities": activities
        }
    }


def merge_signals(rule_signals: Dict[str, Any], ai_signals: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not ai_signals:
        return rule_signals

    merged = dict(rule_signals)

    scalar_fields = [
        "overall_grade", "target_university", "preferred_track",
        "admission_preference", "parser_mode", "is_student_record_heavy",
        "essay_strength", "math_risk", "humanities_media_fit"
    ]
    list_fields = [
        "target_universities", "target_clusters", "target_departments",
        "top_keywords", "strengths", "risks", "notable_activities"
    ]
    dict_fields = ["subjects"]

    for f in scalar_fields:
        if ai_signals.get(f) not in [None, "", []]:
            merged[f] = ai_signals.get(f)

    for f in list_fields:
        merged[f] = unique_keep_order((rule_signals.get(f) or []) + (ai_signals.get(f) or []))

    for f in dict_fields:
        base = dict(rule_signals.get(f) or {})
        base.update(ai_signals.get(f) or {})
        merged[f] = base

    if not merged.get("target_university"):
        tus = merged.get("target_universities") or []
        if tus:
            merged["target_university"] = tus[0]

    if not merged.get("preferred_track"):
        merged["preferred_track"] = classify_track_from_keywords(merged.get("top_keywords", []))

    pm_rule = rule_signals.get("parser_mode", "rule")
    pm_ai = ai_signals.get("parser_mode", "gemini")
    merged["parser_mode"] = f"{pm_ai}+{pm_rule}"

    return merged


def score_university_fit(signals: Dict[str, Any], row: Dict[str, Any]) -> float:
    score = 40.0

    uni = row.get("university", "")
    dept = row.get("department", "")
    row_keywords = row.get("keywords", []) or []

    overall_grade = signals.get("overall_grade")
    target_university = signals.get("target_university")
    target_universities = signals.get("target_universities", []) or []
    target_clusters = signals.get("target_clusters", []) or []
    preferred_track = signals.get("preferred_track")
    target_departments = signals.get("target_departments", []) or []
    top_keywords = signals.get("top_keywords", []) or []
    min_grade = row.get("min_grade")

    if target_university and uni == target_university:
        score += 30
    elif uni in target_universities:
        score += 22

    if "SKY" in target_clusters and uni in ["서울대", "연세대", "고려대"]:
        score += 15
    if "IST" in target_clusters and uni in ["KAIST", "GIST", "DGIST", "UNIST"]:
        score += 15

    if preferred_track:
        if preferred_track == "AI" and any(k in dept for k in ["컴퓨터", "소프트웨어", "AI", "데이터", "전산"]):
            score += 18
        elif preferred_track == "미디어" and any(k in dept for k in ["미디어", "언론", "광고", "홍보", "커뮤니케이션", "콘텐츠"]):
            score += 18
        elif preferred_track == "경영" and any(k in dept for k in ["경영", "경제", "통상", "금융"]):
            score += 18
        elif preferred_track == "의학" and any(k in dept for k in ["의예", "의학", "의과"]):
            score += 18
        elif preferred_track == "생명" and any(k in dept for k in ["생명", "바이오", "의생명"]):
            score += 18

    for td in target_departments:
        if td and td in dept:
            score += 10
            break

    kw_hit = 0
    for kw in top_keywords:
        if kw and any(kw.lower() in str(x).lower() for x in ([dept] + row_keywords)):
            kw_hit += 1
    score += min(kw_hit * 2.5, 12)

    if overall_grade is not None and min_grade is not None:
        diff = overall_grade - min_grade
        if diff <= -0.2:
            score += 18
        elif diff <= 0.2:
            score += 12
        elif diff <= 0.6:
            score += 6
        elif diff <= 1.0:
            score += 1
        else:
            score -= min((diff - 1.0) * 10, 25)

    if signals.get("is_student_record_heavy"):
        score += 3
    if signals.get("math_risk") and preferred_track == "AI":
        score -= 6

    return max(0.0, min(100.0, round(score, 1)))


def recommend_universities(signals: Dict[str, Any], db: List[Dict[str, Any]], top_n: int = 10) -> List[Dict[str, Any]]:
    scored = []
    for row in db:
        fit_score = score_university_fit(signals, row)
        scored.append({**row, "fit_score": fit_score})
    scored.sort(key=lambda x: x["fit_score"], reverse=True)
    return scored[:top_n]


def render_results(signals: Dict[str, Any], results: List[Dict[str, Any]]) -> None:
    st.subheader("추출 결과")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("파서 모드", signals.get("parser_mode", "-"))
    c2.metric("목표 대학", signals.get("target_university") or "-")
    c3.metric("선호 트랙", signals.get("preferred_track") or "-")
    c4.metric("내신 추정", signals.get("overall_grade") if signals.get("overall_grade") is not None else "-")

    with st.expander("추출 신호 상세", expanded=False):
        st.json(signals)

    st.subheader("추천 결과")
    if not results:
        st.warning("추천 결과가 없습니다. 파싱 신호를 확인하십시오.")
        return

    for i, row in enumerate(results, 1):
        st.markdown(
            f"""
**{i}. {row.get('university', '-')} - {row.get('department', '-')}**  
- 적합도: {row.get('fit_score', '-')}  
- 기준 등급: {row.get('min_grade', '-')}  
- 키워드: {", ".join(row.get('keywords', [])[:5])}
            """
        )


def main() -> None:
    st.set_page_config(page_title="학생 맞춤 대학 추천 시스템", layout="wide")
    require_login()

    st.title("학생 HTML 기반 대학 추천 시스템")
    st.caption("S15/S17/스크립트/LLM 보강 파서를 적용한 수정 버전")

    uploaded_file = st.file_uploader("학생 진단 HTML 파일 업로드", type=["html", "htm"])

    if not uploaded_file:
        st.info("HTML 파일을 업로드하십시오.")
        return

    html_bytes = uploaded_file.read()
    html_text = html_bytes.decode("utf-8", errors="ignore")

    if not html_text or len(strip_text(html_text)) < 50:
        st.error("HTML 내용이 비어 있거나 너무 짧습니다.")
        return

    try:
        rule_signals = extract_example_specific_signals(html_text)
    except Exception as e:
        st.error(f"규칙 기반 파싱 실패: {e}")
        rule_signals = {
            "overall_grade": None,
            "target_university": None,
            "target_universities": [],
            "target_clusters": [],
            "preferred_track": None,
            "admission_preference": None,
            "target_departments": [],
            "subjects": {},
            "top_keywords": [],
            "strengths": [],
            "risks": [],
            "notable_activities": [],
            "parser_mode": "rule-failed",
            "is_student_record_heavy": None,
            "essay_strength": None,
            "math_risk": None,
            "humanities_media_fit": None,
        }

    ai_signals = extract_signals_with_gemini(html_text)
    signals = merge_signals(rule_signals, ai_signals)

    db = load_university_db()
    results = recommend_universities(signals, db, top_n=10)
    render_results(signals, results)


if __name__ == "__main__":
    main()
