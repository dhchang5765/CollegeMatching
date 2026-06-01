"""
학과명 정규화 + 자동 그룹화 스크립트 (아이디어 ① 구현).

원리
  각 학과명에서 정규화 키를 추출하여, 같은 정규화 키를 가진 학과들끼리
  서로의 'aliases' 필드에 등록한다. 결과적으로 표기 변형만 다른 학과들은
  자동으로 alias 매핑이 완성된다.

정규화 단계 (한 방향으로 통일)
  1) 괄호 안 제거
  2) 영문 약어 → 한글 풀어쓰기 (AI→인공지능, SW→소프트웨어, IT→정보통신 등)
  3) 공통 수식어 제거 (글로벌, 국제, 융합, 미래, 첨단, 스마트, 신, 차세대)
  4) 학과 어미 한 번 제거 (학과, 학부, 전공, 과, 부)
  5) 공백 제거

예시
  "컴퓨터공학과" → "컴퓨터공학"
  "컴퓨터공학부" → "컴퓨터공학"
  "글로벌컴퓨터공학과" → "컴퓨터공학"
  "AI학과" → "인공지능"
  "인공지능학과" → "인공지능"
  → 위 4개 학과는 같은 그룹으로 묶임 (서로의 aliases)

거버넌스
  - 결정론적: 동일 입력 → 동일 출력
  - 같은 그룹 학과끼리만 alias 등록 (다른 대학 학과끼리도 가능)
  - 사용자가 결과 검토 후 부적절한 매핑은 수동 조정

입력
  - merged_university_db_v3_trimmed.json (현재 DB)

출력
  - merged_university_db_v3_trimmed.json (덮어쓰기, aliases 채움)
  - merged_university_db_v3_trimmed.backup_dept_alias.json (백업)
  - dept_alias_groups.json (검증용 그룹 보고서)

사용
  python3 group_dept_aliases.py
"""
import json
import re
from pathlib import Path
from collections import defaultdict

DB_PATH      = 'merged_university_db_v3_trimmed.json'
OUT_PATH     = 'merged_university_db_v3_trimmed.json'
BACKUP_PATH  = 'merged_university_db_v3_trimmed.backup_dept_alias.json'
REPORT_PATH  = 'dept_alias_groups.json'

# ─── 정규화 규칙 ─────────────────────────────────────────
# (앞 패턴 → 뒤 표준어) 단방향 변환
ABBR_MAP = [
    ('AI', '인공지능'),
    ('SW', '소프트웨어'),
    ('IT', '정보통신'),
    ('ICT', '정보통신'),
    ('IoT', '사물인터넷'),
    ('BT', '바이오'),
    ('CS', '컴퓨터과학'),
    ('EE', '전자공학'),
    ('ME', '기계공학'),
    ('CE', '컴퓨터공학'),
    ('MIS', '경영정보'),
]

# 학과 정체성과 무관한 공통 수식어
COMMON_MODIFIERS = [
    '글로벌', '국제', '융합', '미래', '첨단', '스마트',
    '신', '차세대', 'KSC', '국가전략',
]

# 학과 어미 (한 번만 제거)
DEPT_SUFFIXES = ['학과', '학부', '전공', '학', '과', '부']


def normalize_dept_name(name: str) -> str:
    """학과명 → 정규화 키."""
    if not name: return ''
    s = name.strip()

    # 1) 괄호 안 제거
    s = re.sub(r'\s*\([^)]*\)\s*', '', s)
    s = s.strip()

    # 2) 영문 약어 → 한글 표준어
    for abbr, full in ABBR_MAP:
        # 단어 경계 (앞뒤가 한글 또는 시작/끝)
        s = re.sub(rf'(?<![A-Za-z]){re.escape(abbr)}(?![A-Za-z])', full, s)

    # 3) 공통 수식어 제거 (어디에 있든)
    for mod in COMMON_MODIFIERS:
        s = s.replace(mod, '')

    # 4) 학과 어미 한 번만 제거 (긴 어미 우선)
    for suf in DEPT_SUFFIXES:
        if s.endswith(suf):
            s = s[:-len(suf)]
            break

    # 5) 공백·특수문자 제거
    s = re.sub(r'\s+', '', s)
    s = re.sub(r'[·•\-_/]', '', s)

    return s


