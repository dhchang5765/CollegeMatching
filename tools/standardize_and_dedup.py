"""
standardize_and_dedup.py  (standalone 유틸)
─────────────────────────────────────────────────────────────────────
② 8범주 이탈 키워드 표준화 + ③ 중복 대학 병합.

원칙
  - 비파괴: 새 파일로 출력.
  - 무손실: 표준화 전 키워드는 talent_keywords_original 에 백업(없을 때만).
  - 중복 병합: 학과/전형/별칭/인재상을 합치고, 입결 데이터가 많은 쪽을 base 로
              유지한 뒤 현행 정식명으로 통일. 입결 손실 없음(전형 dedup 으로만 정리).
  - 표준화 매핑은 명시 딕셔너리(결정론). 자동 추정 금지.
"""
from __future__ import annotations
import argparse
import json
from typing import Dict, List

STD = {"창의성", "글로벌", "전문성", "인성/봉사",
       "소통/협력", "도전/혁신", "융합지성", "실천"}

# ② 8범주 이탈 학교 → 표준화된 키워드(분석 매핑)
STANDARDIZE = {
    "순천대학교":     ["도전/혁신", "융합지성", "인성/봉사", "실천"],
    "신한대학교":     ["전문성", "글로벌", "융합지성"],
    "안동대학교":     ["인성/봉사"],
    "우석대학교":     ["도전/혁신"],
    "충북대학교":     ["도전/혁신", "융합지성", "인성/봉사"],
    "한국공학대학교": ["전문성", "융합지성", "창의성", "소통/협력", "도전/혁신"],
    "홍익대학교":     ["창의성", "소통/협력", "도전/혁신"],
}

# ③ 중복 쌍 → (이름A, 이름B, 통일 정식명). 같은 기관만.
#   경주대→신경주대 는 2024 교명 변경(리브랜딩)으로 동일 기관.
DUP_MERGES = [
    ("경상국립대학교", "경상대학교",       "경상국립대학교"),
    ("서울과학기술대학교", "서울과기대학교", "서울과학기술대학교"),
    ("차의과학대학교", "차의과대학교",     "차의과학대학교"),
    ("한경국립대학교", "한경대학교",       "한경국립대학교"),
    ("금오공과대학교", "금오공대학교",     "금오공과대학교"),
    ("신경주대학교", "경주대학교",         "신경주대학교"),
]


def _adm_count(u: Dict) -> int:
    return sum(len(d.get("admissions", [])) for d in u.get("departments", []))


def _merge_depts(base: Dict, other: Dict) -> None:
    """other 의 학과·전형을 base 로 병합(학과명 기준, 전형은 type+track_name dedup)."""
    by_name = {d.get("name"): d for d in base.get("departments", [])}
    for d in other.get("departments", []):
        nm = d.get("name")
        if nm not in by_name:
            base["departments"].append(d)
            by_name[nm] = d
        else:
            bd = by_name[nm]
            seen = {(a.get("type"), a.get("track_name"))
                    for a in bd.get("admissions", [])}
            for a in d.get("admissions", []):
                key = (a.get("type"), a.get("track_name"))
                if key not in seen:
                    bd.setdefault("admissions", []).append(a)
                    seen.add(key)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="merged_university_db_v3_talents.json")
    ap.add_argument("--out", default="merged_university_db_v3_clean.json")
    args = ap.parse_args()

    db = json.load(open(args.db, encoding="utf-8"))
    U = db["universities"]
    idx = {u["name"]: u for u in U}

    # ② 표준화 ──────────────────────────────────────────────
    std_done = []
    for name, new_kws in STANDARDIZE.items():
        u = idx.get(name)
        if not u:
            continue
        if "talent_keywords_original" not in u:
            u["talent_keywords_original"] = list(u.get("talent_keywords") or [])
        u["talent_keywords"] = list(new_kws)
        u["talent_source"] = "standardized-8cat"
        std_done.append(name)

    # ③ 중복 병합 ───────────────────────────────────────────
    drop_ids = set()
    merge_log = []
    for a, b, canonical in DUP_MERGES:
        ua, ub = idx.get(a), idx.get(b)
        if not ua or not ub:
            merge_log.append(f"  (건너뜀) {a} / {b} 중 일부 없음")
            continue
        # 입결 많은 쪽을 base
        base, other = (ua, ub) if _adm_count(ua) >= _adm_count(ub) else (ub, ua)
        _merge_depts(base, other)
        # 인재상: 비어있지 않은 쪽 우선
        if not base.get("talent_keywords") and other.get("talent_keywords"):
            base["talent_keywords"] = other["talent_keywords"]
            base["talent_source"] = other.get("talent_source", base.get("talent_source"))
        # 별칭: 두 원래 이름을 alias 로 (정식명 제외)
        aliases = set(base.get("aliases") or [])
        for nm in (a, b):
            if nm != canonical:
                aliases.add(nm)
        base["aliases"] = sorted(aliases)
        base["name"] = canonical
        # other 는 객체 식별자로 제거(이름 변경 후 충돌 방지)
        drop_ids.add(id(other))
        merge_log.append(f"  {a} + {b} → {canonical} "
                         f"(학과{len(base['departments'])}/전형{_adm_count(base)}, "
                         f"kw={base.get('talent_keywords')})")

    db["universities"] = [u for u in U if id(u) not in drop_ids]

    json.dump(db, open(args.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    print(f"[완료] → {args.out}")
    print(f"② 표준화: {len(std_done)}개 — {', '.join(std_done)}")
    print(f"③ 중복 병합: {len(merge_log)}건")
    for line in merge_log:
        print(line)
    print(f"대학 수: {len(U)} → {len(db['universities'])}")


if __name__ == "__main__":
    main()
