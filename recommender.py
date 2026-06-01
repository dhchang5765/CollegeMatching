"""
recommender.py
─────────────────────────────────────────────────────────────────────
app.py 에서 분리 — 대학 추천 핵심 알고리즘.
  · 합격선 밴드 파싱 / 지원군 분류(안정·적정·상향·도전)
  · 4축 적합도(합격선35 / 진로25 / 전형25 / 인재상15) + 보너스
  · 등급 기반 추천(C/E 옵션) + 지원군 균형 분배

함수 본문은 원본과 동일(동작 보존).
"""
from __future__ import annotations
import re
from typing import Dict, List, Tuple, Optional

from constants import DEPT_ALIAS
from utils import normalize_major_name


def parse_grade_band(s: str) -> Tuple[Optional[float], Optional[float]]:
    if not s:
        return None, None
    m = re.match(r"\s*([0-9.]+)\s*-\s*([0-9.]+)\s*", str(s))
    if not m:
        return None, None
    return float(m.group(1)), float(m.group(2))

def extract_best_admission_band(univ: Dict, target_departments: List[str]) -> Tuple[Optional[str], Optional[Dict]]:
    best = None
    best_dep = None
    for dep in univ.get("departments", []):
        dep_name = dep.get("name", "")
        if not any(t in dep_name or dep_name in t for t in target_departments):
            continue
        for adm in dep.get("admissions", []):
            band = adm.get("min_grade_band")
            if band:
                lo, hi = parse_grade_band(band)
                if lo is None:
                    continue
                if best is None or lo < parse_grade_band(best)[0]:
                    best = band
                    best_dep = {
                        "department": dep_name,
                        "track_name": adm.get("track_name"),
                        "band": band,
                    }
    return best, best_dep

def admission_band_score(overall_grade: Optional[float], grade_band: Optional[str]) -> float:
    if overall_grade is None or not grade_band:
        return 55.0
    lo, hi = parse_grade_band(grade_band)
    if lo is None:
        return 55.0

    if overall_grade < lo:
        return 92.0   # 학생이 합격선보다 좋음 → 안정
    if lo <= overall_grade <= hi:
        return 80.0   # 합격선 범위 안 → 적정
    if overall_grade <= hi + 0.7:
        return 65.0   # 합격선 약간 위 → 상향(도전)
    return 45.0       # 합격선 많이 위 → 어려움


def classify_support_level(overall_grade: Optional[float],
                            grade_band: Optional[str]) -> Tuple[str, str]:
    """
    A2 — 학생 등급 vs 합격선 비교로 지원군 분류 (한국 입시 컨설팅 표준 용어).
    반환: (라벨, 한 줄 설명)

    등급은 낮을수록 좋다는 점을 반영.
    """
    if overall_grade is None or not grade_band:
        return ("정보부족", "학생 등급 또는 합격선 데이터가 없습니다.")
    lo, hi = parse_grade_band(grade_band)
    if lo is None:
        return ("정보부족", "합격선 데이터 형식을 해석할 수 없습니다.")

    # 학생 등급이 합격선 하한보다 1.5 이상 좋음 — 사실상 의미 없는 하향
    if overall_grade <= lo - 1.5:
        return ("하향(과도)", f"학생 등급 {overall_grade} 가 합격선 {lo}-{hi} 보다 1.5 이상 좋음 — 추천 의미 낮음")
    # 학생 등급이 합격선 하한보다 0.3~1.5 좋음
    if overall_grade <= lo - 0.3:
        return ("안정", f"학생 등급 {overall_grade} ≤ 합격선 {lo}-{hi}")
    # 학생 등급이 합격선 범위 안 (약간 좋음 포함)
    if overall_grade <= hi:
        return ("적정", f"학생 등급 {overall_grade} ∈ 합격선 {lo}-{hi}")
    # 합격선 약간 위
    if overall_grade <= hi + 0.3:
        return ("상향", f"학생 등급 {overall_grade} 가 합격선 {lo}-{hi} 보다 0.3 이내로 못함")
    if overall_grade <= hi + 0.7:
        return ("상향(도전)", f"학생 등급 {overall_grade} 가 합격선 {lo}-{hi} 보다 0.4~0.7 못함")
    return ("재고", f"학생 등급 {overall_grade} 가 합격선 {lo}-{hi} 보다 0.7 이상 못함")

