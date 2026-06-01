"""
roadmap.py
─────────────────────────────────────────────────────────────────────
대학별 학습 갭 분석 + 분기별 액션 로드맵 생성.

설계 원칙
- 갭 분석은 결정론적(동일 입력 → 동일 출력).
- 액션 라이브러리는 사람이 큐레이션한 IP 자산(action_library.py).
- LLM 자유 생성을 금지한다. 갭 → action_id 매핑은 규칙 기반.
- 학년 미확정 학생은 분기 라벨 대신 '단계' 라벨로 fallback.

거버넌스
- 모든 로드맵 출력에 "본 로드맵은 일반 가이드이며 컨설턴트와 상의 필요" 명시.
- 행동 처방 출처(source_basis)를 항상 동반 표시.
"""
from __future__ import annotations
import re
from datetime import date
from typing import Dict, List, Optional, Tuple

from action_library import ACTION_LIBRARY, get_action


# ═════════════════════════════════════════════════════════════════
# A. 학년 추출 + 시간축 계산
# ═════════════════════════════════════════════════════════════════

GRADE_PATTERNS = [
    (r"고\s*3|고등\s*3|3학년", "고3"),
    (r"고\s*2|고등\s*2|2학년", "고2"),
    (r"고\s*1|고등\s*1|1학년", "고1"),
    (r"중\s*3|중학\s*3", "중3"),
    (r"중\s*2|중학\s*2", "중2"),
    (r"재수|N수", "재수"),
]


def detect_grade_level(signals: Dict, answer_result: Optional[Dict] = None) -> Optional[str]:
    """HTML 메타 또는 답변 텍스트에서 학년 추출."""
    meta = signals.get("report_meta") or {}
    # 1순위: report_meta 의 명시 학년
    explicit = meta.get("grade_level") or meta.get("학년")
    if explicit:
        for pat, label in GRADE_PATTERNS:
            if re.search(pat, str(explicit)):
                return label
    # 2순위: persona 텍스트
    persona = meta.get("persona") or meta.get("student_persona") or ""
    if not persona and answer_result:
        persona = answer_result.get("persona_display_only") or ""
    for pat, label in GRADE_PATTERNS:
        if re.search(pat, persona):
            return label
    # 3순위: raw_text 첫 200자
    raw = (signals.get("raw_text", "") or "")[:200]
    for pat, label in GRADE_PATTERNS:
        if re.search(pat, raw):
            return label
    return None


