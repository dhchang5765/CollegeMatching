from typing import Dict, List

import streamlit as st

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
    admission_text = ""
    if rec.get("matched_admission_band"):
        admission_text = f"추천 근거 등급대: {rec['matched_admission_band']}"
    detail = rec.get("matched_department_detail") or {}
    detail_text = ""
    if detail.get("department"):
        detail_text = f"{detail.get('department')} / {detail.get('track_name') or '-'}"
        
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
      <div class="subtle" style="margin-top:0.35rem">{admission_text}</div>
      <div class="subtle" style="margin-top:0.2rem">{detail_text}</div>
    </div>
    """, unsafe_allow_html=True)


def env_help_panel():
    st.markdown('### .env 설정 안내')
    st.code("""GEMINI_API_KEY=여기에_API_KEY
APP_PASSWORD_HASH=pbkdf2_sha256$240000$<salt_hex>$<hash_hex>""", language='bash')
    st.write('비밀번호 해시는 앱 내부 도구 또는 아래 스크립트로 생성할 수 있습니다.')
    st.code("""python -c "import secrets,hashlib; p='your_password'; s=secrets.token_bytes(16); i=240000; d=hashlib.pbkdf2_hmac('sha256', p.encode(), s, i); print(f'pbkdf2_sha256${i}${s.hex()}${d.hex()}')\"""", language='bash')

