import os
import re
import json
import hmac
import hashlib
import secrets
from collections import Counter
from typing import Dict, List, Tuple, Optional

import streamlit as st
from bs4 import BeautifulSoup

try:
    from google import genai
except Exception:
    genai = None


GEMINI_MODEL = "gemini-3-flash"
JSON_DB_PATH = "seoul_gyeonggi_university_db.json"

CATEGORY_KEYWORDS = {
    "인문": ["국어", "문학", "언어", "인문", "역사", "철학", "독해", "비평", "서사", "글쓰기"],
    "사회": ["사회", "경제", "경영", "정치", "행정", "미디어", "광고", "홍보", "심리", "소통", "기획", "콘텐츠"],
    "자연": ["수학", "과학", "생명", "화학", "물리", "통계", "탐구", "실험"],
    "공학": ["공학", "컴퓨터", "소프트웨어", "AI", "전자", "기계", "설계", "코딩", "데이터", "기술"]
}

DEPT_ALIAS = {
    "미디어커뮤니케이션": ["미디어커뮤니케이션", "미디어학", "언론정보학"],
    "광고": ["광고홍보학", "미디어커뮤니케이션", "언론정보학"],
    "콘텐츠": ["미디어커뮤니케이션", "디지털미디어학", "언론홍보영상학"],
    "방송": ["미디어커뮤니케이션", "신문방송학", "언론홍보영상학"],
    "언론": ["언론정보학", "신문방송학", "미디어커뮤니케이션"],
    "경영": ["경영학", "경제학", "국제통상학"],
    "심리": ["심리학", "사회학", "행정학"],
    "컴퓨터": ["컴퓨터공학", "컴퓨터과학", "소프트웨어학"],
    "생명": ["생명과학", "생명공학", "생명시스템학"]
}

SPECIAL_PATTERNS = {
    "grade": [r"([0-9.]+)등급", r"내신\s*([0-9.]+)", r"모평\s*([0-9.]+)등급"]
}

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
        
    st.markdown('<div class="login-wrap">', unsafe_allow_html=True)
    st.subheader('로그인')
    password = st.text_input('비밀번호', type='password', placeholder='앱 비밀번호 입력')
    submitted = st.button('로그인', use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)
    if submitted:
        if verify_password(password, stored_hash):
            st.session_state['authenticated'] = True
            st.success('인증되었습니다.')
            st.rerun()
        else:
            st.error('비밀번호가 일치하지 않습니다.')
    st.stop()

def load_json_db(path: str) -> Dict:
    if not os.path.exists(path):
        raise FileNotFoundError(f"JSON DB 파일이 없습니다: {path}")
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def strip_text(s: str) -> str:
    return re.sub(r'\s+', ' ', (s or '')).strip()


def html_to_text(html_text: str) -> str:
    soup = BeautifulSoup(html_text, 'html.parser')
    return strip_text(soup.get_text(' '))


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


def extract_example_specific_signals(html_text: str) -> Dict:
    text = html_to_text(html_text)
    lines = [ln.strip() for ln in re.split(r'[.!?]\s+', text) if ln.strip()]
    top_keywords = Counter(re.findall(r'[가-힣A-Za-z]{2,20}', text))
    for stop in ['학생', '분석', '결과', '응답', '진단', '영역', '전형', '활동', '학과', '대학']:
        top_keywords.pop(stop, None)

    overall_grade = None
    grade_candidates = collect_all_floats(text, SPECIAL_PATTERNS['grade'])
    reasonable = [g for g in grade_candidates if 1 <= g <= 9]
    if 3.5 in reasonable:
        overall_grade = 3.5
    elif reasonable:
        overall_grade = reasonable[0]

    preferred_track = None
    if '미디어커뮤니케이션' in text:
        preferred_track = '미디어커뮤니케이션'
    elif '광고' in text or '콘텐츠' in text or '방송' in text:
        preferred_track = '미디어'

    target_university = None
    if '중앙대 미디어커뮤니케이션 1지망' in text or '중앙대 미디어커뮤니케이션' in text:
        target_university = '중앙대학교'
    else:
        m = re.search(r'목표 대학\s*[:：]?\s*([가-힣A-Za-z0-9\s]+)', text)
        if m:
            target_university = strip_text(m.group(1))

    return {
        'raw_text': text,
        'overall_grade': overall_grade,
        'subjects': infer_subjects_from_text(text),
        'top_keywords': [w for w, _ in top_keywords.most_common(40)],
        'preferred_track': preferred_track,
        'target_university': target_university,
        'is_student_record_heavy': any(k in text for k in ['방송반', '글쓰기 대회', '생기부', '수행평가']),
        'admission_preference': '학생부종합' if ('학생부종합전형' in text or '학종' in text) else None,
        'essay_strength': True if (('논술' in text and '자신' in text) or '글쓰기' in text) else False,
        'math_risk': True if any(k in text for k in ['수학 회피', '수학 4등급', '모평 5등급', '수학은 진짜 못 하겠어요']) else False,
        'humanities_media_fit': True if any(k in text for k in ['인문계', '미디어 진로', '콘텐츠', '광고 기획']) else False,
        'line_samples': lines[:50]
    }


