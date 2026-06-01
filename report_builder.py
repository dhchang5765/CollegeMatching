"""
report_builder.py
─────────────────────────────────────────────────────────────────────
app.py 에서 분리 — 요약 생성과 다운로드용 HTML 직렬화.
  · fallback_summary / summarize_with_gemini
  · build_recommendation_html        : 전체 상세 리포트(기존)
  · build_compact_recommendation_html : 추천 대학 + 근거만 담은 요약본(신규)

함수 본문은 원본과 동일(동작 보존). 신규 요약본만 하단에 추가.
"""
from __future__ import annotations
import html as _html
import re
from datetime import datetime
from typing import Dict, List, Optional

from constants import GEMINI_MODEL
from password import get_secret_value

try:
    from google import genai
except ImportError:
    genai = None


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

def build_recommendation_html(recs: List[Dict],
                              target_departments: List[str],
                              signals: Dict,
                              summary: str,
                              category_scores: Dict[str, float],
                              grade_recs: Optional[List[Dict]] = None,
                              student_top_categories: Optional[List[str]] = None) -> str:
    """
    추천 카드 화면을 독립 HTML 파일로 직렬화.
    Streamlit 의존 없이 어떤 브라우저에서도 열림.
    """
    import html as _html
    from datetime import datetime

    def esc(s):
        return _html.escape(str(s)) if s is not None else ""

    meta = signals.get("report_meta", {}) or {}
    student = esc(meta.get("student_name") or "학생")
    today = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 학생 신호 칩
    tracks = signals.get("detected_tracks") or []
    track_label = f"선호 트랙: {', '.join(tracks)}" if tracks else "선호 트랙: 미탐지"
    target_univ = signals.get('target_university')
    target_label = f"목표 대학: {target_univ}" if target_univ else "목표 대학: 미탐지"
    raw_chips = [
        track_label, target_label,
        f"전형 성향: {signals.get('admission_orientation', '미탐지')}",
        '논술/글쓰기 강점' if signals.get('essay_strength') else '논술 강점 미탐지',
        '영어 강점' if signals.get('english_strength') else '영어 강점 미탐지',
        '수학 위험 신호' if signals.get('math_risk') else '수학 위험 없음',
        '과학 위험 신호' if signals.get('science_risk') else '과학 위험 없음',
        '이공계 적합' if signals.get('sci_track_fit') else None,
        '인문계 적합' if signals.get('humanities_track_fit') else None,
        '의·약학 지향' if signals.get('med_track_fit') else None,
    ]
    chips_html = "".join(
        f"<span class='chip'>{esc(c)}</span>" for c in raw_chips if c
    )

    # 추천 카드들
    card_blocks = []
    for i, r in enumerate(recs, start=1):
        fit = int(round(r.get("fit_score", 0)))
        band_pct = max(0, min(100, int(r.get("band_score", 0))))
        career_pct = max(0, min(100, int(r.get("career_score", 0))))
        track_pct = max(0, min(100, int(r.get("track_score", 0))))
        talent_pct = max(0, min(100, int(r.get("talent_score", 0))))
        talent_kws = ", ".join(r.get("talent_keywords", [])[:5]) or "—"
        band = r.get("matched_admission_band") or "—"
        notes = r.get("notes", "") or ""
        support = r.get("support_level") or ""
        card_blocks.append(f"""
        <div class='card'>
          <div class='card-head'>
            <div>
              <div class='rank'>추천 {i} {('· ' + esc(support)) if support else ''}</div>
              <div class='univ'>{esc(r.get("university"))}</div>
              <div class='meta'>{esc(r.get("region") or "")}</div>
            </div>
            <div class='pill'>적합도 {fit}</div>
          </div>
          <div class='bar-label'>총 적합도</div>
          <div class='bar'><div class='fill' style='width:{fit}%'></div></div>
          <div class='bar-label'>합격선 적합도 (35%)</div>
          <div class='bar'><div class='fill' style='width:{band_pct}%'></div></div>
          <div class='bar-label'>진로 일치도 (25%)</div>
          <div class='bar'><div class='fill' style='width:{career_pct}%'></div></div>
          <div class='bar-label'>전형 적합도 (25%)</div>
          <div class='bar'><div class='fill' style='width:{track_pct}%'></div></div>
          <div class='bar-label'>인재상 유사도 (15%)</div>
          <div class='bar'><div class='fill' style='width:{talent_pct}%'></div></div>
          <div class='kv'><b>인재상 키워드</b> {esc(talent_kws)}</div>
          <div class='kv'><b>매칭 등급대</b> {esc(band)}</div>
          {"<div class='note'>"+esc(notes)+"</div>" if notes else ""}
        </div>""")

    cards_html = "\n".join(card_blocks)
    depts_html = ", ".join(target_departments) or "—"

    # ── 등급 기반 추가 추천 카드 (3개) + 전형 상세 표 ─────────
    student_grade = signals.get("overall_grade")
    grade_section_html = ""
    if grade_recs:
        gcat_label = ", ".join(student_top_categories or []) or "전체"
        grade_card_blocks = []
        for i, r in enumerate(grade_recs, start=1):
            lvl = r.get("support_level", "")
            lvl_color = {"안정":"#16a34a","적정":"#0d9488","상향":"#ea580c",
                         "상향(도전)":"#dc2626"}.get(lvl, "#64748b")
            dept_rows_html = ""
            for d in r.get("all_departments_summary", []):
                dept_rows_html += (
                    f"<div style='display:flex; justify-content:space-between; "
                    f"font-size:0.78rem; padding:0.2rem 0; border-bottom:1px solid var(--border);'>"
                    f"<span>{esc(d['dept'][:24])} <small style='color:var(--text-subtle);'>({esc(d.get('category',''))})</small></span>"
                    f"<b style='color:{lvl_color};'>{d['min_cutoff']:.2f}</b>"
                    f"</div>"
                )

            # 전형 상세 표 (학생 등급 가까운 순 최대 20개)
            flat_rows = []
            for d in r.get("_departments_raw", []):
                for adm in d.get("admissions", []):
                    flat_rows.append({
                        "dept": d.get("name", ""), "type": adm.get("type", ""),
                        "track_name": adm.get("track_name", ""),
                        "applicants": adm.get("applicants"),
                        "competition": adm.get("competition_ratio"),
                        "fill_rank": adm.get("fill_rank"),
                        "p50": adm.get("cutoff_p50"),
                        "p70": adm.get("cutoff_p70"),
                        "p90": adm.get("cutoff_p90"),
                        "subjects": adm.get("evaluated_subjects"),
                    })
            if student_grade is not None:
                flat_rows.sort(key=lambda r: abs((r["p50"] or 99) - student_grade))
            else:
                flat_rows.sort(key=lambda r: r["p50"] or 99)

            def _fmt(v, d=2):
                if v is None: return "—"
                if isinstance(v, float): return f"{v:.{d}f}"
                return esc(str(v))

            tbl_rows = ""
            for fr in flat_rows[:20]:
                bg = ""
                if student_grade is not None and fr["p50"] is not None:
                    dist = abs(fr["p50"] - student_grade)
                    if dist <= 0.3: bg = "background:rgba(22,163,74,0.12);"
                    elif dist <= 0.7: bg = "background:rgba(13,148,136,0.12);"
                    elif dist <= 1.2: bg = "background:rgba(234,88,12,0.10);"
                tbl_rows += (
                    f"<tr style='{bg}'>"
                    f"<td>{esc(fr['dept'][:18])}</td>"
                    f"<td>{esc(fr['type'][:6])}</td>"
                    f"<td>{esc(fr['track_name'][:18])}</td>"
                    f"<td class='r'>{_fmt(fr['applicants'], 0)}</td>"
                    f"<td class='r'>{_fmt(fr['competition'])}</td>"
                    f"<td class='r'>{_fmt(fr['fill_rank'], 1)}</td>"
                    f"<td class='r b'>{_fmt(fr['p50'])}</td>"
                    f"<td class='r'>{_fmt(fr['p70'])}</td>"
                    f"<td class='r'>{_fmt(fr['p90'])}</td>"
                    f"<td class='s'>{esc((fr['subjects'] or '—')[:14])}</td>"
                    f"</tr>"
                )

            admissions_table = f"""
            <table class='admtable'>
              <thead><tr>
                <th>모집단위</th><th>중심전형</th><th>전형명</th>
                <th class='r'>인원</th><th class='r'>경쟁률</th><th class='r'>충원순위</th>
                <th class='r'>50%</th><th class='r'>70%</th><th class='r'>90%</th>
                <th>학종 반영 교과</th>
              </tr></thead>
              <tbody>{tbl_rows}</tbody>
            </table>
            """ if flat_rows else ""

            grade_card_blocks.append(f"""
            <div class='card'>
              <div class='card-head'>
                <div>
                  <div class='rank'>추가 추천 {i} <span style='color:{lvl_color};'>· {esc(lvl)}</span></div>
                  <div class='univ'>{esc(r['university'])}</div>
                  <div class='meta'>{esc(r.get('region',''))} · 학과 {r.get('department_count', 0)}개</div>
                </div>
                <div class='pill' style='background:{lvl_color}; color:white;'>최저 합격선 {r['representative_cutoff']:.2f}</div>
              </div>
              <div class='kv'><b>대표 학과</b> {esc(r.get('representative_dept',''))} ·
                {esc(r.get('representative_track',''))} · 학생 등급 거리 <b>{r['grade_distance']:.2f}</b></div>
              <div class='bar-label'>학과별 최저 합격선 (상위 6개)</div>
              {dept_rows_html}
              {("<div class='bar-label' style='margin-top:0.7rem;'>전형 상세</div>" + admissions_table) if admissions_table else ""}
            </div>
            """)
        grade_cards_html = "\n".join(grade_card_blocks)
        grade_section_html = f"""
          <h2 style='margin-top:2.5rem;'>추가 추천 (등급 기반)</h2>
          <p class='note'>
            학생 등급 <b>{student_grade}</b> + 관심 카테고리 <b>{esc(gcat_label)}</b>을 기준으로,
            학과 추천과는 별개로 등급만 고려한 대학 3개를 추가 추천합니다.
            학생 관심 분야 학과 내에서 합격선이 학생 등급과 가장 가까운 대학들입니다.
          </p>
          <div class='cards'>{grade_cards_html}</div>
        """

    # 계열 적합도 Top 5(>0)
    cat_top = sorted(
        [(k, v) for k, v in category_scores.items() if v > 0],
        key=lambda x: -x[1]
    )[:5]
    cat_total = sum(v for _, v in cat_top) or 1
    cat_lis = "".join(
        f"<li>{esc(k)} <span class='pct'>{int(v/cat_total*100)}%</span></li>"
        for k, v in cat_top
    ) or "<li>—</li>"

    css = """
    :root {
      --bg-app: #f6f5f2; --bg-card: #fffefb; --bg-panel: #fffefb;
      --bg-chip: #f3f4f1; --bg-dept-chip: #d8ede9; --bg-bar: #e4e6e1;
      --bg-note: #f8fafc; --bg-cats-divider: #f1f5f9;
      --text-primary: #0f172a; --text-body: #334155; --text-meta: #475569;
      --text-subtle: #64748b; --text-faint: #94a3b8;
      --text-chip: #3c474b; --text-dept-chip: #0f766e; --accent: #0d9488;
      --border: #e2e8f0;
    }
    @media (prefers-color-scheme: dark) {
      :root {
        --bg-app: #14181a; --bg-card: #222a2d; --bg-panel: #222a2d;
        --bg-chip: #28312f; --bg-dept-chip: #134e4a; --bg-bar: #374151;
        --bg-note: #0f172a; --bg-cats-divider: #334155;
        --text-primary: #f1f5f9; --text-body: #cbd5e1; --text-meta: #94a3b8;
        --text-subtle: #94a3b8; --text-faint: #64748b;
        --text-chip: #c8d0cd; --text-dept-chip: #5eead4; --accent: #2dd4bf;
        --border: #334155;
      }
    }
    body { font-family: -apple-system, 'Pretendard', 'Apple SD Gothic Neo', sans-serif;
           background: var(--bg-app); color: var(--text-primary);
           padding: 2rem; line-height: 1.55; }
    .container { max-width: 1200px; margin: 0 auto; }
    .header { background: linear-gradient(135deg,#1f2a2e,#155e57,#0d9488); color:white;
              padding: 1.4rem 1.6rem; border-radius: 18px; margin-bottom: 1.2rem; }
    .header h1 { margin: 0 0 0.3rem 0; font-size: 1.5rem; color: white; }
    .header .sub { opacity: 0.85; font-size: 0.9rem; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1.2rem; }
    .panel { background: var(--bg-panel); border-radius: 14px; padding: 1.1rem 1.2rem;
             border: 1px solid var(--border); }
    .panel h3 { margin: 0 0 0.6rem 0; font-size: 0.78rem; color: var(--accent);
                text-transform: uppercase; letter-spacing: 0.06em; }
    .chip { display: inline-block; background: var(--bg-chip); color: var(--text-chip);
            border: 1px solid var(--border); padding: 0.3rem 0.6rem; border-radius: 999px;
            margin: 0.15rem 0.25rem 0.15rem 0; font-size: 0.83rem; }
    .dept-chip { background: var(--bg-dept-chip); color: var(--text-dept-chip);
                 border-color: var(--bg-dept-chip); font-weight: 700; padding: 0.4rem 0.7rem; }
    .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; }
    @media (max-width: 1024px) { .grid { grid-template-columns: repeat(2, 1fr); } }
    @media (max-width: 640px) { .grid { grid-template-columns: 1fr; } .row { grid-template-columns: 1fr; } }
    .card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 16px;
            padding: 1rem 1.1rem; }
    .card-head { display: flex; justify-content: space-between; align-items: flex-start;
                 gap: 0.6rem; margin-bottom: 0.7rem; }
    .rank { font-size: 0.7rem; font-weight: 700; color: var(--text-faint);
            text-transform: uppercase; letter-spacing: 0.05em; }
    .univ { font-size: 1.05rem; font-weight: 800; color: var(--text-primary); }
    .meta { font-size: 0.8rem; color: var(--text-faint); margin-top: 0.1rem; }
    .pill { background: linear-gradient(135deg,#0f766e,#0d9488); color: white;
            padding: 0.4rem 0.7rem; border-radius: 999px; font-weight: 800;
            font-size: 0.85rem; white-space: nowrap; }
    .bar-label { font-size: 0.75rem; color: var(--text-subtle); margin: 0.4rem 0 0.15rem; }
    .bar { height: 8px; background: var(--bg-bar); border-radius: 999px; overflow: hidden; }
    .fill { height: 8px; background: linear-gradient(90deg,#5eead4,#0d9488); border-radius: 999px; }
    .kv { font-size: 0.82rem; color: var(--text-meta); margin-top: 0.45rem; }
    .kv b { color: var(--text-primary); margin-right: 0.3rem; }
    .note { font-size: 0.8rem; color: var(--text-subtle); margin-top: 0.5rem;
            line-height: 1.6; }
    .admtable { width: 100%; border-collapse: collapse; font-size: 0.74rem;
                margin-top: 0.4rem; }
    .admtable th { background: var(--bg-chip); padding: 0.35rem 0.4rem;
                   text-align: left; font-weight: 700; color: var(--text-meta); }
    .admtable td { padding: 0.3rem 0.4rem; border-bottom: 1px solid var(--border);
                   color: var(--text-body); }
    .admtable td.r { text-align: right; }
    .admtable td.b { font-weight: 700; }
    .admtable td.s { font-size: 0.7rem; color: var(--text-subtle); }
    .cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.9rem; }
    @media (max-width: 900px) { .cards { grid-template-columns: 1fr; } }
    .note-box { background: var(--bg-note); padding: 0.4rem 0.55rem; border-radius: 8px; }
    .summary { font-size: 0.92rem; line-height: 1.7; color: var(--text-body); }
    ul.cats { list-style: none; padding: 0; margin: 0; }
    ul.cats li { padding: 0.3rem 0; border-bottom: 1px solid var(--bg-cats-divider);
                 font-size: 0.88rem; display: flex; justify-content: space-between;
                 color: var(--text-body); }
    .pct { color: var(--accent); font-weight: 700; }
    .footer { text-align: center; color: var(--text-faint); font-size: 0.8rem; margin-top: 1.2rem; }
    """

    return f"""<!DOCTYPE html>
<html lang='ko'>
<head>
<meta charset='UTF-8'>
<title>대학 추천 결과 — {student}</title>
<style>{css}</style>
</head>
<body>
  <div class='container'>
    <div class='header'>
      <h1>🎓 대학 추천 결과 — {student}</h1>
      <div class='sub'>생성 시각: {today} · MOS Consulting · CollegeMatching</div>
    </div>

    <div class='row'>
      <div class='panel'>
        <h3>우선 추천 학과</h3>
        <div>{"".join(f"<span class='chip dept-chip'>{esc(d)}</span>" for d in target_departments) or "<span class='chip'>—</span>"}</div>
        <h3 style='margin-top:1rem;'>학생 신호</h3>
        <div>{chips_html}</div>
      </div>
      <div class='panel'>
        <h3>요약 분석</h3>
        <div class='summary'>{esc(summary)}</div>
        <h3 style='margin-top:1rem;'>계열 적합도 (상위)</h3>
        <ul class='cats'>{cat_lis}</ul>
      </div>
    </div>

    <h3 style='font-size:0.78rem; color:var(--accent); text-transform:uppercase;
              letter-spacing:0.06em; margin-bottom:0.6rem;'>추천 대학 (학과 기반)</h3>
    <div class='grid'>
      {cards_html}
    </div>

    {grade_section_html}

    <div class='footer'>
      적합도 = (합격선 0.35 + 진로 0.25 + 전형 0.25 + 인재상 0.15) + 보너스(최대 25점),
      100점 상한 · 결정론적 산출 · 추가 추천은 등급+카테고리 기반 거리 정렬
    </div>
  </div>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────
# 신규: 추천 대학 + 근거만 담은 요약 HTML
# (기존 build_recommendation_html 은 전체 화면을 직렬화하지만, 컨설팅
#  현장에서는 학부모/학생에게 '어디를·왜'만 한눈에 보여줄 1장이 필요함)
# ─────────────────────────────────────────────────────────────────────
def _reason_for_dept_rec(r: Dict, student_grade: Optional[float]) -> str:
    """학과 기반 추천 카드 1개의 근거 한 줄을 결정론적으로 합성."""
    parts: List[str] = []
    support = r.get("support_level") or ""
    band = r.get("matched_admission_band")
    if support and band:
        parts.append(f"{support}권 (합격선 {band})")
    elif support:
        parts.append(f"{support}권")
    matched = r.get("matched_departments") or []
    if matched:
        parts.append("매칭 학과 " + ", ".join(matched[:3]))
    if r.get("career_matched_count", 0) >= 2:
        parts.append("추천 학과 다수 보유")
    kws = r.get("talent_keywords") or []
    if kws and int(r.get("talent_score", 0)) >= 70:
        parts.append("인재상 부합(" + ", ".join(kws[:2]) + ")")
    if r.get("target_bonus", 0) > 0:
        parts.append("학생 목표 대학")
    return " · ".join(parts) or "종합 적합도 기준 추천"


def _reason_for_grade_rec(r: Dict, student_grade: Optional[float]) -> str:
    """등급 기반 추천 카드 1개의 근거 한 줄."""
    parts: List[str] = []
    lvl = r.get("support_level") or ""
    cut = r.get("representative_cutoff")
    if lvl and cut is not None:
        parts.append(f"{lvl}권 (대표 합격선 {cut:.2f})")
    dep = r.get("representative_dept")
    if dep:
        parts.append(f"대표 학과 {dep}")
    dist = r.get("grade_distance")
    if dist is not None and student_grade is not None:
        parts.append(f"학생 등급과 거리 {dist:.2f}")
    return " · ".join(parts) or "등급 근접도 기준 추천"


def build_compact_recommendation_html(recs: List[Dict],
                                      target_departments: List[str],
                                      signals: Dict,
                                      summary: str,
                                      grade_recs: Optional[List[Dict]] = None,
                                      student_top_categories: Optional[List[str]] = None,
                                      user_department: Optional[str] = None,
                                      conflict_note: Optional[str] = None) -> str:
    """
    추천 대학과 근거만 시각적으로 보여주는 1장짜리 요약 HTML.
    상세 표/신호 칩/감사 추적은 의도적으로 제외하고, '어느 대학을 왜'에 집중.
    """
    def esc(s):
        return _html.escape(str(s)) if s is not None else ""

    meta = signals.get("report_meta", {}) or {}
    student = esc(meta.get("student_name") or "학생")
    grade = signals.get("overall_grade")
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    depts_html = ", ".join(target_departments) or "—"

    def _row(rank_label, univ, region, score_label, reason, accent):
        return f"""
        <div class='c-card'>
          <div class='c-rank'>{esc(rank_label)}</div>
          <div class='c-main'>
            <div class='c-univ'>{esc(univ)}</div>
            <div class='c-region'>{esc(region or '')}</div>
            <div class='c-reason'>{esc(reason)}</div>
          </div>
          <div class='c-score' style='background:{accent};'>{esc(score_label)}</div>
        </div>"""

    dept_rows = []
    for i, r in enumerate(recs, start=1):
        fit = int(round(r.get("fit_score", 0)))
        reason = _reason_for_dept_rec(r, grade)
        dept_rows.append(_row(f"학과기반 {i}", r.get("university"),
                              r.get("region"), f"적합도 {fit}", reason, "#0d9488"))
    dept_block = "\n".join(dept_rows) or "<div class='c-empty'>학과 기반 추천 없음</div>"

    grade_block = ""
    if grade_recs:
        lvl_color = {"안정": "#16a34a", "적정": "#0d9488",
                     "상향": "#ea580c", "상향(도전)": "#dc2626"}
        g_rows = []
        for i, r in enumerate(grade_recs, start=1):
            lvl = r.get("support_level", "")
            reason = _reason_for_grade_rec(r, grade)
            cut = r.get("representative_cutoff")
            g_rows.append(_row(f"등급기반 {i}", r.get("university"), r.get("region"),
                               f"합격선 {cut:.2f}" if cut is not None else "—",
                               reason, lvl_color.get(lvl, "#64748b")))
        gcat = ", ".join(student_top_categories or []) or "전체"
        grade_block = f"""
        <h2>등급 기반 추가 추천 <small>· 관심 카테고리 {esc(gcat)}</small></h2>
        <div class='c-list'>{''.join(g_rows)}</div>"""

    user_block = ""
    if user_department:
        warn = f"<div class='c-warn'>⚠ {esc(conflict_note)}</div>" if conflict_note else ""
        user_block = (f"<div class='c-user'>사용자 지정 학과: <b>{esc(user_department)}</b>"
                      f" (추천 우선 반영){warn}</div>")

    css = """
    :root{--bg:#f6f5f2;--card:#fffefb;--bd:#e2e8f0;--tx:#0f172a;--sub:#64748b;--ac:#0d9488;}
    @media(prefers-color-scheme:dark){:root{--bg:#14181a;--card:#222a2d;--bd:#334155;--tx:#f1f5f9;--sub:#94a3b8;--ac:#2dd4bf;}}
    *{box-sizing:border-box;} body{font-family:-apple-system,'Pretendard','Apple SD Gothic Neo',sans-serif;
      background:var(--bg);color:var(--tx);margin:0;padding:1.6rem;line-height:1.5;}
    .wrap{max-width:820px;margin:0 auto;}
    .head{background:linear-gradient(135deg,#155e57,#0d9488);color:#fff;padding:1.2rem 1.4rem;border-radius:14px;}
    .head h1{margin:0 0 .25rem;font-size:1.3rem;color:#fff;}
    .head .s{opacity:.85;font-size:.85rem;}
    .strip{background:var(--card);border:1px solid var(--bd);border-radius:12px;
      padding:.8rem 1rem;margin:1rem 0;font-size:.9rem;color:var(--sub);}
    .strip b{color:var(--tx);}
    .c-user{background:var(--card);border:1px solid var(--ac);border-radius:12px;padding:.7rem 1rem;margin:1rem 0;font-size:.9rem;}
    .c-warn{margin-top:.4rem;color:#b45309;font-weight:600;font-size:.85rem;}
    h2{font-size:1rem;margin:1.6rem 0 .6rem;color:var(--ac);}
    h2 small{color:var(--sub);font-weight:400;}
    .c-list{display:flex;flex-direction:column;gap:.6rem;}
    .c-card{display:flex;align-items:stretch;gap:.8rem;background:var(--card);
      border:1px solid var(--bd);border-radius:12px;padding:.8rem 1rem;}
    .c-rank{font-size:.7rem;font-weight:700;color:var(--sub);writing-mode:vertical-rl;
      text-orientation:mixed;letter-spacing:.05em;padding-right:.4rem;border-right:1px solid var(--bd);}
    .c-main{flex:1;min-width:0;}
    .c-univ{font-size:1.05rem;font-weight:800;}
    .c-region{font-size:.78rem;color:var(--sub);margin:.1rem 0 .35rem;}
    .c-reason{font-size:.85rem;color:var(--tx);}
    .c-score{align-self:center;color:#fff;font-weight:800;font-size:.85rem;
      padding:.45rem .7rem;border-radius:999px;white-space:nowrap;}
    .c-empty{color:var(--sub);font-size:.9rem;padding:.6rem;}
    .foot{margin-top:1.5rem;font-size:.75rem;color:var(--sub);text-align:center;}
    """
    return f"""<!DOCTYPE html>
<html lang='ko'><head><meta charset='UTF-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>추천 요약 — {student}</title><style>{css}</style></head>
<body><div class='wrap'>
  <div class='head'>
    <h1>대학 추천 요약 — {student}</h1>
    <div class='s'>{today} · MOS Consulting · 학생 등급 {esc(grade if grade is not None else '미탐지')}</div>
  </div>
  {user_block}
  <div class='strip'>우선 추천 학과: <b>{esc(depts_html)}</b></div>
  <div class='strip'>요약: {esc(summary)}</div>
  <h2>추천 대학 <small>· 학과 기반(4축 적합도)</small></h2>
  <div class='c-list'>{dept_block}</div>
  {grade_block}
  <div class='foot'>적합도 = 합격선0.35 + 진로0.25 + 전형0.25 + 인재상0.15 + 보너스(≤25) · 결정론 산출</div>
</div></body></html>"""