def career_match_score(target_departments: List[str], university: Dict) -> Tuple[float, int]:
    """
    진로 일치도: 학생 추천 학과 1·2·3순위가 그 대학에 있는지 우선순위 가중.
    1순위 매칭 = 50점, 2순위 = 30점, 3순위 = 20점 → 합 최대 100점.
    학과명 매칭은 별칭(DEPT_ALIAS)을 통한 유연 매칭.
    """
    if not target_departments:
        return 0.0, 0

    from constants import DEPT_ALIAS
    weights = [50.0, 30.0, 20.0]  # 1·2·3순위 가중치
    score = 0.0
    matched_count = 0

    dept_names = []
    for dept in university.get("departments", []):
        n = dept.get("name", "")
        if n:
            dept_names.append(n)
            for alias in (dept.get("aliases") or []):
                dept_names.append(alias)

    for rank, target in enumerate(target_departments[:3]):
        # 별칭까지 포함한 매칭
        target_aliases = [target] + list(DEPT_ALIAS.get(target, []))
        for n in dept_names:
            if any(a in n or n in a for a in target_aliases):
                score += weights[rank]
                matched_count += 1
                break  # 한 순위당 1개만 카운트
    return min(100.0, score), matched_count


def track_match_score(track_recs: Optional[List[Dict]], university: Dict,
                       dep_match: Optional[Dict]) -> float:
    """
    전형 적합도: 학생의 추천 전형 Top1 점수를 기반으로,
    그 대학의 admissions 트랙에 해당 전형이 있으면 100% 반영, 없으면 70%만.
    """
    if not track_recs:
        return 55.0
    top_track = track_recs[0]
    student_track_id = top_track.get("id", "")
    student_score = float(top_track.get("score", 0))

    # 대학 admissions 트랙 명에서 해당 전형 식별
    track_keyword_map = {
        "haksang": ["학종", "학생부종합", "종합"],
        "gyogwa":  ["교과", "학생부교과"],
        "nonsul":  ["논술"],
        "jeongsi": ["정시", "수능"],
        "balanced":["지역균형", "학교장추천", "고른기회"],
        "regional":["지역인재"],
        "teukgi":  ["특기자", "실기"],
    }
    target_kws = track_keyword_map.get(student_track_id, [])
    if not target_kws:
        return student_score * 0.85

    # 대학 학과의 admissions 에서 매칭 트랙 검색
    has_track = False
    for dept in university.get("departments", []):
        for adm in dept.get("admissions", []):
            tname = (adm.get("track_name") or "") + " " + (adm.get("type") or "")
            if any(k in tname for k in target_kws):
                has_track = True
                break
        if has_track:
            break

    return student_score if has_track else student_score * 0.7


def major_match_score(target_departments: List[str], university: Dict) -> Tuple[float, List[str]]:
    score = 0.0
    matched = []

    targets = [normalize_major_name(t) for t in target_departments if t]

    for dep in university.get("departments", []):
        dep_name = dep.get("name", "")
        dep_aliases = dep.get("aliases", []) or []
        candidates = [dep_name] + dep_aliases
        norm_candidates = [normalize_major_name(x) for x in candidates if x]

        for target, raw_target in zip(targets, target_departments):
            for cand, raw_cand in zip(norm_candidates, candidates):
                if not cand:
                    continue
                if target == cand:
                    score += 30
                    matched.append(dep_name)
                    break
                elif target in cand or cand in target:
                    score += 22
                    matched.append(dep_name)
                    break
                elif (
                    ("인공지능" in raw_target and any(k in raw_cand for k in ["AI", "인공지능", "지능정보", "컴퓨터"]))
                    or ("데이터" in raw_target and any(k in raw_cand for k in ["데이터", "통계", "컴퓨터", "AI"]))
                    or ("소프트웨어" in raw_target and any(k in raw_cand for k in ["소프트웨어", "컴퓨터", "정보통신"]))
                ):
                    score += 18
                    matched.append(dep_name)
                    break

    return score, list(dict.fromkeys(matched))