# 한국 대입 달력 기준 — 학년별 남은 분기
# 2026.5 기준으로 작성. 매년 자동 보정은 today 인자로 처리.
def compute_timeline(grade_level: Optional[str],
                     today: Optional[date] = None) -> Dict:
    """
    학년 + 현재 날짜 → 대입까지 남은 분기 라벨 리스트.
    분기 = 한국 입시 자연 단위 (1학기 중간/기말 + 여름방학 + 2학기 중간/기말 + 겨울방학)

    반환: {
      'grade_level': '고1'(또는 None),
      'd_day_months': 대입(수능)까지 남은 개월 수 (추정),
      'quarters': [{'label': '고1 1학기 기말', 'months_from_now': 2}, ...]
    }
    """
    today = today or date.today()
    if grade_level is None:
        return {
            "grade_level": None,
            "d_day_months": None,
            "quarters": [
                {"label": "1단계 (학년 미확정)", "months_from_now": 0},
                {"label": "2단계", "months_from_now": 3},
                {"label": "3단계", "months_from_now": 6},
                {"label": "4단계", "months_from_now": 9},
            ],
            "note": "학년 정보가 없어 일반 단계 라벨로 표시합니다.",
        }

    # 학년별 남은 분기 정의 (대입 수능 = 11월 셋째주 목요일)
    # 각 분기: (label, months_from_now)
    # 단순화를 위해 현재 시점이 어느 학기인지는 today.month 로 추정
    is_first_semester = today.month <= 7  # 1~7월: 1학기 중심

    grade_to_quarters = {
        "중3": [
            ("중3 잔여 학기", 0),
            ("중3→고1 겨울방학", 4),
            ("고1 1학기", 8),
            ("고1 여름방학", 12),
            ("고1 2학기", 16),
            ("고2 1학기", 22),
            ("고2 2학기", 28),
            ("고3 (실전)", 36),
        ],
        "고1": [
            ("고1 잔여 학기", 0),
            ("고1 여름방학" if is_first_semester else "고1→고2 겨울방학", 3),
            ("고2 1학기", 8),
            ("고2 여름방학", 12),
            ("고2 2학기", 16),
            ("고3 1학기 (수능 대비)", 22),
            ("고3 여름방학 (실전 모의)", 26),
            ("고3 2학기 (수능 직전)", 30),
        ],
        "고2": [
            ("고2 잔여 학기", 0),
            ("고2 여름방학" if is_first_semester else "고2→고3 겨울방학", 3),
            ("고3 1학기 (수능 + 수시 1차)", 8),
            ("고3 여름방학 (실전 모의)", 12),
            ("고3 2학기 (수능 + 수시 면접·논술)", 15),
        ],
        "고3": [
            ("현재 ~ 9월 모의평가", 0),
            ("9월 ~ 수능 직전", 3),
            ("수능 직후 ~ 수시 면접·논술", 5),
            ("정시 원서 ~ 합격 발표", 7),
        ],
        "재수": [
            ("현재 ~ 6월 모의평가", 0),
            ("6월 ~ 9월 모의평가", 3),
            ("9월 ~ 수능 직전", 5),
            ("수능 직후 ~ 합격", 7),
        ],
    }

    quarters = grade_to_quarters.get(grade_level, grade_to_quarters["고2"])
    d_day = quarters[-1][1] if quarters else 12

    return {
        "grade_level": grade_level,
        "d_day_months": d_day,
        "quarters": [
            {"label": label, "months_from_now": mfn}
            for label, mfn in quarters
        ],
        "note": None,
    }


# ═════════════════════════════════════════════════════════════════
# B. 갭 분석 (등급·인재상·전형)
# ═════════════════════════════════════════════════════════════════

