"""
apply_talents.py  (standalone 유틸 — app 에서 import 안 함)
─────────────────────────────────────────────────────────────────────
사용자 제공 인재상 키워드(표준 8범주 체계)를 DB 의 talent_keywords 에 반영.

원칙
  - 비파괴: 원본을 수정하지 않고 새 파일로 출력.
  - 무손실: 기존 talent_keywords 가 있으면 talent_keywords_original 에 백업한 뒤
            덮어쓴다(되돌리기 가능). 정보 손실 없음.
  - 출처 태깅: 반영 항목에 talent_source="user-provided-2026".
  - 결정론: 정규화 매칭 + 명시적 수동 브리지(애매한 자동 매칭 금지).

매칭
  - 정규화: '대학교'→'대', 공백/괄호/중점/하이픈 제거.
  - 그래도 어긋나는 명칭 artifact 는 MANUAL_BRIDGE 로 1:1 연결.
"""
from __future__ import annotations
import argparse
import json
import re
from typing import Dict


# DB 명칭 artifact ↔ 소스 키 (정규화로 안 잡히는 동일 기관만 명시)
MANUAL_BRIDGE = {
    # 소스 키 : DB 정식명
    "이화여대": "이화여자대학교",
    "한국외대": "한국외국어대학교",
    "서울신학대": "서울신대학교",
    "장로회신학대": "장로회신대학교",
    "한국기술교육대": "한국기술교대학교",
}


def norm(s: str) -> str:
    s = (s or "").strip()
    s = s.replace("대학교", "대").replace("학교", "")
    s = re.sub(r"[\s()·\-]", "", s)
    return s


def main():

    db = json.load(open("university_db.json", encoding="utf-8"))
    src = json.load(open("talent_keywords_source.json", encoding="utf-8"))
    unis = db["universities"]

    # 소스 정규화(중복 키는 키워드 많은 쪽 우선; 예: '충북대' vs '충북대 ')
    src_norm: Dict[str, tuple] = {}
    for k, v in src.items():
        nk = norm(k)
        if nk not in src_norm or len(v) > len(src_norm[nk][1]):
            src_norm[nk] = (k, v)

    # 수동 브리지를 DB정식명 기준 조회표로
    bridge_by_dbname = {dbname: norm(skey) for skey, dbname in MANUAL_BRIDGE.items()}

    filled, overwritten, still_empty = [], [], []
    used = set()

    for u in unis:
        name = u["name"]
        cands = [name] + (u.get("aliases") or [])
        hit = None
        # 1) 정규화 매칭
        for c in cands:
            nc = norm(c)
            if nc in src_norm:
                hit = nc
                break
        # 2) 수동 브리지
        if hit is None and name in bridge_by_dbname:
            hit = bridge_by_dbname[name]

        if hit is None:
            if not u.get("talent_keywords"):
                still_empty.append(name)
            continue

        used.add(hit)
        skey, kws = src_norm[hit]
        had = u.get("talent_keywords")
        if had:
            u["talent_keywords_original"] = had  # 백업(무손실)
            overwritten.append((name, skey))
        else:
            filled.append((name, skey))
        u["talent_keywords"] = list(kws)
        u["talent_source"] = "user-provided-2026"

    unmatched_src = sorted(src_norm[k][0] for k in src_norm if k not in used)

    json.dump(db, open("merged_university_db_v3_talents.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    print(f"[적용 완료] → merged_university_db_v3_talents.json")
    print(f"  신규 채움      : {len(filled)}")
    print(f"  덮어씀(백업有) : {len(overwritten)}")
    print(f"  잔여 공란      : {len(still_empty)}")
    print(f"  소스 미매칭(DB에 없는 학교): {len(unmatched_src)}")
    print(f"    → {', '.join(unmatched_src)}")
    print(f"  잔여 공란 목록 : {', '.join(still_empty)}")


if __name__ == "__main__":
    main()