def target_bonus(university_name: str, signals: Dict) -> float:
    target = signals.get("target_university")
    if not target:
        return 0.0

    normalized_name = university_name.lower()

    alias_map = {
        "KAIST": ["kaist", "카이스트", "한국과학기술원"],
        "DGIST": ["dgist", "디지스트", "대구경북과학기술원"],
        "GIST": ["gist", "지스트", "광주과학기술원"],
        "UNIST": ["unist", "유니스트", "울산과학기술원"],
    }

    if target in alias_map:
        if any(alias in normalized_name for alias in [a.lower() for a in alias_map[target]]):
            return 12.0
    elif target.lower() in normalized_name:
        return 12.0

    return 0.0


def recommend_universities(db: Dict, signals: Dict, target_departments: List[str],
                            top_n: int = 5,
                            answer_result: Optional[Dict] = None,
                            track_recs: Optional[List[Dict]] = None) -> List[Dict]:
    """
    새 적합도 산출 (4축 + 보너스):
      - 합격선 적합도 35% (객관)
      - 진로 일치도 25% (학생 추천 학과 1·2·3 우선순위 가중)
      - 전형 적합도 25% (학생 추천 전형 × 대학 트랙 가용성)
      - 인재상 유사도 15% (상대 percentile 임베딩)
      - 보너스 최대 +25 (목표대학 가산)
      - 100점 상한
    """
    overall_grade = signals.get("overall_grade")

    # 1) 후보 대학 필터링 (학과 매칭 0인 대학 제외)
    candidates = []
    for u in db.get("universities", []):
        mscore_raw, matched = major_match_score(target_departments, u)
        if mscore_raw <= 0:
            continue
        candidates.append((u, mscore_raw, matched))

    if not candidates:
        return []

    # 2) 인재상 유사도 — 학생 1명에 대해 모든 후보 대학 한 번에 percentile 계산
    from embeddings import (
        compute_talent_similarities_normalized,
        build_student_profile_text,
    )
    student_profile = build_student_profile_text(signals, answer_result)
    talent_scores_map = compute_talent_similarities_normalized(
        student_profile, [u for u, _, _ in candidates]
    )
    talent_backend_used = "embedding(percentile)" if talent_scores_map else "keyword(fallback)"

    # 3) 각 대학 점수 산출
    recs = []
    for u, mscore_raw, matched in candidates:
        univ_name = u.get("name", "")

        # ── 4축 적합도 ───────────────────────────────
        # (A) 합격선 적합도 (35%)
        band, dep_match = extract_best_admission_band(u, target_departments)
        band_score = admission_band_score(overall_grade, band)

        # (B) 진로 일치도 (25%) — 추천 학과 1·2·3 우선순위 가중
        career_score, career_matched_count = career_match_score(target_departments, u)

        # (C) 전형 적합도 (25%)
        trk_score = track_match_score(track_recs, u, dep_match)

        # (D) 인재상 유사도 (15%) — percentile 상대 점수
        if talent_scores_map and univ_name in talent_scores_map:
            talent_score = talent_scores_map[univ_name]
        else:
            # 임베딩 미가용 시 키워드 부분 일치 fallback (절대값)
            from embeddings import talent_similarity
            talent_score, _ = talent_similarity(
                student_profile, univ_name, u.get("talent_keywords", []) or []
            )

        # ── 보너스 (최대 +25) ────────────────────────
        bonus = target_bonus(univ_name, signals)  # 목표 대학 가산

        # 다수 학과 매칭 보너스 (2개 이상 매칭 시)
        multi_match_bonus = 5.0 if career_matched_count >= 2 else 0.0

        # 최종 산출
        base_score = (
            band_score   * 0.35 +
            career_score * 0.25 +
            trk_score    * 0.25 +
            talent_score * 0.15
        )
        bonus_total = min(25.0, bonus + multi_match_bonus)
        total = round(min(100.0, base_score + bonus_total), 2)

        # A2: 지원군 분류
        support_level, support_reason = classify_support_level(overall_grade, band)

        recs.append({
            "university": univ_name,
            "region": u.get("region"),
            "fit_score": total,
            "matched_departments": matched[:6],
            "talent_keywords": u.get("talent_keywords", []),
            "notes": u.get("notes", ""),
            "target_bonus": bonus,
            # 새 4축 점수
            "band_score": round(band_score, 1),
            "career_score": round(career_score, 1),
            "track_score": round(trk_score, 1),
            "talent_score": round(talent_score, 1),
            "talent_backend": talent_backend_used,
            "career_matched_count": career_matched_count,
            "matched_admission_band": band,
            "matched_department_detail": dep_match,
            "multi_match_bonus": multi_match_bonus,
            "support_level": support_level,
            "support_reason": support_reason,
        })

    # 정렬: fit_score 우선, 동점 시 진로 일치도 → 합격선 거리(가까운 순)
    def _sort_key(r):
        band = r.get("matched_admission_band", "")
        lo = 9.0
        m = re.match(r'\s*([0-9.]+)', band) if band else None
        if m:
            try: lo = float(m.group(1))
            except: pass
        og = (overall_grade if overall_grade is not None else 5.0)
        dist = abs(og - lo)
        # fit_score 내림차순(음수), career 내림차순(음수), 거리 오름차순
        return (-r["fit_score"], -r.get("career_score", 0), dist)
    recs.sort(key=_sort_key)
    return _distribute_by_support_level(recs, total=top_n)