def normalize_subject(v: Optional[float]) -> float:
    if v is None:
        return 50.0
    if v <= 9:
        return max(0.0, 100 - (v - 1) * 12.5)
    return max(0.0, min(100.0, v))


def infer_category_scores(signals: Dict) -> Dict[str, float]:
    text = signals['raw_text']
    scores = {k: 0.0 for k in CATEGORY_KEYWORDS}
    for cat, kws in CATEGORY_KEYWORDS.items():
        for kw in kws:
            scores[cat] += text.count(kw) * 2.5
    subjects = signals.get('subjects', {})
    scores['인문'] += normalize_subject(subjects.get('국어')) * 0.30
    scores['사회'] += normalize_subject(subjects.get('사회')) * 0.35
    scores['사회'] += normalize_subject(subjects.get('영어')) * 0.15
    scores['자연'] += normalize_subject(subjects.get('과학')) * 0.25
    scores['공학'] += normalize_subject(subjects.get('수학')) * 0.30
    scores['공학'] += normalize_subject(subjects.get('과학')) * 0.10
    if signals.get('humanities_media_fit'):
        scores['인문'] += 25
        scores['사회'] += 35
    if signals.get('math_risk'):
        scores['공학'] -= 20
        scores['자연'] -= 10
    if signals.get('essay_strength'):
        scores['인문'] += 15
        scores['사회'] += 10
    return scores


def choose_target_departments(signals: Dict, category_scores: Dict[str, float], max_n: int = 2) -> List[str]:
    text = signals['raw_text']
    direct = []
    for seed, departments in DEPT_ALIAS.items():
        if seed in text:
            direct.extend(departments)
    uniq = []
    for d in direct:
        if d not in uniq:
            uniq.append(d)
    if uniq:
        return uniq[:max_n]
    sorted_cats = sorted(category_scores.items(), key=lambda x: x[1], reverse=True)
    mapping = {
        '인문': ['국어국문학', '영어영문학'],
        '사회': ['미디어커뮤니케이션', '광고홍보학'],
        '자연': ['생명과학', '통계학'],
        '공학': ['컴퓨터공학', '전자공학']
    }
    recs = []
    for cat, _ in sorted_cats:
        for d in mapping.get(cat, []):
            if d not in recs:
                recs.append(d)
            if len(recs) >= max_n:
                return recs
    return recs[:max_n]


def major_match_score(target_departments: List[str], major_categories: Dict[str, List[str]]) -> Tuple[float, List[str]]:
    majors_flat = []
    for vals in major_categories.values():
        majors_flat.extend(vals)
    score = 0.0
    matched = []
    for target in target_departments:
        for major in majors_flat:
            if target == major:
                score += 30
                matched.append(major)
            elif target in major or major in target:
                score += 20
                matched.append(major)
            elif target.startswith('미디어') and any(k in major for k in ['미디어', '언론', '광고', '방송']):
                score += 18
                matched.append(major)
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
    if signals.get('target_university') and signals['target_university'] in university_name:
        return 12.0
    return 0.0


def recommend_universities(db: Dict, signals: Dict, target_departments: List[str], top_n: int = 6) -> List[Dict]:
    recs = []
    gscore = grade_fit_score(signals.get('overall_grade'))
    for u in db.get('universities', []):
        mscore, matched = major_match_score(target_departments, u.get('major_categories', {}))
        if mscore <= 0:
            continue
        tscore = keyword_fit_score(signals, u.get('talent_keywords', []))
        bonus = target_bonus(u['name'], signals)
        total = round(mscore * 0.50 + tscore * 0.25 + gscore * 0.20 + bonus, 2)
        recs.append({
            'university': u['name'],
            'region': u.get('region'),
            'campus': u.get('campus'),
            'fit_score': total,
            'matched_departments': matched[:6],
            'talent_keywords': u.get('talent_keywords', []),
            'notes': u.get('notes', ''),
            'target_bonus': bonus,
            'major_score': round(mscore, 1),
            'talent_score': round(tscore, 1),
            'grade_score': round(gscore, 1)
        })
    recs.sort(key=lambda x: x['fit_score'], reverse=True)
    return recs[:top_n]


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


def inject_css():
    st.markdown("""
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
    """, unsafe_allow_html=True)


def render_hero():
    st.markdown("""
    <div class='hero-box'>
      <div class='hero-title'>학생 HTML 기반 대학 추천 대시보드</div>
      <div class='hero-sub'>서울·경기권 대학 DB와 현재 예시 HTML 구조를 바탕으로 학과 및 대학 적합도를 시각적으로 정리합니다.</div>
    </div>
    """, unsafe_allow_html=True)