def analyze_gaps(rec: Dict, signals: Dict,
                 track_recs: Optional[List[Dict]] = None) -> Dict:
    """
    학생-대학 쌍에 대한 3종 갭 분석.
    rec: recommend_universities 의 단일 결과 (support_level, matched_admission_band 등 포함)
    signals: 학생 신호
    track_recs: admission_tracks.recommend_tracks 결과 (있으면 전형 갭 분석에 활용)
    """
    gaps = {
        "grade_gap": None,      # 등급 차이 (float, 음수=학생 우위)
        "grade_severity": None, # 'safe' | 'small' | 'medium' | 'large'
        "talent_gap": None,     # 인재상 미매칭 키워드 비율 (0~1)
        "talent_missing": [],   # 미매칭 인재상 키워드 목록
        "track_gap": None,      # 추천 전형 Top1 vs 임계치
        "track_top_id": None,
        "summary": "",
    }

    # 1) 등급 갭
    overall = signals.get("overall_grade")
    band = rec.get("matched_admission_band")
    if overall is not None and band:
        m = re.match(r"\s*([0-9.]+)\s*[-~]\s*([0-9.]+)", band)
        if m:
            lo = float(m.group(1))
            hi = float(m.group(2))
            # 학생이 합격선 하한보다 얼마나 못한지 (양수 = 학생이 못함)
            gap = overall - lo
            gaps["grade_gap"] = round(gap, 2)
            if gap <= 0:
                gaps["grade_severity"] = "safe"
            elif gap <= 0.3:
                gaps["grade_severity"] = "small"
            elif gap <= 0.7:
                gaps["grade_severity"] = "medium"
            else:
                gaps["grade_severity"] = "large"

    # 2) 인재상 갭 (학생 키워드 ∩ 대학 인재상)
    student_kws = set(signals.get("top_keywords", []) or [])
    student_kws |= set(signals.get("strong_subjects", []) or [])
    univ_kws = rec.get("talent_keywords", []) or []
    if univ_kws:
        # 학생 키워드 중 대학 인재상과 일치하는 비율
        matched = [kw for kw in univ_kws if any(kw in sk or sk in kw for sk in student_kws)]
        match_ratio = len(matched) / max(len(univ_kws), 1)
        gaps["talent_gap"] = round(1 - match_ratio, 2)
        gaps["talent_missing"] = [kw for kw in univ_kws if kw not in matched][:6]

    # 3) 전형 갭
    if track_recs:
        top_track = max(track_recs, key=lambda t: t.get("score", 0))
        gaps["track_top_id"] = top_track.get("id")
        gaps["track_top_label"] = top_track.get("label")
        gaps["track_top_score"] = top_track.get("score")
        gaps["track_gap"] = max(0, 70 - top_track.get("score", 0))  # 70점 임계

    # 요약
    parts = []
    if gaps["grade_severity"] == "safe":
        parts.append(f"등급 안전 (학생 {overall} ≤ {band})")
    elif gaps["grade_gap"] is not None:
        parts.append(f"등급 갭 {gaps['grade_gap']:.1f}등급 ({gaps['grade_severity']})")
    if gaps["talent_gap"] and gaps["talent_gap"] > 0.6:
        parts.append(f"인재상 미매칭 {int(gaps['talent_gap']*100)}%")
    if gaps["track_top_id"]:
        parts.append(f"우선 전형: {gaps.get('track_top_label')}")
    gaps["summary"] = " · ".join(parts) if parts else "갭 정보 부족"

    return gaps


# ═════════════════════════════════════════════════════════════════
# C. 갭 → 처방 매핑 (결정론적 규칙)
# ═════════════════════════════════════════════════════════════════

# 학년 호환성: 학생 학년이 처방의 applies_to_grade 중 하나에 인접하면 적용 가능.
# 예: 중3 학생은 '고1 진입 직전' 이므로 고1용 처방 적용 가능
GRADE_COMPATIBILITY = {
    "중3": ["중3", "고1"],
    "고1": ["고1", "고2"],
    "고2": ["고2", "고3", "고1"],  # 보강용으로 고1 처방도 일부 받음
    "고3": ["고3", "고2"],
    "재수": ["고3", "재수"],
}


def _grade_compatible(student_grade: Optional[str], applies_to: List[str]) -> bool:
    """학생 학년이 처방의 applies_to_grade 와 호환되는지."""
    if not student_grade or not applies_to:
        return True  # 학년 미확정 시 모든 처방 통과
    compat = GRADE_COMPATIBILITY.get(student_grade, [student_grade])
    return any(g in applies_to for g in compat)