def recommend_universities_by_grade(db: Dict, student_grade: float,
                                     top_n: int = 3,
                                     student_categories: Optional[List[str]] = None,
                                     dept_keywords: Optional[List[str]] = None,
                                     balanced_levels: bool = True) -> List[Dict]:
    """
    학생 등급 기반 대학 추천 (C 옵션: 카테고리 필터 + 키워드 필터 + E 옵션: 균형 분배).

    원리
      1) student_categories 가 주어지면 해당 카테고리 학과만 후보
      2) dept_keywords 가 주어지면 학과명에 키워드가 포함된 학과 우선
         (매칭 학과가 있으면 그 학과만 사용, 없으면 카테고리 필터 결과 그대로)
      3) balanced_levels=True 면 안정/적정/상향에서 1개씩 균형 분배 (E 옵션)
         False 면 거리 작은 순으로만 top_n

    student_categories: 학과 표준 카테고리 (인문/사회/자연/공학/의학/약학/교육/예체능)
    dept_keywords: 학생 target_departments 에서 추출한 핵심 키워드
                   (예: ['인공지능', '데이터', '컴퓨터'])
    """
    if student_grade is None:
        return []

    candidates = []
    for u in db.get("universities", []):
        # 학과 카테고리 필터 (1차)
        relevant_depts = u.get("departments", [])
        if student_categories:
            relevant_depts = [d for d in relevant_depts
                              if d.get("category") in student_categories]
        if not relevant_depts:
            continue

        # 학과명 키워드 필터 (2차) — 매칭 학과가 있으면 그 학과만, 없으면 그대로
        has_keyword_match = True  # 키워드 미사용 시 기본 True
        if dept_keywords:
            kw_matched = [d for d in relevant_depts
                          if any(kw in d.get("name", "") for kw in dept_keywords)]
            if kw_matched:
                relevant_depts = kw_matched
                has_keyword_match = True
            else:
                has_keyword_match = False  # fallback 발생 — 정렬 시 패널티

        # 각 학과의 최저 cutoff_p50
        dept_min_cuts = []
        for d in relevant_depts:
            cuts = [a.get("cutoff_p50") for a in d.get("admissions", [])
                    if a.get("cutoff_p50") is not None]
            if cuts:
                min_cut = min(cuts)
                dept_min_cuts.append({
                    "dept": d["name"],
                    "category": d.get("category", ""),
                    "min_cutoff": min_cut,
                    "min_track": next((a["track_name"] for a in d["admissions"]
                                       if a.get("cutoff_p50") == min_cut), ""),
                })
        if not dept_min_cuts:
            continue

        rep = min(dept_min_cuts, key=lambda x: x["min_cutoff"])
        dist = abs(student_grade - rep["min_cutoff"])

        if student_grade <= rep["min_cutoff"] - 1.5:
            level = "하향(과도)"
        elif student_grade <= rep["min_cutoff"] - 0.3:
            level = "안정"
        elif student_grade <= rep["min_cutoff"] + 0.3:
            level = "적정"
        elif student_grade <= rep["min_cutoff"] + 0.7:
            level = "상향"
        else:
            level = "상향(도전)"

        # 학생 등급보다 너무 좋은 합격선 대학은 추천에서 배제
        if level == "하향(과도)":
            continue

        candidates.append({
            "university": u["name"],
            "region": u.get("region", ""),
            "talent_keywords": u.get("talent_keywords", []),
            "talent_statement": u.get("talent_statement"),
            "aliases": u.get("aliases"),
            "representative_cutoff": round(rep["min_cutoff"], 2),
            "representative_dept": rep["dept"],
            "representative_track": rep["min_track"],
            "grade_distance": round(dist, 2),
            "support_level": level,
            "matched_categories": sorted(set(d["category"] for d in dept_min_cuts if d["category"])),
            "all_departments_summary": sorted(
                dept_min_cuts, key=lambda x: x["min_cutoff"]
            )[:6],
            "department_count": len(dept_min_cuts),
            "_departments_raw": relevant_depts,
            "_has_keyword_match": has_keyword_match,
        })

    level_priority = {"안정": 0, "적정": 1, "상향": 2, "상향(도전)": 3}
    # 정렬: 키워드 매칭 대학 우선 → 거리 작은 순 → 지원군 우선순위
    candidates.sort(key=lambda x: (
        not x.get("_has_keyword_match", True),  # False(미매칭)=1 → 뒤로
        x["grade_distance"],
        level_priority.get(x["support_level"], 9),
    ))

    if not balanced_levels:
        return candidates[:top_n]

    # E 옵션: 지원군별 균형 분배 — 각 지원군에서 거리 가장 작은 후보 1개씩
    # 우선순위: 적정 → 안정 → 상향 → 상향(도전)
    by_level: Dict[str, List[Dict]] = {}
    for c in candidates:
        by_level.setdefault(c["support_level"], []).append(c)

    selected = []
    pick_order = ["적정", "안정", "상향", "상향(도전)"]
    # 1단계: 각 지원군에서 1개씩
    for lv in pick_order:
        if lv in by_level and by_level[lv]:
            selected.append(by_level[lv].pop(0))
            if len(selected) >= top_n:
                break
    # 2단계: 부족분을 같은 우선순위로 추가
    if len(selected) < top_n:
        for lv in pick_order:
            while lv in by_level and by_level[lv] and len(selected) < top_n:
                selected.append(by_level[lv].pop(0))

    return selected[:top_n]


