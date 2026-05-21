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


def render_roadmap_panel(roadmap: Dict, univ_name: str):
    """대학 카드 안에 펼침 패널로 로드맵 표시."""
    if not roadmap:
        return
    grade_level = roadmap.get("grade_level") or "학년 미확정"
    gaps = roadmap.get("gaps", {})
    schedule = roadmap.get("schedule", [])
    actions = roadmap.get("actions", [])
    timeline = roadmap.get("timeline", {})

    # 갭 요약 배지
    gap_chips = []
    sev = gaps.get("grade_severity")
    if sev == "safe":
        gap_chips.append(("등급 안전", "#16a34a"))
    elif sev == "small":
        gap_chips.append((f"등급 갭 {gaps.get('grade_gap')}", "#ea580c"))
    elif sev == "medium":
        gap_chips.append((f"등급 갭 {gaps.get('grade_gap')} (중간)", "#dc2626"))
    elif sev == "large":
        gap_chips.append((f"등급 갭 {gaps.get('grade_gap')} (큼)", "#991b1b"))
    if gaps.get("talent_gap") and gaps["talent_gap"] > 0.5:
        gap_chips.append((f"인재상 미매칭 {int(gaps['talent_gap']*100)}%", "#7c3aed"))
    if gaps.get("track_top_label"):
        gap_chips.append((f"우선 전형: {gaps['track_top_label']}", "#1d4ed8"))

    gap_chip_html = "".join(
        f"<span style='background:{c}22; color:{c}; border:1px solid {c}55; "
        f"padding:0.2rem 0.55rem; border-radius:999px; font-size:0.78rem; "
        f"font-weight:700; margin:0.15rem 0.2rem 0.15rem 0;'>{txt}</span>"
        for txt, c in gap_chips
    ) or "<span class='subtle'>갭 정보 부족</span>"

    # 분기별 스케줄 — 분기 라벨로 그룹화
    by_quarter: Dict[str, List[Dict]] = {}
    for s in schedule:
        by_quarter.setdefault(s["quarter_label"], []).append(s)

    quarter_html_blocks = []
    for q_info in timeline.get("quarters", []):
        q_label = q_info["label"]
        items = by_quarter.get(q_label, [])
        if not items:
            continue
        action_lines = "".join(
            f"<li style='font-size:0.85rem; color:var(--text-body); "
            f"margin:0.2rem 0; line-height:1.5;'>"
            f"<span style='color:var(--text-faint, var(--text-subtle)); "
            f"font-size:0.72rem; margin-right:0.4rem;'>[{it['action_title'][:14]}]</span>"
            f"{it['milestone']}</li>"
            for it in items
        )
        quarter_html_blocks.append(f"""
        <div style='margin-bottom:0.7rem;'>
          <div style='font-weight:700; color:var(--accent, #2563eb); font-size:0.82rem;
                      margin-bottom:0.3rem;'>{q_label}</div>
          <ul style='margin:0; padding-left:1.1rem;'>{action_lines}</ul>
        </div>
        """)

    # 처방 출처 박스
    sources_html = "".join(
        f"<div style='font-size:0.72rem; color:var(--text-subtle); "
        f"margin:0.1rem 0;'>· <b>{a.get('title','')[:30]}</b>: "
        f"{a.get('source_basis','—')}</div>"
        for a in actions
    )

    with st.expander(f"📋 {univ_name} 학습 갭 로드맵 보기", expanded=False):
        st.markdown(
            f"""
            <div style='padding:0.4rem 0;'>
              <div class='subtle' style='font-size:0.82rem; margin-bottom:0.5rem;'>
                학년: <b>{grade_level}</b> · 대입까지 약
                <b>{timeline.get('d_day_months','?')}</b>개월 ·
                전체 분기 {len(timeline.get('quarters', []))}개
              </div>
              <div style='margin-bottom:0.7rem;'>{gap_chip_html}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if quarter_html_blocks:
            st.markdown(
                "<div class='section-title' style='font-size:0.92rem; margin-top:0.5rem;'>"
                "분기별 행동 계획</div>",
                unsafe_allow_html=True,
            )
            st.markdown("".join(quarter_html_blocks), unsafe_allow_html=True)
        else:
            st.markdown(
                "<div class='subtle'>현재 분석된 갭에 대한 추천 행동이 없습니다.</div>",
                unsafe_allow_html=True,
            )
        if sources_html:
            st.markdown(
                f"<div style='margin-top:0.7rem; padding-top:0.6rem; "
                f"border-top:1px solid var(--border);'>"
                f"<div class='subtle' style='font-size:0.78rem; font-weight:700; "
                f"margin-bottom:0.3rem;'>처방 출처 (정책·통계 근거)</div>"
                f"{sources_html}</div>",
                unsafe_allow_html=True,
            )
        st.markdown(
            f"<div class='subtle' style='font-size:0.74rem; margin-top:0.7rem; "
            f"font-style:italic;'>⚠ {roadmap.get('disclaimer','')}</div>",
            unsafe_allow_html=True,
        )


def render_track_recommendations(track_recs: List[Dict], student_area: str = None):
    """A3 — 학생별 추천 전형 카드를 표시."""
    if not track_recs:
        return
    top = track_recs[:3]
    region_hint = f" · 거주 권역 추정: {student_area}" if student_area else ""

    cards_html = []
    for i, t in enumerate(top, start=1):
        score = int(round(t["score"]))
        reasons = "".join(
            f"<li style='color:var(--text-meta);font-size:0.85rem;'>{r}</li>"
            for r in t.get("reasons", [])[:3]
        ) or "<li class='subtle'>—</li>"
        cautions = "".join(
            f"<li style='color:#f59e0b;font-size:0.82rem;'>⚠ {c}</li>"
            for c in t.get("cautions", [])[:2]
        )
        # 점수에 따른 색상
        if score >= 75: pill_color = "linear-gradient(135deg,#16a34a,#22c55e)"
        elif score >= 55: pill_color = "linear-gradient(135deg,#1d4ed8,#3b82f6)"
        else: pill_color = "linear-gradient(135deg,#94a3b8,#cbd5e1)"
        cards_html.append(f"""
        <div style='background:var(--bg-card); border:1px solid var(--border);
                    border-radius:14px; padding:0.9rem 1rem;'>
          <div style='display:flex;justify-content:space-between;align-items:flex-start;
                      gap:0.5rem; margin-bottom:0.5rem;'>
            <div>
              <div style='font-size:0.72rem; color:var(--text-faint, var(--text-subtle));
                          font-weight:700; text-transform:uppercase; letter-spacing:0.05em;'>전형 {i}</div>
              <div style='font-size:1rem; font-weight:800; color:var(--text-primary);'>{t["label"]}</div>
            </div>
            <div style='background:{pill_color}; color:white; padding:0.35rem 0.7rem;
                        border-radius:999px; font-weight:800; font-size:0.85rem;'>적합도 {score}</div>
          </div>
          <ul style='margin:0.3rem 0 0 1rem; padding:0;'>{reasons}{cautions}</ul>
        </div>
        """)

    st.markdown(
        f"""
        <div class='section-title' style='margin-top:1.2rem;'>추천 전형{region_hint}</div>
        <div style='display:grid; grid-template-columns: repeat(3, 1fr); gap:0.8rem;
                    margin-bottom:0.8rem;'>
          {"".join(cards_html)}
        </div>
        """,
        unsafe_allow_html=True
    )


def render_support_level_header(level: str, count: int):
    """A2 — 지원군 그룹 헤더."""
    colors = {
        "안정":      ("#16a34a", "🛡️", "내 등급이 합격선보다 좋은 대학"),
        "적정":      ("#1d4ed8", "🎯", "내 등급이 합격선 범위 안인 대학"),
        "상향":      ("#ea580c", "📈", "노력하면 합격 가능한 대학"),
        "상향(도전)": ("#dc2626", "🚀", "도전적으로 지원할 대학"),
        "재고":      ("#94a3b8", "⚠️", "현재 등급으로는 어려운 대학"),
        "정보부족":  ("#94a3b8", "❔", "합격선 데이터 부족"),
    }
    color, icon, desc = colors.get(level, ("#64748b", "•", ""))
    st.markdown(
        f"""<div style='margin: 1rem 0 0.6rem 0; padding: 0.55rem 0.9rem;
                    border-left: 4px solid {color}; background: {color}11;
                    border-radius: 6px;'>
          <span style='font-size:1rem;'>{icon}</span>
          <span style='font-weight:800; color:{color}; margin-left:0.35rem;'>{level}</span>
          <span style='color:var(--text-meta); margin-left:0.5rem; font-size:0.85rem;'>{count}개 · {desc}</span>
        </div>""",
        unsafe_allow_html=True
    )


def render_score_methodology():
    """대학 적합도 점수 산출 방식을 사용자에게 간단히 설명."""
    st.markdown(
        """
<div class='glass-card'>
  <div class='section-title'>적합도 점수는 어떻게 계산되나요?</div>
  <div class='subtle' style='font-size:0.92rem; line-height:1.7; color:var(--text-body);'>
    각 대학의 적합도는 <b>0~100점</b>으로, 네 가지 객관 지표에 가중치를 곱해
    합산한 뒤 보너스를 더해 산출합니다.
  </div>
  <div style='margin-top:0.7rem; display:flex; flex-wrap:wrap; gap:0.4rem;'>
    <span class='tag-chip'>합격선 적합도 35%</span>
    <span class='tag-chip'>진로 일치도 25%</span>
    <span class='tag-chip'>전형 적합도 25%</span>
    <span class='tag-chip'>인재상 유사도 15%</span>
    <span class='tag-chip'>+ 보너스 최대 25점</span>
  </div>
  <div class='subtle' style='font-size:0.88rem; line-height:1.7; margin-top:0.7rem; color:var(--text-meta);'>
    · <b>합격선 적합도</b> — 학생 등급이 그 학과 전형의 합격 등급대에 어느 정도 부합하는지 (객관)<br>
    · <b>진로 일치도</b> — 학생 추천 학과 1·2·3순위가 그 대학에 존재하는지 (우선순위 가중)<br>
    · <b>전형 적합도</b> — 학생의 추천 전형(학종·교과·논술·정시 등) Top1이 그 대학에 있는지<br>
    · <b>인재상 유사도</b> — 학생 신호와 대학 인재상의 의미 유사도를 후보 대학 풀 내에서 상대 순위로 환산<br>
    · <b>보너스</b> — 목표 대학 일치, 진로 클러스터 적합, 추천 학과 2개 이상 매칭 시 가산
  </div>
  <div class='subtle' style='font-size:0.84rem; margin-top:0.7rem; color:var(--text-subtle);'>
    점수 = (합격선 × 0.35 + 진로 × 0.25 + 전형 × 0.25 + 인재상 × 0.15) + 보너스,
    100점 상한. 동일 입력은 항상 동일 점수를 냅니다(결정론적).
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_university_card(rec: Dict, rank: int):
    fit_pct = max(0, min(100, int(rec['fit_score'])))
    band_pct = max(0, min(100, int(rec.get('band_score', 50))))
    career_pct = max(0, min(100, int(rec.get('career_score', 50))))
    track_pct = max(0, min(100, int(rec.get('track_score', 50))))
    talent_pct = max(0, min(100, int(rec.get('talent_score', 50))))
    talents = ''.join([f'<span class="tag-chip">{x}</span>' for x in rec['talent_keywords']])
    bonus_text = f"목표대학 가중치 +{rec['target_bonus']}" if rec.get('target_bonus') else '목표대학 가중치 없음'
    admission_text = ""
    if rec.get("matched_admission_band"):
        admission_text = f"추천 근거 등급대: {rec['matched_admission_band']}"
    detail = rec.get("matched_department_detail") or {}
    detail_text = ""
    if detail.get("department"):
        detail_text = f"{detail.get('department')} / {detail.get('track_name') or '-'}"

    # A2: 지원군 라벨 배지
    support_level = rec.get("support_level") or ""
    support_reason = rec.get("support_reason") or ""
    level_colors = {
        "안정": "#16a34a", "적정": "#1d4ed8", "상향": "#ea580c",
        "상향(도전)": "#dc2626", "재고": "#94a3b8", "정보부족": "#94a3b8",
    }
    lvl_color = level_colors.get(support_level, "#64748b")
    support_badge = (
        f"<span style='background:{lvl_color}22; color:{lvl_color}; "
        f"border:1px solid {lvl_color}55; padding:0.18rem 0.5rem; border-radius:999px; "
        f"font-size:0.72rem; font-weight:700; margin-left:0.4rem;'>{support_level}</span>"
        if support_level else ""
    )

    # 인재상 적합도 백엔드 표시 (워드 임베딩 vs 키워드)
    backend_note = ""
    backend = rec.get("talent_backend", "")
    if "embedding" in backend:
        backend_note = " <span class='subtle' style='font-size:0.72rem;'>(워드 임베딩·상대)</span>"
    elif "keyword" in backend:
        backend_note = " <span class='subtle' style='font-size:0.72rem;'>(키워드)</span>"

    # 진로 매칭 학과 수 표시
    match_count = rec.get("career_matched_count", 0)
    match_count_text = f" ({match_count}/3 매칭)" if match_count else ""

    st.markdown(f"""
    <div class='recommend-card'>
      <div class='recommend-head'>
        <div>
          <div class='subtle'>추천 {rank} {support_badge}</div>
          <div class='recommend-title'>{rec['university']}</div>
          <div class='subtle'>{rec['region']} · {rec['campus'] if rec['campus'] else '단일 캠퍼스/미표기'}</div>
          {("<div class='subtle' style='font-size:0.76rem; margin-top:0.2rem;'>"+support_reason+"</div>") if support_reason else ""}
        </div>
        <div class='score-pill'>적합도 {rec['fit_score']}</div>
      </div>
      <div class='score-bar-wrap'><div class='score-bar-label'>총 적합도</div><div class='score-bar'><div class='score-fill' style='width:{fit_pct}%'></div></div></div>
      <div class='score-bar-wrap'><div class='score-bar-label'>합격선 적합도 <span class='subtle' style='font-size:0.72rem;'>(35%)</span></div><div class='score-bar'><div class='score-fill' style='width:{band_pct}%'></div></div></div>
      <div class='score-bar-wrap'><div class='score-bar-label'>진로 일치도 <span class='subtle' style='font-size:0.72rem;'>(25%){match_count_text}</span></div><div class='score-bar'><div class='score-fill' style='width:{career_pct}%'></div></div></div>
      <div class='score-bar-wrap'><div class='score-bar-label'>전형 적합도 <span class='subtle' style='font-size:0.72rem;'>(25%)</span></div><div class='score-bar'><div class='score-fill' style='width:{track_pct}%'></div></div></div>
      <div class='score-bar-wrap'><div class='score-bar-label'>인재상 유사도{backend_note} <span class='subtle' style='font-size:0.72rem;'>(15%)</span></div><div class='score-bar'><div class='score-fill' style='width:{talent_pct}%'></div></div></div>
      <div class='section-title' style='margin-top:0.7rem;'>인재상 키워드</div>
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

