from typing import Dict, List

import streamlit as st
import plotly.graph_objects as go


def render_category_donut(category_scores: Dict[str, float]):
    """
    계열 적합도를 도넛 차트로 표시.
    - 양수 점수만 사용
    - 비율 10% 미만 항목은 "기타"로 통합 (또는 생략)
    - 색상 팔레트는 블루-그린-퍼플 계열
    """
    # 양수만 집계
    positives = [(k, v) for k, v in category_scores.items() if v > 0]
    if not positives:
        st.markdown(
            "<div class='glass-card'><div class='section-title'>계열 적합도</div>"
            "<div class='subtle'>표시할 계열 점수가 없습니다.</div></div>",
            unsafe_allow_html=True
        )
        return

    total = sum(v for _, v in positives)
    # 비율 계산 후 10% 미만은 제외
    threshold = 0.10
    major = [(k, v) for k, v in positives if v / total >= threshold]
    # 모두 10% 미만이면 상위 3개만이라도 표시
    if not major:
        major = sorted(positives, key=lambda x: -x[1])[:3]

    major.sort(key=lambda x: -x[1])
    labels = [k for k, _ in major]
    values = [v for _, v in major]

    palette = [
        "#2563eb", "#0ea5e9", "#10b981", "#8b5cf6", "#f59e0b",
        "#ef4444", "#06b6d4", "#84cc16", "#a855f7", "#f97316",
    ]
    colors = palette[: len(labels)]

    fig = go.Figure(data=[
        go.Pie(
            labels=labels,
            values=values,
            hole=0.55,
            marker=dict(colors=colors, line=dict(color="white", width=2)),
            textinfo="percent",
            textfont=dict(size=13, color="white", family="sans-serif"),
            hovertemplate="<b>%{label}</b><br>점수: %{value:.1f}<br>비율: %{percent}<extra></extra>",
            sort=False,
        )
    ])
    fig.update_layout(
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.05,
            xanchor="center",
            x=0.5,
            font=dict(size=12, color="#94a3b8"),
        ),
        margin=dict(t=10, b=10, l=10, r=10),
        height=380,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )

    st.markdown(
        "<div class='glass-card'><div class='section-title'>계열 적합도 (상위 비중)</div>",
        unsafe_allow_html=True
    )
    st.plotly_chart(fig, width='stretch', config={"displayModeBar": False})
    # 제외된 항목 안내
    omitted = [k for k, v in positives if (k, v) not in major]
    if omitted:
        st.markdown(
            f"<div class='subtle' style='margin-top:-0.5rem;'>10% 미만 항목 제외: "
            f"{', '.join(omitted[:8])}{' ...' if len(omitted)>8 else ''}</div>",
            unsafe_allow_html=True
        )
    st.markdown("</div>", unsafe_allow_html=True)