def _distribute_by_support_level(scored_recs: List[Dict], total: int = 5) -> List[Dict]:
    """
    한국 입시 컨설팅 표준 분배 (안정 1 + 적정 2 + 상향 2 = 5).
    fit_score 내림차순으로 정렬된 입력을 받아 지원군별로 의도적으로 분배한다.

    원칙
    - 분배 목표(plan)를 우선 채움
    - 특정 그룹이 비면 fallback 순서에 따라 인접 그룹에서 보충
    - 최종 결과는 fit_score 내림차순으로 다시 정렬해 카드 순서 유지
    """
    if not scored_recs:
        return []

    # '하향(과도)' 는 학생 등급보다 합격선이 1.5 이상 낮은 케이스 — 추천에서 제외
    scored_recs = [r for r in scored_recs
                    if r.get("support_level") != "하향(과도)"]
    if not scored_recs:
        return []

    # 지원군별 목표 개수 (한국 입시 컨설팅 표준 + 도전 슬롯 1개)
    # 안정 1 + 적정 2 + 상향 1 + 상향(도전) 1 = 5
    # → 의대·약대 등 초고 합격선 지망 학생에게도 도전 옵션 1개를 보장
    plan = {"안정": 1, "적정": 2, "상향": 1, "상향(도전)": 1}

    # 그룹화 (이미 fit_score 내림차순)
    groups: Dict[str, List[Dict]] = {}
    for r in scored_recs:
        lv = r.get("support_level") or "정보부족"
        groups.setdefault(lv, []).append(r)

    selected: List[Dict] = []
    # 1단계: plan 그대로 채움
    for lv, n in plan.items():
        if lv in groups:
            picks = groups[lv][:n]
            selected.extend(picks)
            groups[lv] = groups[lv][n:]

    # 2단계: 부족분을 fallback 순서로 채움
    # 적정 > 상향 > 상향(도전) > 안정 > 재고 > 정보부족 순
    fallback_order = ["적정", "상향", "상향(도전)", "안정", "재고", "정보부족"]
    while len(selected) < total:
        added = False
        for lv in fallback_order:
            if lv in groups and groups[lv]:
                selected.append(groups[lv].pop(0))
                added = True
                if len(selected) >= total:
                    break
        if not added:
            break  # 더 채울 후보가 없음

    # 최종 정렬: fit_score 내림차순
    selected.sort(key=lambda x: -x.get("fit_score", 0))
    return selected[:total]
