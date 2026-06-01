# app.py — 메인 오케스트레이터 (UI/흐름 제어 전용)
# ─────────────────────────────────────────────────────────────────────
# v9 리팩터링: 1,778행 단일 파일을 기능별 모듈로 분리.
#   · signals.py        : 신호 추출 / 계열 점수 / 학과 후보 산출
#   · recommender.py    : 합격선·지원군 분류 / 4축 추천 / 등급 기반 추천
#   · report_builder.py : 요약 + 다운로드 HTML(전체/요약본)
#   · dept_matching.py  : 사용자 지정 학과 ↔ DB 학과 유사도 매칭(신규)
# app.py 는 화면 흐름과 모듈 호출만 담당한다.
import re
from typing import Dict, List, Optional

import streamlit as st

from constants import *
from utils import load_json_db
from password import require_login, get_secret_value
from renderUI import *

from signals import (
    extract_example_specific_signals,
    infer_category_scores,
    choose_target_departments,
)
from recommender import (
    recommend_universities,
    recommend_universities_by_grade,
)
from report_builder import (
    summarize_with_gemini,
    build_recommendation_html,
    build_compact_recommendation_html,
)
from dept_matching import (
    resolve_user_department,
    assess_department_conflict,
    merge_user_department,
)


def main():
    st.set_page_config(
        page_title='학생 HTML 기반 대학 추천기',
        page_icon='🎓',
        layout='wide',
        initial_sidebar_state='collapsed'
    )
    inject_css()
    render_hero()

    if not require_login():
        st.stop()

    try:
        db = load_json_db(JSON_DB_PATH)
    except Exception as e:
        st.error(str(e))
        st.stop()

    # DB 통계 집계
    univs = db.get('universities', [])
    n_univ = len(univs)
    n_dept = sum(len(u.get('departments', [])) for u in univs)
    n_adm = sum(len(d.get('admissions', [])) for u in univs for d in u.get('departments', []))

    top1, top2, top3 = st.columns(3)
    with top1:
        render_metric_card(
            '연결 DB',
            f"{n_univ}개 대학",
            f"학과 {n_dept}개 · 전형 {n_adm}개 정보를 로드했습니다."
        )
    with top2:
        render_metric_card(
            '입력 형식',
            '학생 HTML',
            '학생 정보를 담은 MOS 진단 보고서를 삽입하세요.'
        )
    with top3:
        render_metric_card(
            '분석 엔진',
            'Gemini + Kiwi 형태소',
            'AI 요약과 한국어 형태소 분석으로 핵심 신호만 추출합니다.'
        )

    col_up1, col_up2 = st.columns(2)
    with col_up1:
        uploaded_html = st.file_uploader('학생 분석 HTML 업로드', type=['html', 'htm'])
    with col_up2:
        uploaded_answers = st.file_uploader('학생 답변 JSON 업로드', type=['json'])

    # ── 신규: 사용자 지정 희망 학과 입력 ───────────────────────────
    user_dept_input = st.text_input(
        '희망 학과 직접 입력 (선택)',
        placeholder='예: 컴퓨터공학과 / AI / 신문방송 / 의예',
        help='입력하면 DB의 실제 학과명 중 가장 유사한 학과를 API(임베딩)로 '
             '자동 매칭해 추천에 우선 반영합니다. HTML/JSON에서 추출한 학과와 '
             '충돌하면 경고 후 사용자 입력을 우선합니다.'
    )

    # HTML 과 JSON 을 모두 첨부했을 때만 분석 진행.
    both_uploaded = (uploaded_html is not None) and (uploaded_answers is not None)

    if (uploaded_html is not None) ^ (uploaded_answers is not None):
        missing = "학생 답변 JSON" if uploaded_html is not None else "학생 분석 HTML"
        st.info(
            f"분석을 시작하려면 HTML 과 JSON 을 **모두** 첨부해야 합니다. "
            f"현재 '{missing}' 파일이 없습니다. 두 파일이 모두 업로드되면 "
            f"결합 분석이 1회 실행됩니다 (AI API 중복 호출 방지)."
        )

    if both_uploaded:
        answer_result = None
        answers_text = uploaded_answers.read().decode('utf-8', errors='ignore')

        # ── HTML + JSON 결합 분석 (AI 파이프라인 단일 실행) ──
        html_text = uploaded_html.read().decode('utf-8', errors='ignore')
        signals = extract_example_specific_signals(html_text)
        category_scores = infer_category_scores(signals)

        try:
            from answer_pipeline import run_answer_pipeline
            answer_result = run_answer_pipeline(
                answers_text,
                base_category_scores=category_scores,
                use_llm=True,
                log_prediction=False,
            )
            dec_scores = answer_result["decision"]["category_scores"]
            if dec_scores:
                # 답변 JSON(1인칭 직접 응답)을 HTML(2차 재가공)보다 강하게 신뢰.
                ANSWER_WEIGHT = 3.0
                HTML_DAMPENING = 0.5
                merged = {cat: v * HTML_DAMPENING for cat, v in category_scores.items()}
                for cat, v in dec_scores.items():
                    merged[cat] = merged.get(cat, 0.0) + v * ANSWER_WEIGHT
                category_scores = merged

            # 학생 등급 보완: HTML 파서가 등급을 못 잡았으면 답변에서 추출
            if signals.get("overall_grade") is None:
                rs = answer_result.get("rule_signals", {}) or {}
                grade_text = (rs.get("grade_goal_text") or "") + " " + (rs.get("target_tier_text") or "")
                m = re.search(r"([1-9](?:\.\d)?)\s*등급", grade_text)
                if m:
                    try:
                        signals["overall_grade"] = float(m.group(1))
                    except Exception:
                        pass

            # 답변 JSON 신호를 signals 에 동기화
            rs = answer_result.get("rule_signals", {}) or {}
            answer_strong = set(rs.get("strong_subjects") or [])
            answer_weak = set(rs.get("weak_subjects") or [])
            if answer_weak:
                if any(s in answer_weak for s in ["수학"]):
                    signals["math_risk"] = True
                if any(s in answer_weak for s in ["과학", "물리", "화학", "생명과학", "지구과학", "탐구"]):
                    signals["science_risk"] = True
                if "영어" not in answer_strong and "영어" in answer_weak:
                    signals["english_strength"] = False
            if "국어" in answer_strong:
                signals["essay_strength"] = True
            ac = set(rs.get("career_clusters") or [])
            if "의약학" in ac:
                signals["med_track_fit"] = True
            if any(c in ac for c in ["컴퓨터·AI", "공학", "수리·통계"]):
                signals["sci_track_fit"] = True
            if any(c in ac for c in ["미디어·콘텐츠", "인문·언어", "사회·정치"]):
                signals["humanities_media_fit"] = True

            st.success(
                f"HTML + 답변 JSON 결합 분석 (질문지 {answer_result['version']}, "
                f"{answer_result['n_questions']}문항). "
                f"판정 엔진 v{answer_result['decision']['decision_version']} · "
                f"LLM 보강 {'사용' if answer_result['llm_used'] else '규칙 단독'}"
            )
        except Exception as e:
            st.warning(f"답변 JSON 처리 실패 — HTML 신호만 사용합니다: {e}")

        target_departments = choose_target_departments(signals, category_scores, max_n=3)

        # ── 신규: 사용자 지정 학과 해석 + 충돌 감지 + 우선 반영 ──────
        user_department_final: Optional[str] = None
        conflict_note: Optional[str] = None
        if user_dept_input.strip():
            candidates = resolve_user_department(user_dept_input, db, top_k=5)
            if not candidates:
                st.warning(f"'{user_dept_input}'와 유사한 학과를 DB에서 찾지 못했습니다. "
                           f"추출된 학과로만 추천합니다.")
            else:
                best = candidates[0]
                user_department_final = best["name"]
                cand_label = " · ".join(
                    f"{c['name']}({c['score']:.2f})" for c in candidates
                )
                st.info(
                    f"입력 학과 '{user_dept_input}' → 매칭 후보: {cand_label} "
                    f"[{best['backend']}]. 1순위 **{best['name']}**를 우선 반영합니다."
                )
                is_conflict, sim, msg = assess_department_conflict(
                    user_department_final, target_departments
                )
                if is_conflict:
                    conflict_note = msg
                    st.warning("⚠ " + msg)
                target_departments = merge_user_department(
                    user_department_final, target_departments, max_n=3
                )

        # 추천 전형 (추천 대학 점수 산출에도 사용 → 먼저 계산)
        from admission_tracks import recommend_tracks, detect_student_region
        track_recs = recommend_tracks(signals, answer_result)
        student_area = detect_student_region(signals)

        recs = recommend_universities(db, signals, target_departments, top_n=5,
                                       answer_result=answer_result,
                                       track_recs=track_recs)
        summary = summarize_with_gemini(signals, target_departments, recs)

        # 답변 파이프라인 상세(설명가능성·거버넌스)
        if answer_result is not None:
            dec = answer_result["decision"]
            ml = answer_result["ml_crosscheck"]
            with st.expander("답변 기반 판정 근거 (설명가능성)", expanded=True):
                st.markdown(f"**최종 판정 Top3**: {' · '.join(dec['top_categories'])}")
                st.caption(
                    f"판정 방식: 결정론 규칙 엔진 (동일 입력→동일 출력) · "
                    f"버전 {dec['decision_version']}"
                )
                rs = answer_result["rule_signals"]
                st.markdown(
                    f"- 강점 과목: {rs['strong_subjects'] or '—'}\n"
                    f"- 약점 과목: {rs['weak_subjects'] or '—'}\n"
                    f"- 규칙 확정 진로 클러스터: {rs['career_clusters'] or '—'}\n"
                    f"- 목표 대학 진술: {rs['target_tier_text'] or '—'}"
                )
                ml_mode = answer_result["ml_status"]["mode"]
                ml_note = (
                    f"ML 교차검증: {ml.get('confidence_flag','-')} "
                    f"(모드 {ml_mode}, 레이블 "
                    f"{answer_result['ml_status']['labeled']}/"
                    f"{answer_result['ml_status']['threshold']}) — "
                    f"ML은 판정자가 아닌 자문입니다."
                )
                st.caption(ml_note)
                with st.expander("점수 변동 감사 추적 (audit trail)", expanded=False):
                    st.json(dec["audit_trail"][:40])

        # ── 상단: 학생 분석 영역 ────────────────────────────────
        st.markdown(
            "<div class='section-title' style='margin-top:1rem;'>학생 분석</div>",
            unsafe_allow_html=True
        )

        from student_profile import build_student_profile
        profile = build_student_profile(
            signals, answer_result,
            answers_text=answers_text if both_uploaded else None
        )

        left, right = st.columns([1.55, 1], gap="large")
        with left:
            render_chip_row('우선 추천 학과', target_departments, dept=True)
            render_student_profile_card(profile)
        with right:
            render_category_donut(category_scores)
            st.markdown(
                f"<div class='glass-card' style='margin-top:0.6rem;'>"
                f"<div class='section-title' style='font-size:0.98rem;'>요약 분석</div>"
                f"<div class='subtle' style='font-size:0.92rem; line-height:1.65; "
                f"color:var(--text-body);'>{summary}</div></div>",
                unsafe_allow_html=True
            )

        # ── 중간: 추천 전형 (A3) ────────────────────────────────
        render_track_recommendations(track_recs, student_area)

        # ── 하단 ①: 학과 기반 추천 대학 (5개) ───────────────────
        st.markdown(
            "<div class='section-title' style='margin-top:1.5rem;'>추천 대학 (학과 기반)</div>",
            unsafe_allow_html=True
        )
        with st.expander("적합도 점수 산출 방식 안내", expanded=False):
            render_score_methodology()

        if not target_departments:
            st.warning(
                "HTML에서 추천용 학과 후보를 충분히 구성하지 못했습니다. "
                "키워드 사전 또는 최종 결론 반영 규칙을 점검해야 합니다."
            )
        elif not recs:
            st.warning(
                "추천 학과 후보는 추출되었지만 현재 DB 학과명과의 매칭이 충분하지 않아 "
                "대학 추천이 생성되지 않았습니다."
            )
        else:
            level_order = ["안정", "적정", "상향", "상향(도전)", "재고", "정보부족"]
            grouped_dept: Dict[str, List[Dict]] = {lv: [] for lv in level_order}
            for r in recs:
                lv = r.get("support_level") or "정보부족"
                grouped_dept.setdefault(lv, []).append(r)

            global_rank = 1
            for lv in level_order:
                cards = grouped_dept.get(lv, [])
                if not cards:
                    continue
                render_support_level_header(lv, len(cards))
                row_size = 3
                for row_start in range(0, len(cards), row_size):
                    row = cards[row_start:row_start + row_size]
                    cols = st.columns(row_size)
                    for col_i, rec in enumerate(row):
                        with cols[col_i]:
                            render_university_card(rec, global_rank)
                            univ_obj = next(
                                (u for u in db['universities']
                                 if u['name'] == rec['university']), None
                            )
                            if univ_obj:
                                with st.expander(
                                    f"📋 {rec['university']} 전형 상세 보기",
                                    expanded=False
                                ):
                                    render_admissions_detail_panel(
                                        univ_obj.get("departments", []),
                                        student_grade=signals.get("overall_grade")
                                    )
                            global_rank += 1

        # ── 하단 ②: 등급 기반 추가 추천 (3개) ───────────────────
        student_grade = signals.get("overall_grade")
        grade_recs: List[Dict] = []
        student_top_categories: List[str] = []

        if student_grade is not None:
            top_cats = sorted(category_scores.items(),
                              key=lambda x: x[1], reverse=True)[:1]
            student_top_categories = [c for c, v in top_cats if v > 0]

            CATEGORY_TO_DEPT_CAT = {
                "국어국문·언어": ["인문"], "역사·철학·윤리": ["인문"],
                "사회과학": ["사회"], "경영·경제": ["사회"],
                "미디어·광고·콘텐츠": ["사회"], "심리·상담": ["사회"],
                "수학·통계": ["자연"], "물리·화학·기초과학": ["자연"],
                "생명과학·바이오": ["자연"], "환경·지구과학": ["자연"],
                "컴퓨터·소프트웨어": ["공학"], "인공지능·데이터사이언스": ["공학"],
                "전기·전자·반도체": ["공학"], "기계·로봇·모빌리티": ["공학"],
                "화공·신소재·에너지공학": ["공학"], "건축·도시·토목": ["공학"],
                "의학": ["의학"], "치의학": ["의학"], "한의학": ["의학"],
                "수의학": ["의학"], "간호": ["의학"], "보건·재활": ["의학"],
                "약학": ["약학"], "교육": ["교육"], "디자인·예술": ["예체능"],
            }
            dept_cats_filter = []
            for cat in student_top_categories:
                dept_cats_filter.extend(CATEGORY_TO_DEPT_CAT.get(cat, []))

            target_dept_cats = set()
            for u in db.get("universities", []):
                for d in u.get("departments", []):
                    d_name = d.get("name", "")
                    d_aliases = d.get("aliases") or []
                    if d_name in (target_departments or []) or \
                       any(a in (target_departments or []) for a in d_aliases):
                        c = d.get("category")
                        if c:
                            target_dept_cats.add(c)
            dept_cats_filter.extend(target_dept_cats)
            dept_cats_filter = list(set(dept_cats_filter))

            dept_keywords = []
            for dept in (target_departments or []):
                s = dept
                while True:
                    new = re.sub(r'(학과|학부|전공|과|부|학)$', '', s)
                    if new == s:
                        break
                    s = new
                for mod in ['글로벌', '국제', '융합', '미래', '첨단', '스마트']:
                    s = s.replace(mod, '')
                s = s.strip()
                if len(s) >= 2:
                    dept_keywords.append(s)
            seen = set()
            dept_keywords = [k for k in dept_keywords
                             if not (k in seen or seen.add(k))]

            grade_recs = recommend_universities_by_grade(
                db, student_grade,
                top_n=3,
                student_categories=dept_cats_filter if dept_cats_filter else None,
                dept_keywords=dept_keywords if dept_keywords else None,
                balanced_levels=True,
            )

        st.markdown(
            "<div class='section-title' style='margin-top:2rem;'>추가 추천 (등급 기반)</div>",
            unsafe_allow_html=True
        )

        if student_grade is None:
            st.warning(
                "학생의 등급 정보를 추출하지 못해 등급 기반 추가 추천을 생성할 수 없습니다."
            )
        elif not grade_recs:
            st.info(
                f"학생 관심 카테고리({', '.join(student_top_categories) or '미탐지'}) 내에서 "
                f"등급 {student_grade}과 가까운 대학을 찾지 못했습니다."
            )
        else:
            cat_filter_label = ", ".join(student_top_categories) or "전체"
            st.markdown(
                f"<div class='subtle' style='margin-bottom:0.6rem; font-size:0.88rem;'>"
                f"학생 등급 <b>{student_grade}</b> + 관심 카테고리 <b>{cat_filter_label}</b>을 기준으로, "
                f"학과 추천과는 별개로 등급만 고려한 대학 3개를 추가 추천합니다. "
                f"학생 관심 분야 학과 내에서 합격선이 학생 등급과 가장 가까운 대학들입니다.</div>",
                unsafe_allow_html=True
            )

            cols = st.columns(3)
            for col_i, rec in enumerate(grade_recs):
                with cols[col_i]:
                    render_grade_based_card(rec, col_i + 1, student_grade)
                    with st.expander(
                        f"📋 {rec['university']} 전형 상세 보기",
                        expanded=False
                    ):
                        render_admissions_detail_panel(
                            rec.get("_departments_raw", []),
                            student_grade=student_grade
                        )

        # ── 다운로드 버튼: 전체 리포트 + 요약본(신규) ──────────────
        if recs:
            student_name_hint = (signals.get("report_meta", {}) or {}).get("student_name") or "학생"

            full_html = build_recommendation_html(
                recs=recs,
                target_departments=target_departments,
                signals=signals,
                summary=summary,
                category_scores=category_scores,
                grade_recs=grade_recs,
                student_top_categories=student_top_categories,
            )
            compact_html = build_compact_recommendation_html(
                recs=recs,
                target_departments=target_departments,
                signals=signals,
                summary=summary,
                grade_recs=grade_recs,
                student_top_categories=student_top_categories,
                user_department=user_department_final,
                conflict_note=conflict_note,
            )

            st.markdown("<div style='margin-top:1.2rem;'></div>", unsafe_allow_html=True)
            dl1, dl2 = st.columns(2)
            with dl1:
                st.download_button(
                    label="📥 전체 상세 리포트 HTML 저장",
                    data=full_html.encode("utf-8"),
                    file_name=f"추천대학_상세_{student_name_hint}.html",
                    mime="text/html",
                    width='stretch',
                )
            with dl2:
                st.download_button(
                    label="📄 추천 요약본 HTML 저장 (대학+근거만)",
                    data=compact_html.encode("utf-8"),
                    file_name=f"추천대학_요약_{student_name_hint}.html",
                    mime="text/html",
                    width='stretch',
                )

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
                'user_department': user_department_final,
                'top_keywords': signals.get('top_keywords', [])[:20]
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
