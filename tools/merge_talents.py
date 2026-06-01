"""
대학 인재상 통합 스크립트 (사용자 실행용).

입력:
  - merged_university_db_v3_trimmed.json (현재 DB)
  - 171_university_talents.json (인재상 자료)

처리:
  1) 'OO대' ↔ 'OO대학교' 표기 자동 정규화 매칭
  2) 자연어 인재상 원문을 'talent_statement' 필드로 보존
  3) 인재상 원문에서 핵심 키워드 추출 → 'talent_keywords' 보강
     (기존 talent_keywords 가 비어있던 신규 141개 대학에 우선 적용)

출력:
  - merged_university_db_v3_trimmed.json (덮어쓰기)
  - 매칭 보고서 콘솔 출력

사용법:
  python3 merge_talents.py
"""
import json
import re
from pathlib import Path

# ─── 경로 (실행 환경에 맞게 수정) ─────────────────────────
DB_PATH       = 'merged_university_db_v3_trimmed.json'
TALENTS_PATH  = '171_university_talents.json'
OUT_PATH      = 'merged_university_db_v3_trimmed.json'  # 덮어쓰기
BACKUP_PATH   = 'merged_university_db_v3_trimmed.backup.json'


# ─── 대학명 정규화 (양쪽 표기를 공통 키로) ───────────────
def normalize_univ_name(s: str) -> str:
    if not s: return ''
    s = s.strip()
    # 약칭 → 풀어쓰기
    s = s.replace('한국외대', '한국외국어대')
    s = s.replace('이화여대', '이화여자대')
    # 괄호·캠퍼스 접미 표기 제거
    s = re.sub(r'\s*\([^)]*\)\s*', '', s)
    s = re.sub(r'\s*ERICA\s*$', '', s, flags=re.IGNORECASE)
    s = re.sub(r'\s*WISE\s*$', '', s, flags=re.IGNORECASE)
    s = re.sub(r'\s*글로벌\s*$', '', s)
    s = re.sub(r'\s*세종\s*$', '', s)
    # 어미 '대학교/대학/대' 반복 제거
    # (예: '신한대(동두천)대학교' → '신한대대학교' → '신한대' → '신한' 까지 도달)
    while True:
        new = re.sub(r'(대학교|대학|대)$', '', s)
        if new == s: break
        s = new
    return s.strip()


# ─── 인재상 자연어 → 키워드 추출 ─────────────────────────
def extract_keywords_from_statement(statement: str, max_n: int = 6) -> list:
    """
    인재상 자연어 문장에서 핵심 키워드를 추출.
    예: "정직한 기술전문인, 근면한 국제전문인(세계인), 창의적 문화문화인"
        → ['정직', '기술전문인', '근면', '국제전문인', '창의', '문화인']

    규칙
    - 쉼표/점/슬래시/괄호로 구절 분할
    - 각 구절에서:
      a) "~한 ~인/사람/리더/엔지니어" 패턴: 형용사 어간 + 명사 둘 다 추출
      b) "~성", "~력", "~심", "~의식", "~정신" 명사형 그대로
      c) 2자 이상 한자어 명사 추출
    - 중복 제거 후 상위 max_n 개
    """
    if not statement:
        return []
    # 분할: 쉼표/점/슬래시/괄호/세미콜론
    chunks = re.split(r'[,，·•/／()（）;；]', statement)
    keywords = []

    for chunk in chunks:
        c = chunk.strip()
        if not c or len(c) < 2:
            continue

        # 패턴 1: "OO한 ~인" → 'OO' 추출 (형용사 어간)
        m = re.match(r'(.+?)(한|적인|있는|적|운|로운)\s+(.+)', c)
        if m:
            adj_root = m.group(1).strip()
            if 2 <= len(adj_root) <= 4 and re.fullmatch(r'[가-힣]+', adj_root):
                keywords.append(adj_root)
            # 뒤의 명사도 추출 (5자 이내)
            tail = m.group(3).strip()
            tail = re.sub(r'[을를이가은는의에서에게]\s*$', '', tail)
            if 2 <= len(tail) <= 8 and re.fullmatch(r'[가-힣]+', tail):
                keywords.append(tail)
            continue

        # 패턴 2: 단일 단어 명사 (성/력/심/정신/의식 등)
        if re.search(r'(성|력|심|정신|의식|관|애|애심|능력)$', c) and len(c) <= 8:
            keywords.append(c)
            continue

        # 패턴 3: 일반 한자어 명사 (3-6자, 한글만)
        if 2 <= len(c) <= 8 and re.fullmatch(r'[가-힣]+', c):
            keywords.append(c)

    # 중복 제거 (순서 유지)
    seen = set(); out = []
    for k in keywords:
        if k not in seen:
            seen.add(k)
            out.append(k)
        if len(out) >= max_n:
            break
    return out


