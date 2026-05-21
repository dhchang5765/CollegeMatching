"""
admission_tracks.py
─────────────────────────────────────────────────────────────────────
A3 — 학생 신호 기반 전형 추천.

대한민국 대입 전형 (사실)
─────────────────────────────────────────────────────────────────────
크게 수시(75%)와 정시(25%)로 나뉜다.

수시
  1) 학생부종합전형(학종)
     - 내신 + 비교과(생기부 활동·수상·동아리·세특·진로) 정성 평가
     - 자기주도성·전공적합성·발전가능성·인성·창의성 5축
     - 활동 풍부·자기주도형 학생에게 유리
  2) 학생부교과전형(교과)
     - 내신 위주(정량). 비교과 거의 안 봄
     - 내신 우수·비교과 약함·논술 거부 학생에게 유리
  3) 논술전형
     - 내신 + 논술시험. 일부 대학은 수능 최저 적용
     - 글쓰기 강점·중상위권 내신·내신 약점 보완 필요 학생에게 유리
  4) 특기자전형(어학/수학/과학/예체능)
     - 특정 분야 검증된 성과 필수(공인성적·수상)
  5) 지역균형(서울대 등) / 지역인재(지방 의약학)
     - 학교장 추천 또는 해당 권역 졸업 자격
     - 일반고·우수 내신 / 해당 지역 거주 학생에게 유리

정시
  6) 수능위주전형(정시)
     - 수능 표준점수·백분위 위주(일부 학종 정시·실기 정시 등 있음)
     - 모의고사 우수·내신 약점·수능형 학생에게 유리

산출 방식: 학생 신호 → 각 전형별 적합도 0~100점
"""
from __future__ import annotations
from typing import Dict, List, Optional, Tuple

# 전형 ID → 정식 명칭
TRACK_LABEL = {
    "haksang":   "학생부종합전형 (학종)",
    "gyogwa":    "학생부교과전형 (교과)",
    "nonsul":    "논술전형",
    "jeongsi":   "수능위주전형 (정시)",
    "balanced":  "지역균형전형",  # 서울대·고려대 등 학교장 추천형
    "regional":  "지역인재전형",  # 지방 의약학·일부 학과
    "teukgi":    "특기자전형",
}

# 한국 입시 권역 매핑 (지역인재 자격 판정용 — 사실: 2024학년도부터 지방 의대는 신입생의
# 40% 이상을 지역인재로 의무 선발)
REGIONAL_AREAS = {
    "대구·경북": ["대구", "경북", "수성구", "범어동", "달서구", "달성", "경산", "포항", "구미", "안동"],
    "부산·울산·경남": ["부산", "울산", "경남", "창원", "김해", "양산", "진주"],
    "광주·전남·전북": ["광주", "전남", "전북", "전주", "익산", "여수", "순천", "목포"],
    "대전·세종·충남·충북": ["대전", "세종", "충남", "충북", "천안", "청주", "공주", "충주"],
    "강원": ["강원", "춘천", "원주", "강릉"],
    "제주": ["제주"],
    "수도권": ["서울", "경기", "인천", "성남", "수원", "고양", "용인", "안양", "강남", "분당", "송파", "노원"],
}


def detect_student_region(signals: Dict) -> Optional[str]:
    """학생 거주 권역 식별 (HTML/답변 텍스트의 지역명에서 추출)."""
    raw = (signals.get("raw_text", "") or "")
    for area, kws in REGIONAL_AREAS.items():
        for kw in kws:
            if kw in raw:
                return area
    return None


def _grade_band(g: Optional[float]) -> str:
    """학생 등급 → 밴드 라벨."""
    if g is None:
        return "unknown"
    if g <= 1.5: return "top"        # 1.0~1.5
    if g <= 2.0: return "high"       # 1.5~2.0
    if g <= 2.5: return "midhigh"    # 2.0~2.5
    if g <= 3.5: return "mid"        # 2.5~3.5
    return "low"                     # 3.5~


