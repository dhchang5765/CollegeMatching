from typing import Dict, List, Optional

import streamlit as st
import plotly.graph_objects as go


def _clean_html(html: str) -> str:
    """
    각 줄의 선두/후미 공백과 빈 줄을 제거한다.
    Streamlit 의 st.markdown(unsafe_allow_html=True) 은 4칸 이상 들여쓰기된 줄을
    마크다운 코드 블록으로 오인해 HTML 원본을 그대로 출력한다. 이를 방지.
    """
    return "\n".join(line.strip() for line in html.splitlines() if line.strip())


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
        "#0d9488", "#0891b2", "#65a30d", "#7c6fd4", "#d97706",
        "#c2683f", "#0e9488", "#9a8c30", "#8b6db8", "#b45f3d",
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
      /* 따뜻한 슬레이트 + 차분한 틸(teal) 강조색 — 장시간 보기 편한 저채도 */
      --bg-app: linear-gradient(180deg, #f6f5f2 0%, #eef0ed 100%);
      --bg-card: #fffefb;
      --bg-card-glass: rgba(255,254,251,0.85);
      --bg-chip: #f3f4f1;
      --bg-dept-chip: #d8ede9;
      --bg-bar-track: #e4e6e1;
      --border: #e3e4df;
      --border-soft: rgba(120,130,125,0.20);
      --border-chip: #e0e2dd;
      --border-dept-chip: #a9d6cd;
      --text-primary: #1f2a2e;
      --text-body: #3c474b;
      --text-meta: #566065;
      --text-subtle: #6b7479;
      --text-on-pill: #ffffff;
      --text-dept-chip: #0f766e;
      --text-chip: #3c474b;
      --accent: #0d9488;
      --accent-strong: #0f766e;
      --shadow-soft: 0 12px 30px rgba(31,42,46,0.05);
      --shadow-mid:  0 18px 32px rgba(31,42,46,0.06);
      --shadow-strong: 0 18px 38px rgba(13,148,136,0.14);
    }

    /* ─── 색상 변수 (다크) — OS 설정 자동 반응 ─────── */
    @media (prefers-color-scheme: dark) {
      :root {
        --bg-app: linear-gradient(180deg, #14181a 0%, #1a2023 100%);
        --bg-card: #222a2d;
        --bg-card-glass: rgba(34,42,45,0.88);
        --bg-chip: #28312f;
        --bg-dept-chip: #134e4a;
        --bg-bar-track: #374151;
        --border: #374151;
        --border-soft: rgba(148,163,160,0.18);
        --border-chip: #374151;
        --border-dept-chip: #115e59;
        --text-primary: #ecefed;
        --text-body: #c8d0cd;
        --text-meta: #9aa5a2;
        --text-subtle: #97a2a0;
        --text-on-pill: #ffffff;
        --text-dept-chip: #5eead4;
        --text-chip: #c8d0cd;
        --accent: #2dd4bf;
        --accent-strong: #5eead4;
        --shadow-soft: 0 12px 30px rgba(0,0,0,0.38);
        --shadow-mid:  0 18px 32px rgba(0,0,0,0.42);
        --shadow-strong: 0 18px 38px rgba(13,148,136,0.28);
      }
    }

    /* ─── 컴포넌트 ─────────────────────────────────── */
    .stApp { background: var(--bg-app); }
    .hero-box { padding: 1.4rem 1.6rem; border-radius: 22px;
                background: linear-gradient(135deg, #1f2a2e 0%, #155e57 55%, #0d9488 100%);
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
    .score-pill { background: linear-gradient(135deg, #0f766e, #0d9488); color: var(--text-on-pill);
                  padding: 0.45rem 0.8rem; border-radius: 999px;
                  font-weight: 800; font-size: 0.9rem; white-space: nowrap; }

    .subtle { color: var(--text-subtle); font-size: 0.9rem; }
    .score-bar-wrap { margin-top: 0.4rem; margin-bottom: 0.55rem; }
    .score-bar-label { font-size: 0.82rem; color: var(--text-meta); margin-bottom: 0.2rem; }
    .score-bar { width: 100%; height: 10px; background: var(--bg-bar-track);
                 border-radius: 999px; overflow: hidden; }
    .score-fill { height: 10px; border-radius: 999px;
                  background: linear-gradient(90deg, #5eead4, #0d9488); }

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


def render_student_profile_card(profile: Dict):
    """
    학생 프로파일 4슬롯 카드 — '핵심 키워드' 대체.
    profile: { strengths, weaknesses, interests, risks, mode }
    """
    if not profile:
        return

    mode = profile.get("mode", "exploring")
    mode_label = "진로 명확" if mode == "clear" else "진로 탐색 단계"
    mode_color = "#16a34a" if mode == "clear" else "#ea580c"

    def slot_html(title, items, color, icon):
        if not items:
            content = "<span class='subtle' style='color:var(--text-subtle);'>—</span>"
        else:
            content = "".join(
                f"<span style='background:{color}18; color:{color}; border:1px solid {color}44; "
                f"padding:0.22rem 0.6rem; border-radius:999px; font-size:0.82rem; "
                f"font-weight:600; margin:0.15rem 0.25rem 0.15rem 0; display:inline-block;'>{item}</span>"
                for item in items
            )
        return f"""
        <div style='margin-bottom:0.7rem;'>
          <div style='font-size:0.78rem; font-weight:700; color:{color};
                      text-transform:uppercase; letter-spacing:0.03em; margin-bottom:0.3rem;'>
            {icon} {title}
          </div>
          <div>{content}</div>
        </div>
        """

    st.markdown(
        f"""
        <div style='margin-top:0.6rem;'>
          <div style='display:flex; justify-content:space-between; align-items:center;
                      margin-bottom:0.5rem;'>
            <div class='section-title' style='margin:0;'>학생 프로파일</div>
            <span style='background:{mode_color}22; color:{mode_color};
                         border:1px solid {mode_color}55; padding:0.18rem 0.55rem;
                         border-radius:999px; font-size:0.75rem; font-weight:700;'>
              {mode_label}
            </span>
          </div>
          {slot_html("강점", profile["strengths"], "#16a34a", "💪")}
          {slot_html("약점", profile["weaknesses"], "#dc2626", "⚠")}
          {slot_html("관심", profile["interests"], "#1d4ed8", "🎯")}
          {slot_html("위험 신호", profile["risks"], "#ea580c", "🚨")}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_chip_row(title: str, items: List[str], dept: bool = False):
    chip_class = 'dept-chip' if dept else 'tag-chip'
    chips = ''.join([f'<span class="{chip_class}">{item}</span>' for item in items if item])
    empty = '<div class="subtle">표시할 항목이 없습니다.</div>'
    st.markdown(f"<div class='glass-card'><div class='section-title'>{title}</div>{chips if chips else empty}</div>", unsafe_allow_html=True)


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


def render_admissions_detail_panel(departments_raw: List[Dict],
                                    student_grade: Optional[float] = None):
    """
    대학 카드 안에 펼침 패널로 전형별 상세 정보 표시.
    departments_raw: DB 의 universities[].departments[] 원본
    student_grade: 학생 등급 (있으면 합격선 비교 행 색칠)
    """
    if not departments_raw:
        return

    # 모든 admissions 를 평탄화 — 학과명·중심전형·전형명·정보
    flat_rows = []
    for d in departments_raw:
        dept_name = d.get("name", "")
        for adm in d.get("admissions", []):
            flat_rows.append({
                "dept": dept_name,
                "type": adm.get("type", ""),
                "track_name": adm.get("track_name", ""),
                "applicants": adm.get("applicants"),
                "competition": adm.get("competition_ratio"),
                "fill_rank": adm.get("fill_rank"),
                "p50": adm.get("cutoff_p50"),
                "p70": adm.get("cutoff_p70"),
                "p90": adm.get("cutoff_p90"),
                "subjects": adm.get("evaluated_subjects"),
            })

    if not flat_rows:
        return

    # 학생 등급과 가까운 순으로 정렬 (있을 때만)
    if student_grade is not None:
        flat_rows.sort(key=lambda r: abs((r["p50"] or 99) - student_grade))
    else:
        flat_rows.sort(key=lambda r: r["p50"] or 99)

    # 표 HTML 빌드
    def fmt(v, decimals=2):
        if v is None: return "—"
        if isinstance(v, float): return f"{v:.{decimals}f}"
        return str(v)

    rows_html = ""
    for r in flat_rows[:30]:  # 최대 30개 전형 표시
        # 학생 등급과의 거리로 행 색조 결정 (다크/라이트 모두 안전한 저투명도)
        bg = ""
        if student_grade is not None and r["p50"] is not None:
            dist = abs(r["p50"] - student_grade)
            if dist <= 0.3: bg = "background:rgba(22,163,74,0.12);"
            elif dist <= 0.7: bg = "background:rgba(13,148,136,0.12);"
            elif dist <= 1.2: bg = "background:rgba(234,88,12,0.10);"
        rows_html += f"""
        <tr style='{bg} border-bottom:1px solid var(--border);'>
          <td style='padding:0.3rem 0.5rem; font-size:0.78rem; color:var(--text-body);'>{r["dept"][:18]}</td>
          <td style='padding:0.3rem 0.5rem; font-size:0.78rem; color:var(--text-body);'>{r["type"][:6]}</td>
          <td style='padding:0.3rem 0.5rem; font-size:0.78rem; color:var(--text-body);'>{r["track_name"][:18]}</td>
          <td style='padding:0.3rem 0.5rem; font-size:0.78rem; text-align:right; color:var(--text-body);'>{fmt(r["applicants"], 0)}</td>
          <td style='padding:0.3rem 0.5rem; font-size:0.78rem; text-align:right; color:var(--text-body);'>{fmt(r["competition"])}</td>
          <td style='padding:0.3rem 0.5rem; font-size:0.78rem; text-align:right; color:var(--text-body);'>{fmt(r["fill_rank"], 1)}</td>
          <td style='padding:0.3rem 0.5rem; font-size:0.82rem; text-align:right; font-weight:800; color:var(--accent-strong);'>{fmt(r["p50"])}</td>
          <td style='padding:0.3rem 0.5rem; font-size:0.78rem; text-align:right; color:var(--text-meta);'>{fmt(r["p70"])}</td>
          <td style='padding:0.3rem 0.5rem; font-size:0.78rem; text-align:right; color:var(--text-meta);'>{fmt(r["p90"])}</td>
          <td style='padding:0.3rem 0.5rem; font-size:0.74rem; color:var(--text-subtle);'>{(r["subjects"] or "—")[:14]}</td>
        </tr>
        """

    table_html = f"""
    <div style='overflow-x:auto; margin-top:0.5rem;'>
      <table style='width:100%; border-collapse:collapse; font-size:0.78rem;'>
        <thead style='background:var(--bg-chip); border-bottom:2px solid var(--accent);'>
          <tr>
            <th style='padding:0.4rem 0.5rem; text-align:left; font-weight:700; color:var(--text-primary);'>모집단위</th>
            <th style='padding:0.4rem 0.5rem; text-align:left; font-weight:700; color:var(--text-primary);'>중심전형</th>
            <th style='padding:0.4rem 0.5rem; text-align:left; font-weight:700; color:var(--text-primary);'>전형명</th>
            <th style='padding:0.4rem 0.5rem; text-align:right; font-weight:700; color:var(--text-primary);'>인원</th>
            <th style='padding:0.4rem 0.5rem; text-align:right; font-weight:700; color:var(--text-primary);'>경쟁률</th>
            <th style='padding:0.4rem 0.5rem; text-align:right; font-weight:700; color:var(--text-primary);'>충원순위</th>
            <th style='padding:0.4rem 0.5rem; text-align:right; font-weight:800; color:var(--accent-strong); background:var(--bg-dept-chip);'>50%</th>
            <th style='padding:0.4rem 0.5rem; text-align:right; font-weight:700; color:var(--text-primary);'>70%</th>
            <th style='padding:0.4rem 0.5rem; text-align:right; font-weight:700; color:var(--text-primary);'>90%</th>
            <th style='padding:0.4rem 0.5rem; text-align:left; font-weight:700; color:var(--text-primary);'>학종 반영 교과</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
      <div style='margin-top:0.4rem; font-size:0.72rem; color:var(--text-subtle);'>
        · 등급 50%/70%/90% cut 은 최종 등록자 교과 등급 분포 / 5년 인원 가중평균<br>
        · 50% cut(기준열)이 핵심 합격선이며, 학생 등급과의 거리에 따라 행 색조: 초록=±0.3, 청록=±0.7, 주황=±1.2 이내<br>
        · 전형이 많은 경우 학생 등급에 가까운 순서로 최대 30개만 표시
      </div>
    </div>
    """
    st.markdown(_clean_html(table_html), unsafe_allow_html=True)


def render_grade_based_card(rec: Dict, rank: int, student_grade: Optional[float] = None):
    """등급 기반 추천 대학 카드."""
    support_level = rec.get("support_level", "")
    level_colors = {
        "안정": "#16a34a", "적정": "#1d4ed8",
        "상향": "#ea580c", "상향(도전)": "#dc2626",
    }
    color = level_colors.get(support_level, "#64748b")

    talents = "".join([f'<span class="tag-chip">{x}</span>'
                       for x in (rec.get("talent_keywords") or [])[:5]])
    talent_statement = rec.get("talent_statement", "") or ""

    # 학과별 최저 cutoff 분포 (top 6)
    dept_rows = ""
    for d in rec.get("all_departments_summary", []):
        dist = abs((d["min_cutoff"] or 99) - (student_grade or 0)) if student_grade else None
        marker = ""
        if dist is not None:
            if dist <= 0.3: marker = "🟢"
            elif dist <= 0.7: marker = "🔵"
            elif dist <= 1.2: marker = "🟠"
        dept_rows += f"""
        <div style='display:flex; justify-content:space-between;
                    font-size:0.78rem; padding:0.18rem 0; border-bottom:1px solid var(--border, #e5e7eb);'>
          <span style='color:var(--text-body);'>{marker} {d["dept"][:24]} <span class='subtle' style='font-size:0.7rem;'>({d.get("category","")})</span></span>
          <span style='font-weight:600; color:{color};'>{d["min_cutoff"]:.2f}</span>
        </div>
        """

    _card = f"""
    <div class='recommend-card'>
      <div class='recommend-head'>
        <div>
          <div class='subtle'>추천 {rank}
            <span style='background:{color}22; color:{color}; border:1px solid {color}55; padding:0.18rem 0.5rem; border-radius:999px; font-size:0.72rem; font-weight:700; margin-left:0.4rem;'>{support_level}</span>
          </div>
          <div class='recommend-title'>{rec['university']}</div>
          <div class='subtle'>{rec.get('region', '')} · 학과 {rec.get('department_count', 0)}개</div>
        </div>
        <div class='score-pill' style='background:{color}; color:white;'>
          최저 합격선 {rec['representative_cutoff']:.2f}
        </div>
      </div>
      <div class='subtle' style='margin-top:0.4rem; font-size:0.78rem;'>
        대표 학과: <b>{rec.get('representative_dept', '')}</b> · {rec.get('representative_track', '')} · 학생 등급과 거리 <b>{rec['grade_distance']:.2f}</b>
      </div>
      <div class='section-title' style='margin-top:0.7rem;'>학과별 최저 합격선 (상위 6개)</div>
      {dept_rows}
      <div class='section-title' style='margin-top:0.8rem;'>인재상 키워드</div>
      <div>{talents if talents else '<span class="subtle">없음</span>'}</div>
      {("<div class='subtle' style='font-size:0.76rem; margin-top:0.5rem; font-style:italic;'>" + talent_statement + "</div>") if talent_statement else ""}
    </div>
    """
    st.markdown(_clean_html(_card), unsafe_allow_html=True)


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
          <div class='subtle'>{rec['region']}</div>
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