def inject_css():
    st.markdown("""
    <style>
    /* ─── 색상 변수 (라이트) ─────────────────────────── */
    :root {
      --bg-app: linear-gradient(180deg, #f5f7fb 0%, #edf2f7 100%);
      --bg-card: #ffffff;
      --bg-card-glass: rgba(255,255,255,0.82);
      --bg-chip: #f8fafc;
      --bg-dept-chip: #dbeafe;
      --bg-bar-track: #e2e8f0;
      --border: #e5e7eb;
      --border-soft: rgba(148,163,184,0.22);
      --border-chip: #e2e8f0;
      --border-dept-chip: #bfdbfe;
      --text-primary: #0f172a;
      --text-body: #334155;
      --text-meta: #475569;
      --text-subtle: #64748b;
      --text-on-pill: #ffffff;
      --text-dept-chip: #1d4ed8;
      --text-chip: #334155;
      --shadow-soft: 0 12px 30px rgba(15,23,42,0.06);
      --shadow-mid:  0 18px 32px rgba(15,23,42,0.06);
      --shadow-strong: 0 20px 40px rgba(37,99,235,0.18);
    }

    /* ─── 색상 변수 (다크) — OS 설정 자동 반응 ─────── */
    @media (prefers-color-scheme: dark) {
      :root {
        --bg-app: linear-gradient(180deg, #0b1220 0%, #111827 100%);
        --bg-card: #1e293b;
        --bg-card-glass: rgba(30,41,59,0.85);
        --bg-chip: #1e293b;
        --bg-dept-chip: #1e3a8a;
        --bg-bar-track: #334155;
        --border: #334155;
        --border-soft: rgba(148,163,184,0.18);
        --border-chip: #334155;
        --border-dept-chip: #2563eb;
        --text-primary: #f1f5f9;
        --text-body: #cbd5e1;
        --text-meta: #94a3b8;
        --text-subtle: #94a3b8;
        --text-on-pill: #ffffff;
        --text-dept-chip: #93c5fd;
        --text-chip: #cbd5e1;
        --shadow-soft: 0 12px 30px rgba(0,0,0,0.35);
        --shadow-mid:  0 18px 32px rgba(0,0,0,0.4);
        --shadow-strong: 0 20px 40px rgba(37,99,235,0.30);
      }
    }

    /* ─── 컴포넌트 ─────────────────────────────────── */
    .stApp { background: var(--bg-app); }
    .hero-box { padding: 1.4rem 1.6rem; border-radius: 22px;
                background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 55%, #2563eb 100%);
                color: #fff; box-shadow: var(--shadow-strong); margin-bottom: 1rem; }
    .hero-title { font-size: 1.75rem; font-weight: 800; margin-bottom: 0.35rem; color: #fff; }
    .hero-sub { font-size: 0.98rem; opacity: 0.9; color: #fff; }

    .glass-card { background: var(--bg-card-glass); border: 1px solid var(--border-soft);
                  border-radius: 18px; padding: 1rem 1.1rem; box-shadow: var(--shadow-soft); }
    .metric-card { background: var(--bg-card); border-radius: 18px;
                   padding: 1rem 1rem 0.9rem 1rem; border: 1px solid var(--border);
                   box-shadow: var(--shadow-soft); min-height: 120px; }
    .metric-label { color: var(--text-subtle); font-size: 0.82rem; margin-bottom: 0.4rem; }
    .metric-value { font-size: 1.4rem; font-weight: 800; color: var(--text-primary); margin-bottom: 0.35rem; }
    .metric-desc { color: var(--text-meta); font-size: 0.9rem; line-height: 1.4; }

    .section-title { font-size: 1.1rem; font-weight: 800; color: var(--text-primary);
                     margin: 0.2rem 0 0.8rem 0; }

    .dept-chip { display: inline-block; background: var(--bg-dept-chip); color: var(--text-dept-chip);
                 border: 1px solid var(--border-dept-chip); padding: 0.45rem 0.7rem;
                 border-radius: 999px; margin: 0.2rem 0.35rem 0.2rem 0;
                 font-weight: 700; font-size: 0.9rem; }
    .tag-chip { display: inline-block; background: var(--bg-chip); color: var(--text-chip);
                border: 1px solid var(--border-chip); padding: 0.35rem 0.6rem;
                border-radius: 999px; margin: 0.18rem 0.32rem 0.18rem 0; font-size: 0.84rem; }

    .recommend-card { background: var(--bg-card); border-radius: 22px;
                      padding: 1.15rem 1.2rem; border: 1px solid var(--border-chip);
                      box-shadow: var(--shadow-mid); margin-bottom: 1rem; }
    .recommend-head { display: flex; justify-content: space-between; align-items: center;
                      gap: 1rem; margin-bottom: 0.75rem; }
    .recommend-title { font-size: 1.12rem; font-weight: 800; color: var(--text-primary); }
    .score-pill { background: linear-gradient(135deg, #1d4ed8, #2563eb); color: var(--text-on-pill);
                  padding: 0.45rem 0.8rem; border-radius: 999px;
                  font-weight: 800; font-size: 0.9rem; white-space: nowrap; }

    .subtle { color: var(--text-subtle); font-size: 0.9rem; }
    .score-bar-wrap { margin-top: 0.4rem; margin-bottom: 0.55rem; }
    .score-bar-label { font-size: 0.82rem; color: var(--text-meta); margin-bottom: 0.2rem; }
    .score-bar { width: 100%; height: 10px; background: var(--bg-bar-track);
                 border-radius: 999px; overflow: hidden; }
    .score-fill { height: 10px; border-radius: 999px;
                  background: linear-gradient(90deg, #60a5fa, #1d4ed8); }

    .login-wrap { max-width: 420px; margin: 2rem auto 0 auto; padding: 1rem;
                  background: var(--bg-card-glass); border-radius: 20px;
                  border: 1px solid var(--border-soft); box-shadow: var(--shadow-soft); }

    /* ─── Streamlit 위젯 색 보정 (다크에서 입력칸·라벨 가독성) ── */
    @media (prefers-color-scheme: dark) {
        /* 본문 텍스트 기본색을 다크에서도 강제 (Streamlit 기본 검정 방지) */
        .stMarkdown, .stMarkdown p, .stMarkdown li,
        [data-testid="stMarkdownContainer"] { color: var(--text-body) !important; }
        /* 도넛 차트가 흰 배경 카드 안에 있을 때 글자가 안 보이는 문제 방지 */
        .js-plotly-plot .plotly text { fill: var(--text-body) !important; }
        /* st.success/info/warning 박스 가독성 보정 */
        [data-testid="stAlertContainer"] { color: var(--text-body); }
    }

    /* ─── PDF 인쇄 친화 (라이트 강제) ───────────────── */
    .recommend-card, .glass-card { page-break-inside: avoid; break-inside: avoid; }
    .section-title { page-break-after: avoid; break-after: avoid; }
    @media print {
        :root {
            --bg-app: #ffffff; --bg-card: #ffffff; --bg-card-glass: #ffffff;
            --bg-chip: #f8fafc; --bg-dept-chip: #dbeafe; --bg-bar-track: #e2e8f0;
            --border: #cbd5e1; --border-soft: #cbd5e1; --border-chip: #e2e8f0;
            --text-primary: #0f172a; --text-body: #334155; --text-meta: #475569;
            --text-subtle: #64748b;
        }
        .stApp { background: white !important; }
        .hero-box { box-shadow: none !important; }
        .recommend-card, .glass-card { box-shadow: none !important; }
        header, footer, [data-testid="stToolbar"], [data-testid="stSidebar"] { display: none !important; }
    }
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


def render_score_methodology():
    """대학 적합도 점수 산출 방식을 사용자에게 간단히 설명."""
    st.markdown(
        """
<div class='glass-card'>
  <div class='section-title'>적합도 점수는 어떻게 계산되나요?</div>
  <div class='subtle' style='font-size:0.92rem; line-height:1.7; color:var(--text-body);'>
    각 대학의 적합도는 <b>0~100점</b>으로, 네 가지 항목에 가중치를 곱해
    합산한 뒤 보너스를 더해 산출합니다.
  </div>
  <div style='margin-top:0.7rem; display:flex; flex-wrap:wrap; gap:0.4rem;'>
    <span class='tag-chip'>학과 일치도 50%</span>
    <span class='tag-chip'>등급대 적합 23%</span>
    <span class='tag-chip'>인재상 부합 15%</span>
    <span class='tag-chip'>기본 성적 12%</span>
    <span class='tag-chip'>+ 보너스 최대 25점</span>
  </div>
  <div class='subtle' style='font-size:0.88rem; line-height:1.7; margin-top:0.7rem; color:var(--text-meta);'>
    · <b>학과 일치도</b> — 학생의 추천 학과가 그 대학에 실제로 있는지·얼마나 가까운지<br>
    · <b>등급대 적합</b> — 학생 등급이 그 학과 전형의 합격 등급대에 드는지<br>
    · <b>인재상 부합</b> — 대학이 명시한 인재상 키워드와 학생 신호의 겹침<br>
    · <b>기본 성적</b> — 전반적 내신 수준 반영<br>
    · <b>보너스</b> — 목표 대학 일치, 계열 클러스터 적합 시 가산
  </div>
  <div class='subtle' style='font-size:0.84rem; margin-top:0.7rem; color:var(--text-subtle);'>
    점수 = (학과 × 0.50 + 등급대 × 0.23 + 인재상 × 0.15 + 성적 × 0.12) + 보너스,
    100점 상한. 동일 입력은 항상 동일 점수를 냅니다(결정론적).
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_university_card(rec: Dict, rank: int):
    fit_pct = max(0, min(100, int(rec['fit_score'])))
    # major_score는 이미 0~100 정규화된 값 (recommend_universities에서 처리)
    major_pct = max(0, min(100, int(rec['major_score'])))
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