def map_gaps_to_actions(gaps: Dict, signals: Dict,
                         grade_level: Optional[str] = None) -> List[str]:
    """
    갭 분석 결과 → 적용할 action_id 리스트.
    LLM 없이 결정론적 규칙으로 매핑.
    """
    action_ids: List[str] = []

    # 1) 등급 갭 기반 처방
    sev = gaps.get("grade_severity")
    if sev == "small":
        action_ids.append("grade_gap_0_3")
    elif sev == "medium":
        action_ids.append("grade_gap_0_5")
    elif sev == "large":
        action_ids.append("grade_gap_0_7_plus")
    # safe 면 등급 처방 없음

    # 2) 전형 갭 기반 처방
    top_track = gaps.get("track_top_id")
    if top_track == "haksang":
        action_ids.append("track_haksang_prep")
    elif top_track == "gyogwa":
        action_ids.append("track_gyogwa_prep")
    elif top_track == "nonsul":
        action_ids.append("track_nonsul_prep")
    elif top_track == "jeongsi":
        action_ids.append("track_jeongsi_prep")
    elif top_track == "regional":
        action_ids.append("track_regional_prep")

    # 3) 비교과 부족 처방
    if not signals.get("extracurricular_strong"):
        if signals.get("med_track_fit"):
            action_ids.append("profile_extracurricular_medical")
        elif signals.get("sci_track_fit") or signals.get("humanities_media_fit") is False:
            action_ids.append("profile_extracurricular_stem")
        else:
            action_ids.append("profile_extracurricular_humanities")

    # 4) 자기주도성 부족
    if signals.get("self_directed") is False and grade_level in ("고1", "고2"):
        action_ids.append("profile_self_directed")

    # 5) 특수 처방: 의약학 + 고3 = MMI
    if signals.get("med_track_fit") and grade_level == "고3":
        action_ids.append("targeted_mmi_medical")

    # 6) 특수 처방: 인문 + 글쓰기 강점
    if signals.get("essay_strength") and signals.get("humanities_media_fit"):
        action_ids.append("targeted_essay_humanities")

    # 학년 호환성 필터 (인접 학년 처방도 허용)
    if grade_level:
        action_ids = [
            aid for aid in action_ids
            if _grade_compatible(grade_level,
                                  ACTION_LIBRARY.get(aid, {}).get("applies_to_grade", []))
        ]

    # 중복 제거 + 최대 4개로 제한 (정보 과부하 방지)
    seen = set()
    final = []
    for aid in action_ids:
        if aid not in seen:
            seen.add(aid)
            final.append(aid)
        if len(final) >= 4:
            break
    return final


# ═════════════════════════════════════════════════════════════════
# D. 분기 스케줄링
# ═════════════════════════════════════════════════════════════════

def schedule_actions(action_ids: List[str], timeline: Dict) -> List[Dict]:
    """
    선정된 처방의 마일스톤을 분기 라벨에 매핑.
    반환: [{'action_id', 'title', 'quarter_label', 'milestone', 'source_basis'}, ...]
    """
    if not action_ids:
        return []
    quarters = timeline.get("quarters", [])
    n_quarters = len(quarters)
    if n_quarters == 0:
        return []

    scheduled = []
    for aid in action_ids:
        action = get_action(aid)
        if not action:
            continue
        for q_idx, milestone in action.get("milestones", []):
            # action 의 분기 인덱스를 timeline 분기에 매핑
            target_q = min(q_idx, n_quarters - 1)
            scheduled.append({
                "action_id": aid,
                "action_title": action["title"],
                "category": action.get("category"),
                "quarter_label": quarters[target_q]["label"],
                "months_from_now": quarters[target_q]["months_from_now"],
                "milestone": milestone,
                "source_basis": action.get("source_basis"),
            })

    # 분기 순서대로 정렬
    scheduled.sort(key=lambda x: x["months_from_now"])
    return scheduled


# ═════════════════════════════════════════════════════════════════
# E. 통합 — 학생-대학 쌍 → 완성 로드맵
# ═════════════════════════════════════════════════════════════════

def build_roadmap(rec: Dict, signals: Dict,
                   answer_result: Optional[Dict] = None,
                   track_recs: Optional[List[Dict]] = None) -> Dict:
    """대학 카드 1개에 대한 완성 로드맵."""
    grade_level = detect_grade_level(signals, answer_result)
    timeline = compute_timeline(grade_level)
    gaps = analyze_gaps(rec, signals, track_recs)
    action_ids = map_gaps_to_actions(gaps, signals, grade_level)
    schedule = schedule_actions(action_ids, timeline)

    return {
        "grade_level": grade_level,
        "timeline": timeline,
        "gaps": gaps,
        "action_ids": action_ids,
        "actions": [get_action(aid) for aid in action_ids],
        "schedule": schedule,
        "disclaimer": "본 로드맵은 일반 가이드입니다. 학생 개별 상황에 맞춰 "
                      "컨설턴트와 상의 후 적용하십시오.",
    }