def main():
    db = json.loads(Path(DB_PATH).read_text(encoding='utf-8'))
    Path(BACKUP_PATH).write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'백업: {BACKUP_PATH}')

    # 1) 모든 학과를 정규화 키로 그룹화
    #    같은 키 → 같은 alias 그룹
    groups: dict = defaultdict(list)  # norm_key -> [(univ_name, dept_name, dept_ref), ...]
    total_depts = 0
    for u in db['universities']:
        for d in u.get('departments', []):
            key = normalize_dept_name(d['name'])
            if not key or len(key) < 2:
                continue
            groups[key].append((u['name'], d['name'], d))
            total_depts += 1

    # 2) 각 학과의 aliases 필드를 같은 그룹의 다른 학과명으로 채움
    multi_groups = {k: v for k, v in groups.items() if len(v) >= 2}
    single_groups_n = sum(1 for k, v in groups.items() if len(v) == 1)

    alias_filled = 0
    for key, members in multi_groups.items():
        # 그룹 내 유니크한 학과명 집합 (대학 무관)
        unique_dept_names = sorted(set(m[1] for m in members))
        for univ, dept_name, dept_ref in members:
            # 자기 자신 제외한 그룹 동료들을 aliases 로 등록
            others = [n for n in unique_dept_names if n != dept_name]
            if others:
                # 기존 aliases 가 있으면 합치고, 없으면 새로 채움
                existing = dept_ref.get('aliases') or []
                merged = list(existing)
                seen = set(existing)
                for n in others:
                    if n not in seen:
                        merged.append(n); seen.add(n)
                dept_ref['aliases'] = merged
                alias_filled += 1

    # 3) 그룹화되지 않은 (단일) 학과는 aliases 가 null 유지

    # 4) 저장
    Path(OUT_PATH).write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding='utf-8')

    # 5) 검증용 그룹 보고서 저장
    report = {
        'meta': {
            'total_depts': total_depts,
            'unique_norm_keys': len(groups),
            'multi_member_groups': len(multi_groups),
            'single_member_groups': single_groups_n,
            'alias_filled_depts': alias_filled,
        },
        'groups': {
            key: sorted(set(m[1] for m in members))
            for key, members in sorted(multi_groups.items())
        }
    }
    Path(REPORT_PATH).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f'\n━━━━━━━━━━ 결과 ━━━━━━━━━━')
    print(f'총 학과 항목:                  {total_depts}')
    print(f'고유 정규화 키:                {len(groups)}')
    print(f'복수 멤버 그룹:                {len(multi_groups)}')
    print(f'단일 멤버 그룹(alias 없음):     {single_groups_n}')
    print(f'aliases 가 채워진 학과 항목:    {alias_filled}')
    print(f'\n→ {OUT_PATH}')
    print(f'→ 그룹 보고서: {REPORT_PATH}')

    # 6) 대표 그룹 출력
    print(f'\n━━━━━━━━━━ 대표 그룹 샘플 (크기 큰 순 Top 12) ━━━━━━━━━━')
    by_size = sorted(multi_groups.items(),
                      key=lambda x: -len(set(m[1] for m in x[1])))
    for key, members in by_size[:12]:
        unique_names = sorted(set(m[1] for m in members))
        print(f'\n  [정규화 키: "{key}"]  ({len(unique_names)}개 변형)')
        for n in unique_names[:8]:
            print(f'    · {n}')
        if len(unique_names) > 8:
            print(f'    ... 외 {len(unique_names)-8}개')


if __name__ == '__main__':
    main()