def render_metric_card(label: str, value: str, desc: str):
    st.markdown(f"""
    <div class='metric-card'>
      <div class='metric-label'>{label}</div>
      <div class='metric-value'>{value}</div>
      <div class='metric-desc'>{desc}</div>
    </div>
    """, unsafe_allow_html=True)


def render_chip_row(title: str, items: List[str], dept: bool = False):
    chip_class = 'dept-chip' if dept else 'tag-chip'
    chips = ''.join([f'<span class="{chip_class}">{item}</span>' for item in items if item])
    empty = '<div class="subtle">표시할 항목이 없습니다.</div>'
    st.markdown(f"<div class='glass-card'><div class='section-title'>{title}</div>{chips if chips else empty}</div>", unsafe_allow_html=True)


def render_university_card(rec: Dict, rank: int):
    fit_pct = max(0, min(100, int(rec['fit_score'])))
    major_pct = max(0, min(100, int(rec['major_score'] * 2.5)))
    talent_pct = max(0, min(100, int(rec['talent_score'])))
    grade_pct = max(0, min(100, int(rec['grade_score'])))
    matched = ''.join([f'<span class="tag-chip">{x}</span>' for x in rec['matched_departments']])
    talents = ''.join([f'<span class="tag-chip">{x}</span>' for x in rec['talent_keywords']])
    bonus_text = f"목표대학 가중치 +{rec['target_bonus']}" if rec.get('target_bonus') else '목표대학 가중치 없음'
    st.markdown(f"""
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
      <div class='section-title'>일치 학과군</div>
      <div>{matched if matched else '<span class="subtle">없음</span>'}</div>
      <div class='section-title' style='margin-top:0.8rem;'>인재상 키워드</div>
      <div>{talents if talents else '<span class="subtle">없음</span>'}</div>
      <div class='subtle' style='margin-top:0.9rem;'>{bonus_text}</div>
      <div class='subtle' style='margin-top:0.3rem;'>{rec.get('notes', '')}</div>
    </div>
    """, unsafe_allow_html=True)


def env_help_panel():
    st.markdown('### .env 설정 안내')
    st.code("""GEMINI_API_KEY=여기에_API_KEY
APP_PASSWORD_HASH=pbkdf2_sha256$240000$<salt_hex>$<hash_hex>""", language='bash')
    st.write('비밀번호 해시는 앱 내부 도구 또는 아래 스크립트로 생성할 수 있습니다.')
    st.code("""python -c "import secrets,hashlib; p='your_password'; s=secrets.token_bytes(16); i=240000; d=hashlib.pbkdf2_hmac('sha256', p.encode(), s, i); print(f'pbkdf2_sha256${i}${s.hex()}${d.hex()}')\"""", language='bash')


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
        render_metric_card('연결 DB', f"{len(db.get('universities', []))}개 대학", '서울·경기권 대학 데이터가 로드되었습니다.')
    with top2:
        render_metric_card('입력 형식', '학생 HTML', '현재 예시 리포트 구조에 맞춘 파서가 동작합니다.')
    with top3:
        render_metric_card('분석 방식', 'JSON + HTML', 'PDF 없이 구조화된 대학 DB와 학생 리포트만 사용합니다.')

    uploaded_html = st.file_uploader('학생 분석 HTML 업로드', type=['html', 'htm'])

    if uploaded_html is not None:
        html_text = uploaded_html.read().decode('utf-8', errors='ignore')
        signals = extract_example_specific_signals(html_text)
        category_scores = infer_category_scores(signals)
        target_departments = choose_target_departments(signals, category_scores, max_n=2)
        recs = recommend_universities(db, signals, target_departments, top_n=6)
        summary = summarize_with_gemini(signals, target_departments, recs)

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            render_metric_card('추천 학과 수', str(len(target_departments)), '요청 조건에 맞춰 최대 2개까지 제시합니다.')
        with m2:
            render_metric_card('추천 대학 수', str(len(recs)), '추천 결과는 최대 6개 대학까지 노출합니다.')
        with m3:
            render_metric_card('추정 전체 등급', str(signals.get('overall_grade') or '-'), 'HTML 서술에서 탐지한 대표 등급 값입니다.')
        with m4:
            render_metric_card('전형 적합도', signals.get('admission_preference') or '미탐지', '예시 HTML의 전형 서술을 우선 반영합니다.')

        left, right = st.columns([1.05, 1.35])
        with left:
            render_chip_row('우선 추천 학과', target_departments, dept=True)
            render_chip_row('핵심 키워드', signals.get('top_keywords', [])[:12])
            render_chip_row('학생 신호', [
                signals.get('preferred_track') or '희망 트랙 미탐지',
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
            if not recs:
                st.warning('현재 HTML에서 학과 또는 대학 적합 신호를 충분히 추출하지 못했습니다.')
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

if __name__ == '__main__':
    main()