def recommend_tracks(signals: Dict, answer_result: Optional[Dict] = None
                     ) -> List[Dict]:
    """
    학생 신호 → 전형별 적합도 점수 + 근거 산출.
    반환: [{ id, label, score(0~100), reasons[], cautions[] }, ...] (점수 내림차순)
    """
    grade = signals.get("overall_grade")
    band = _grade_band(grade)
    rs = (answer_result or {}).get("rule_signals", {}) if answer_result else {}
    answers = ((rs or {}).get("evidence", []))  # 사용 안 함, 미래 확장용

    # 답변 JSON 기반 추가 신호 (있으면 사용)
    explicit_admission = signals.get("admission_orientation", "") or ""
    susi_focus = "수시" in explicit_admission
    jeongsi_focus = "정시" in explicit_admission and "수시" not in explicit_admission
    essay = bool(signals.get("essay_strength"))
    extracur = bool(signals.get("extracurricular_strong"))
    self_dir = bool(signals.get("self_directed"))
    med = bool(signals.get("med_track_fit"))

    # 답변에서 명시적 논술 거부/수시파/일반고 정보 추출
    rule_sig = (answer_result or {}).get("rule_signals", {}) or {}
    nonsul_rejected = False
    is_general_school = True  # 기본 가정(일반고)
    is_autonomous = False     # 자사고/특목고
    for ev in rule_sig.get("evidence", []) or []:
        q = (ev.get("quote") or "").lower()
        if "논술" in q and ("쳐다보지" in q or "안 칠" in q or "낮아서" in q or "극혐" in q):
            nonsul_rejected = True
    raw = (signals.get("raw_text") or "")
    if "자율형" in raw or "자사고" in raw or "특목고" in raw or "외고" in raw or "과학고" in raw:
        is_general_school = False
        is_autonomous = True

    student_area = detect_student_region(signals)

    out: List[Dict] = []

    # ── 1) 학생부종합 (학종) ──────────────────────────────
    score = 50.0
    reasons, cautions = [], []
    if extracur:
        score += 22; reasons.append("비교과 활동 풍부")
    else:
        score -= 18; cautions.append("비교과 활동 부족 — 학종 약점")
    if self_dir:
        score += 15; reasons.append("자기주도성 신호")
    if susi_focus:
        score += 8; reasons.append("수시 중심 전략")
    if band in ("top", "high"):
        score += 10; reasons.append(f"내신 {band} 구간(우수)")
    elif band == "low":
        score -= 12; cautions.append("내신 약점")
    out.append({"id":"haksang","label":TRACK_LABEL["haksang"],
                "score":max(0,min(100,score)), "reasons":reasons, "cautions":cautions})

    # ── 2) 학생부교과 (교과) ──────────────────────────────
    score = 45.0
    reasons, cautions = [], []
    if band == "top":
        score += 35; reasons.append("내신 최상위(1.5 이내) — 교과 강력 추천")
    elif band == "high":
        score += 25; reasons.append("내신 상위(2.0 이내) — 교과 적합")
    elif band == "midhigh":
        score += 10; reasons.append("내신 중상위")
    else:
        score -= 15; cautions.append("교과는 내신이 절대 기준")
    if not extracur:
        score += 12; reasons.append("비교과 부족 → 교과가 학종보다 유리")
    if nonsul_rejected:
        score += 5; reasons.append("논술 비선호 → 교과 비중↑")
    if not is_general_school:
        score -= 10; cautions.append("자사고/특목고는 교과 내신 불리")
    out.append({"id":"gyogwa","label":TRACK_LABEL["gyogwa"],
                "score":max(0,min(100,score)), "reasons":reasons, "cautions":cautions})

    # ── 3) 논술전형 ───────────────────────────────────────
    score = 35.0
    reasons, cautions = [], []
    if essay:
        score += 30; reasons.append("논술/글쓰기 강점")
    if band in ("mid", "midhigh"):
        score += 15; reasons.append("논술은 중위권 내신에서 유리")
    if band in ("top", "high"):
        score -= 10; cautions.append("최상위 내신은 학종·교과가 더 유리")
    if nonsul_rejected:
        score -= 35; cautions.append("학생 본인이 논술 명시적 거부")
    if signals.get("humanities_media_fit"):
        score += 8
    out.append({"id":"nonsul","label":TRACK_LABEL["nonsul"],
                "score":max(0,min(100,score)), "reasons":reasons, "cautions":cautions})

    # ── 4) 수능위주(정시) ─────────────────────────────────
    score = 35.0
    reasons, cautions = [], []
    if jeongsi_focus:
        score += 30; reasons.append("정시 중심 전략 명시")
    if susi_focus:
        score -= 18; cautions.append("수시파 — 정시 비중 낮음")
    if signals.get("math_risk"):
        score -= 10; cautions.append("수학 위험 — 수능 불리")
    # 모의고사가 내신보다 좋으면 정시 유리(추정 — 정확한 모의고사 등급 데이터 필요)
    out.append({"id":"jeongsi","label":TRACK_LABEL["jeongsi"],
                "score":max(0,min(100,score)), "reasons":reasons, "cautions":cautions})

    # ── 5) 지역균형 (학교장 추천형) ──────────────────────
    score = 35.0
    reasons, cautions = [], []
    if is_general_school:
        score += 18; reasons.append("일반고 자격(지역균형 대상)")
    else:
        score -= 25; cautions.append("자사고·특목고 → 지역균형 자격 제한")
    if band == "top":
        score += 25; reasons.append("내신 최상위 — 지역균형 핵심 조건")
    elif band == "high":
        score += 12; reasons.append("내신 상위")
    else:
        score -= 10; cautions.append("지역균형은 내신 최상위 필수")
    out.append({"id":"balanced","label":TRACK_LABEL["balanced"],
                "score":max(0,min(100,score)), "reasons":reasons, "cautions":cautions})

    # ── 6) 지역인재 (지방 의약학·일부 학과) ──────────────
    score = 25.0
    reasons, cautions = [], []
    if student_area and student_area != "수도권":
        score += 35
        reasons.append(f"비수도권 거주({student_area}) — 지역인재 자격")
        if med:
            score += 20
            reasons.append("의약학 지망 — 지방 의대 지역인재 비중 40% 이상(2024~)")
    elif student_area == "수도권":
        score -= 25; cautions.append("수도권 거주 — 지역인재 자격 없음")
    else:
        cautions.append("거주 권역 미확인")
    if band in ("top", "high"):
        score += 10; reasons.append("내신 우수")
    out.append({"id":"regional","label":TRACK_LABEL["regional"],
                "score":max(0,min(100,score)), "reasons":reasons, "cautions":cautions})

    # 점수 내림차순
    out.sort(key=lambda x: -x["score"])
    return out


def match_university_tracks(rec: Dict, track_scores: List[Dict]) -> List[Dict]:
    """
    추천 대학의 실제 admissions 트랙명과 학생 전형 적합도를 교차.
    반환: 그 대학에서 학생이 노릴 만한 전형 목록(점수순).
    """
    detail = rec.get("matched_department_detail") or {}
    univ_tracks = []
    # detail 에 단일 track_name 만 있어 정밀 매칭은 어려움 — 표시는 학생 적합도 Top3 로
    student_top = track_scores[:3]
    return [
        {"label": t["label"], "score": t["score"],
         "reasons": t["reasons"][:2], "cautions": t["cautions"][:1]}
        for t in student_top
    ]
