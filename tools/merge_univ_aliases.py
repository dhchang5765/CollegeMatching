"""
대학 alias 통합 스크립트 (사용자 실행용).

처리
  1) DB 대학명을 alias 파일의 풀네임(표준명) 으로 자동 정규화
     예: '덕성여대학교' → '덕성여자대학교' (alias 파일의 '덕성여대' 역인덱스로 매핑)
  2) 매칭된 대학에 'aliases' 필드 추가/갱신

입력
  - merged_university_db_v3_trimmed.json
  - korean_university_aliases.json

출력
  - merged_university_db_v3_trimmed.json (덮어쓰기)
  - merged_university_db_v3_trimmed.backup_alias.json (백업)

사용
  python3 merge_univ_aliases.py
"""
import json
import re
from pathlib import Path

DB_PATH      = 'merged_university_db_v3_trimmed.json'
ALIAS_PATH   = 'korean_university_aliases.json'
OUT_PATH     = 'merged_university_db_v3_trimmed.json'
BACKUP_PATH  = 'merged_university_db_v3_trimmed.backup_alias.json'


def normalize_univ_name(s: str) -> str:
    """약칭·풀네임·캠퍼스 표기를 공통 정규화 키로 변환."""
    if not s: return ''
    s = s.strip()
    s = s.replace('한국외대', '한국외국어대')
    s = s.replace('이화여대', '이화여자대')
    # 괄호·캠퍼스 표기 제거
    s = re.sub(r'\s*\([^)]*\)\s*', '', s)
    s = re.sub(r'\s*ERICA\s*$', '', s, flags=re.IGNORECASE)
    s = re.sub(r'\s*WISE\s*$', '', s, flags=re.IGNORECASE)
    s = re.sub(r'\s*글로벌\s*$', '', s)
    s = re.sub(r'\s*세종\s*$', '', s)
    # 어미 반복 제거
    while True:
        new = re.sub(r'(대학교|대학|대)$', '', s)
        if new == s: break
        s = new
    return s.strip()


def main():
    db = json.loads(Path(DB_PATH).read_text(encoding='utf-8'))
    aliases_data = json.loads(Path(ALIAS_PATH).read_text(encoding='utf-8'))

    Path(BACKUP_PATH).write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'백업: {BACKUP_PATH}')

    # 1) 양방향 인덱스 구축
    #    - 풀네임 정규화 키 → 풀네임 + aliases
    #    - 모든 alias 정규화 키 → 풀네임
    index_by_norm = {}  # norm_key -> {'official', 'aliases'}
    for official, alias_list in aliases_data.items():
        norm = normalize_univ_name(official)
        if norm:
            index_by_norm[norm] = {'official': official, 'aliases': list(alias_list)}
        # alias 도 역인덱스에 등록
        for a in alias_list:
            n = normalize_univ_name(a)
            if n and n not in index_by_norm:
                index_by_norm[n] = {'official': official, 'aliases': list(alias_list)}

    # 2) DB 순회
    renamed = []      # 표준명으로 변경된 대학
    alias_added = 0   # aliases 필드 추가된 대학 수
    unmatched = []    # alias 자료 없는 대학

    for u in db['universities']:
        norm = normalize_univ_name(u['name'])
        match = index_by_norm.get(norm)
        if not match:
            unmatched.append(u['name'])
            continue
        # 표준명으로 변경 (DB의 '덕성여대학교' → alias의 '덕성여자대학교')
        if u['name'] != match['official']:
            renamed.append((u['name'], match['official']))
            u['name'] = match['official']
        # aliases 필드 추가
        u['aliases'] = list(match['aliases'])
        alias_added += 1

    Path(OUT_PATH).write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding='utf-8')

    # 보고
    print(f'\n━━━━━━━━━━ 결과 ━━━━━━━━━━')
    print(f'DB 대학 수:           {len(db["universities"])}')
    print(f'aliases 추가:         {alias_added}')
    print(f'표준명 변경:          {len(renamed)}')
    print(f'alias 자료 없음:       {len(unmatched)}')
    print(f'\n→ {OUT_PATH}')

    if renamed:
        print(f'\n[표준명 변경 내역 - 상위 20개]')
        for before, after in renamed[:20]:
            print(f'   {before:25s} → {after}')

    if unmatched:
        print(f'\n[alias 자료 없는 대학 - 수동 보강 후보]')
        for n in unmatched[:25]:
            print(f'   - {n}')


if __name__ == '__main__':
    main()
