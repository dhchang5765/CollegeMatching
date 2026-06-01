"""
enrich_talents.py  (standalone 유틸 — app 에서 import 안 함)
─────────────────────────────────────────────────────────────────────
목적
  merged_university_db_v3_trimmed.json 에서 talent_keywords 가 비어 있는
  대학(현재 155개)의 인재상 키워드를 보강한다.

중요 원칙 (사용자 선호: 사실 우선, 추측 금지, 사실/의견 구분)
  - 대학 인재상은 각 대학이 공표한 저작물이다. 본 스크립트가 LLM 으로
    생성한 키워드는 '검증된 사실'이 아니라 '생성 추정치'다.
  - 따라서 생성된 항목에는 반드시 talent_source 와 생성 시각을 태깅한다.
        talent_source = "llm-generated-unverified"
    컨설턴트가 각 대학 입학처 공식 인재상과 대조해 검증한 뒤에만
    "verified" 로 승격해야 한다.
  - 기존에 값이 있는 30개 대학은 절대 덮어쓰지 않는다.
  - 원본을 수정하지 않고 새 파일로 출력한다(비파괴).

사용법
  # 1) 명칭 오기/중복만 먼저 진단 (보강 전 정리 권장)
  python enrich_talents.py --diagnose

  # 2) 무엇을 생성할지 미리보기 (API 호출 없음)
  python enrich_talents.py --dry-run

  # 3) 실제 생성 (GEMINI_API_KEY 환경변수 필요)
  GEMINI_API_KEY=... python enrich_talents.py --run --out merged_university_db_v3_enriched.json
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Dict, List, Tuple

DEFAULT_IN = "merged_university_db_v3_talents.json"

# 정규화 결합 오기 패턴 — '○○대' 약칭에 '학교'가 덧붙은 명백한 결합 오류만.
# (예: 교육대→교대 + 학교 = "교대학교", 여자대→여대 + 학교 = "여대학교")
# '공대학교/신대학교' 등은 한국항공대·한신대처럼 정상 명칭과 겹쳐 오탐이 커
# 패턴에서 제외한다(오탐 방지, 사용자 검토 신뢰성 우선).
MALFORMED_SUFFIX = re.compile(r"(교대학교|여대학교|과기대학교|체대학교)$")

# 동일 기관으로 의심되는 중복 쌍 (수동 검토 대상 — 자동 병합하지 않음)
SUSPECTED_DUP_PAIRS = [
    ("경상국립대학교", "경상대학교"),
    ("서울과학기술대학교", "서울과기대학교"),
    ("차의과학대학교", "차의과대학교"),
    ("한경국립대학교", "한경대학교"),
    ("금오공과대학교", "금오공대학교"),
]


def load_db(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def diagnose(db: Dict) -> None:
    unis = db.get("universities", [])
    names = [u.get("name", "") for u in unis]
    have_kw = [u["name"] for u in unis if u.get("talent_keywords")]
    no_kw = [u["name"] for u in unis if not u.get("talent_keywords")]
    no_stmt = [u for u in unis if not u.get("talent_statement")]

    print(f"총 대학: {len(unis)}")
    print(f"talent_keywords 보유: {len(have_kw)} / 미보유: {len(no_kw)}")
    print(f"talent_statement 공란: {len(no_stmt)}")
    print()
    malformed = [n for n in names if MALFORMED_SUFFIX.search(n)]
    print(f"[명칭 오기 의심] {len(malformed)}건 (정규화 결합 오류 추정):")
    print("  " + ", ".join(malformed))
    print()
    print("[중복 의심 쌍] (자동 병합 안 함 — 수동 검토 필요):")
    for a, b in SUSPECTED_DUP_PAIRS:
        print(f"  {a} {'O' if a in names else 'X'}  /  {b} {'O' if b in names else 'X'}")


def build_prompt(univ_name: str, region: str, departments: List[str]) -> str:
    dept_hint = ", ".join(departments[:12]) if departments else "(학과 정보 없음)"
    return (
        "너는 한국 대학 인재상 데이터를 정리하는 도우미다. 추측·창작 금지.\n"
        f"대학명: {univ_name}\n지역: {region or '미상'}\n주요 학과: {dept_hint}\n\n"
        "이 대학이 공식적으로 표방하는 인재상의 핵심 키워드를 5~8개 추출하라.\n"
        "확신할 수 없으면 빈 배열을 반환하라. 일반적 미사여구(글로벌, 창의 등)만 "
        "나열하지 말고, 가능한 한 해당 대학 고유의 표현을 사용하라.\n"
        '아래 JSON 만 출력: {"talent_keywords": [...], "confidence": "high|medium|low"}'
    )


def generate_keywords(client, model: str, univ: Dict) -> Tuple[List[str], str]:
    name = univ.get("name", "")
    region = univ.get("region", "")
    depts = [d.get("name", "") for d in univ.get("departments", [])][:12]
    prompt = build_prompt(name, region, depts)
    try:
        resp = client.models.generate_content(
            model=model, contents=prompt,
            config={"response_mime_type": "application/json", "temperature": 0},
        )
        data = json.loads(resp.text)
        kws = [k for k in data.get("talent_keywords", []) if isinstance(k, str)][:8]
        conf = data.get("confidence", "low")
        return kws, conf
    except Exception as e:
        print(f"  ! {name}: 생성 실패 ({e})", file=sys.stderr)
        return [], "error"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=DEFAULT_IN)
    ap.add_argument("--out", default="merged_university_db_v3_enriched.json")
    ap.add_argument("--diagnose", action="store_true", help="명칭/중복 진단만")
    ap.add_argument("--dry-run", action="store_true", help="대상만 출력(API 호출 없음)")
    ap.add_argument("--run", action="store_true", help="실제 생성")
    ap.add_argument("--model", default=os.getenv("GEMINI_MODEL", "gemini-3-flash"))
    args = ap.parse_args()

    db = load_db(args.inp)
    unis = db.get("universities", [])

    if args.diagnose:
        diagnose(db)
        return

    targets = [u for u in unis if not u.get("talent_keywords")]
    print(f"보강 대상(talent_keywords 공란): {len(targets)}개")

    if args.dry_run or not args.run:
        for u in targets:
            print(f"  - {u.get('name')} ({u.get('region') or '지역미상'})")
        print("\n[dry-run] 실제 생성하려면 --run + GEMINI_API_KEY 필요.")
        return

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY 환경변수가 없습니다.", file=sys.stderr)
        sys.exit(1)
    try:
        from google import genai
    except ImportError:
        print("google-genai 미설치: pip install google-genai", file=sys.stderr)
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    now = datetime.now(timezone.utc).isoformat()
    filled, skipped = 0, 0
    for u in targets:
        kws, conf = generate_keywords(client, args.model, u)
        if not kws:
            skipped += 1
            continue
        u["talent_keywords"] = kws
        # 출처·신뢰도 태깅 — 검증 전까지 '사실'로 취급 금지
        u["talent_source"] = "llm-generated-unverified"
        u["talent_confidence"] = conf
        u["talent_generated_at"] = now
        filled += 1
        print(f"  + {u.get('name')}: {kws} (conf={conf})")

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    print(f"\n완료: {filled}개 생성 / {skipped}개 건너뜀(저신뢰) → {args.out}")
    print("주의: 생성 항목은 모두 'llm-generated-unverified'. 입학처 공식 "
          "인재상과 대조 검증 후 talent_source 를 'verified'로 승격하십시오.")


if __name__ == "__main__":
    main()