# ─── 메인 처리 ─────────────────────────────────────────
def main():
    # 1) 로드
    db = json.loads(Path(DB_PATH).read_text(encoding='utf-8'))
    talents = json.loads(Path(TALENTS_PATH).read_text(encoding='utf-8'))

    # 2) 백업
    Path(BACKUP_PATH).write_text(json.dumps(db, ensure_ascii=False, indent=2),
                                  encoding='utf-8')
    print(f'백업: {BACKUP_PATH}')

    # 3) 인재상 파일을 정규화된 키로 인덱싱
    talents_index = {}  # norm_key -> {'대학명': ..., '인재상': ...}
    for v in talents.values():
        norm_key = normalize_univ_name(v['대학명'])
        if norm_key:
            talents_index[norm_key] = v

    # 4) DB 대학 순회하며 매칭·통합
    matched = 0
    unmatched_db = []      # DB 에 있는데 인재상 자료 없음
    keywords_added = 0     # 키워드 신규 추가 대학 수
    statement_added = 0    # 자연어 원문 추가 대학 수

    for u in db['universities']:
        norm_key = normalize_univ_name(u['name'])
        match = talents_index.get(norm_key)
        if not match:
            unmatched_db.append(u['name'])
            continue
        matched += 1

        # 4-a) 자연어 원문 추가 (talent_statement)
        statement = match['인재상'].strip()
        u['talent_statement'] = statement
        statement_added += 1

        # 4-b) 키워드 추출 + 기존과 합치기
        extracted = extract_keywords_from_statement(statement, max_n=6)
        existing = u.get('talent_keywords') or []
        # 기존 키워드가 비어있었으면 새로 추출한 키워드로 채움
        # 비어있지 않았으면 추가만 (중복 제거)
        if not existing:
            u['talent_keywords'] = extracted
            keywords_added += 1
        else:
            # 합치되 중복 제거
            seen = set(existing)
            merged = list(existing)
            for k in extracted:
                if k not in seen:
                    merged.append(k); seen.add(k)
            u['talent_keywords'] = merged[:10]  # 최대 10개

    # 5) 인재상 자료에는 있는데 DB 에 없는 대학 (참고용)
    db_norm_set = {normalize_univ_name(u['name']) for u in db['universities']}
    unmatched_talents = [v['대학명'] for k, v in talents_index.items()
                          if k not in db_norm_set]

    # 6) 저장
    Path(OUT_PATH).write_text(json.dumps(db, ensure_ascii=False, indent=2),
                               encoding='utf-8')

    # 7) 보고
    print(f'\n━━━━━━━━━━ 통합 결과 ━━━━━━━━━━')
    print(f'DB 대학 수:             {len(db["universities"])}')
    print(f'인재상 매칭 성공:        {matched}')
    print(f'  ├ 자연어 원문 추가:    {statement_added}')
    print(f'  └ 키워드 신규 채움:    {keywords_added}')
    print(f'DB 에 있지만 인재상 자료 없음: {len(unmatched_db)}')
    print(f'인재상 자료에 있지만 DB 에 없음: {len(unmatched_talents)}')
    print(f'\n→ {OUT_PATH}')

    if unmatched_db:
        print(f'\n[참고] 인재상 자료 없는 DB 대학 (수동 보강 후보):')
        for n in unmatched_db[:30]:
            print(f'   - {n}')
        if len(unmatched_db) > 30:
            print(f'   ... 외 {len(unmatched_db)-30}개')

    if unmatched_talents:
        print(f'\n[참고] DB 에 없는 인재상 자료 (DB 확장 후보):')
        for n in unmatched_talents[:15]:
            print(f'   - {n}')

    # 8) 샘플 출력
    print(f'\n━━━━━━━━━━ 샘플 ━━━━━━━━━━')
    for name in ['서울대학교', '경북대학교', '광운대학교']:
        u = next((u for u in db['universities'] if u['name'] == name), None)
        if u:
            print(f'\n[{u["name"]}]')
            print(f'  talent_statement: {u.get("talent_statement", "—")}')
            print(f'  talent_keywords:  {u.get("talent_keywords")}')


if __name__ == '__main__':
    main()