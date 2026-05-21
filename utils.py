import json
import os
import re
from typing import Dict, List, Optional
from collections import Counter


def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def extract_text(node):
    if not node:
        return ""
    return clean_text(node.get_text(" ", strip=True))


def load_json_db(path: str) -> Dict:
    if not os.path.exists(path):
        raise FileNotFoundError(f"JSON DB 파일이 없습니다: {path}")
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)
    
def normalize_subject(v: Optional[float]) -> float:
    if v is None:
        return 50.0
    if v <= 9:
        return max(0.0, 100 - (v - 1) * 12.5)
    return max(0.0, min(100.0, v))

def strip_text(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def normalize_major_name(s: str) -> str:
    s = strip_text(s).lower()
    s = s.replace("학과", "").replace("학부", "").replace("전공", "")
    s = s.replace(" ", "").replace("·", "").replace("-", "")
    return s


# ─────────────────────────────────────────────────────────────────────
# 한국어 형태소 기반 키워드 추출 (Kiwi)
# ─────────────────────────────────────────────────────────────────────
# 진단 리포트 UI 상용구·의미 없는 일반어를 제거하기 위한 도메인 불용어
DOMAIN_STOPWORDS = {
    # 리포트 UI / 상품 고유어
    "리포트", "통합", "진단", "응답", "문항", "슬라이드", "보고서",
    "MOS", "EDULAB", "VAMOS", "CONSULTANT", "CONSULTANTS", "DIAGNOSIS",
    "CONFIDENTIAL", "EDU", "LAB", "TIER", "BAR", "SWOT", "RADAR",
    "ALL", "RIGHTS", "RESERVED",
    # 진단 구조어 / 학습 환경 상용구
    "학생", "학년", "학교", "결과", "시간", "점수", "단계", "트랙",
    "학원", "직업", "선행", "환경", "자율형", "자기소개서",
    "일반고", "고교", "고등학교", "중학교", "진학", "입시",
    "수성구", "수성", "범어동", "범어",
    # 전형 일반 용어 (계열 변별력 낮음)
    "학종", "수시", "정시", "교과", "전형", "면접", "서류",
    "내신", "등급", "평균", "객관", "지표", "성적", "모의고사",
    # 모든 리포트에 공통적으로 등장 → 학생 변별력 없음
    # 사용자 지적: 과목, 영역, 결정, 평가, 시사, 효율, 학과, 확인, 진로
    "과목", "영역", "결정", "평가", "시사", "효율", "학과", "확인",
    "진로", "선택", "기준", "방법", "이유", "내용", "정보",
    "활동", "지원", "준비", "관리", "운영", "참여",
    "수업", "수행", "수행평가", "탐구", "특기",
    # 과목명: 별도 신호(strong/weak_subjects)로 이미 표시되므로 중복 제거
    "국어", "영어", "수학", "과학", "사회", "한국사",
    # AI/SW 같은 영어 약어는 career_cluster로 잡히므로 키워드에서 제외
    "AI", "SW", "IT", "STEM",
    # 너무 일반적인 추상명사
    "강점", "약점", "필요", "역량", "성향", "패턴", "분석",
    "유형", "정도", "수준", "방식", "방안", "방향",
    "본인", "자기", "자신", "현재", "이번", "최근",
    "전국", "지역", "현실", "일관", "최종", "기본",
    "확보", "보완", "응답자", "표본", "응답수",
    "변화", "차이", "비교", "구분", "조합", "주제", "사항", "부분",
    # 컨설팅 산업 어휘 (본 도구가 컨설팅 리포트이므로 모든 학생 보고서에 공통 등장)
    "분석가", "분석가형", "전략가", "기획가", "기획자형",
    "메타", "메타인지", "코칭", "컨설팅", "컨설턴트", "트레이닝",
    "코치", "어드바이저", "솔루션", "프로그램", "프로세스",
    "프레임", "프레임워크", "전략", "처방", "처방전",
    "정반대", "반대", "동시", "동시에", "별도", "각각",
    "활용", "조정", "개선", "추진", "수립", "정립",
    # 보고서 내부 라벨/약어 (모든 학생 보고서에 공통 등장)
    "자주도", "자기주도성", "주체성", "주도성", "정합", "재정합",
    # 외래어 일반 명사 (보고서에 자주 등장하지만 변별력 낮음)
    "데이터", "시스템", "디지털", "포인트", "모드", "스타일",
    "사이클", "패턴", "타입", "케이스",
    # 부사·기타 추상명사 (보고서 작성 시 흔히 쓰이지만 학생 특성과 무관)
    "스스로", "자체", "인지도", "회로", "전반",
    "관련", "전체", "일부", "기존", "본격",
    # 접속사·부사 (보고서에서 모든 학생에 공통 등장)
    "그러나", "그리고", "또한", "따라서", "한편", "다만", "하지만",
    "특히", "오히려", "역시", "결국", "이미", "어떻게", "어디서",
    # 너무 일반적인 입시·학습 어휘 (학생 변별력 거의 없음)
    "이과", "문과", "문이과", "이공계", "인문계",
    "선택과목", "선택", "선행", "등급대", "성적대", "교과목",
    "학습효율", "공부법", "학습법",
    # 보고서에 흔히 등장하는 추상 명사 (조사 결합형도 자동 확장됨)
    "자원", "구조", "응답", "차원", "관점", "시각", "발생", "지점",
    "포인트", "구간", "범위", "조건", "사례", "경우", "상황",
    # 일반 학습 어휘 (계열 무관)
    "공부", "학습", "교과", "정리", "암기", "이해",
    "탐색", "보강", "도전", "유지", "확보",
    # 단위어
    "이상", "이하", "미만", "초과", "내외", "정도",
}

# 변별력 있는 학생 특성 키워드의 후보 단서
# (2자 추상명사 제외, 3자 이상 또는 구체 명사만 유지하는 보조 휴리스틱용)
_GENERIC_2CHAR_PATTERN = {  # 2자인데도 변별력 있는 예외 (살려둘 단어)
    "의대", "의예", "약대", "치대", "한의", "수의",
    "공대", "법대", "사대", "상대",
    "논술", "면접", "수상", "동아", "봉사",
}

# 진단 리포트에서 학생 특성으로 유의미한 키워드의 최소 길이
_MIN_KEYWORD_LEN = 2

_kiwi_instance = None

# 한국어 조사 패턴 (정규식 fallback 에서 명사+조사 결합을 분리)
# 2자 조사 먼저 확인 후 1자 조사 (긴 것이 먼저)
_KO_PARTICLES_2 = (
    "에서", "에게", "에는", "에도", "으로", "처럼", "마저", "조차",
    "까지", "부터", "보다", "이라", "이고", "이며", "라는", "라고",
)
_KO_PARTICLES_1 = "은는이가을를도만의에로와과나"

def _strip_particles_and_endings(token: str) -> str:
    """
    토큰 끝의 2자 조사를 분리해 어간(명사)을 반환.
    1자 조사 분리는 명사 끝자(자기주도의 '도', 자료·구조 등)와 충돌 위험이 커
    비활성화. 1자 조사 결합형은 _expand_stopwords_with_particles 가 처리한다.
    """
    if not token or len(token) < 3:
        return token
    for p in _KO_PARTICLES_2:
        if token.endswith(p) and len(token) - len(p) >= 2:
            return token[:-len(p)]
    return token


def _expand_stopwords_with_particles(base: set) -> set:
    """stopword 에 1자/2자 조사 결합형을 추가해 정규식 fallback 누락을 보완.
    한글뿐 아니라 외래어 stopword(예: 데이터·시스템)도 함께 확장한다."""
    expanded = set(base)
    one_char = "은는이가을를도만의에로와과"
    two_char = ["에서", "에게", "으로", "처럼", "까지", "부터", "보다"]
    for w in list(base):
        if not w or len(w) < 2:
            continue
        # 알파벳 단독은 제외(AI/SW 등은 조사 결합 가능성 낮음)
        if w.isascii():
            continue
        for p in one_char:
            expanded.add(w + p)
        for p in two_char:
            expanded.add(w + p)
    return expanded


# 활용 어미·접미 패턴 (한자어형 형용사 + 동사 활용형)
_INFLECTION_ENDINGS = (
    # 동사 활용 - "결합되어, 나타난다, 보여준다, 갖춰진" 류
    "되어", "하여", "한다", "했다", "된다", "되다", "한다는",
    "있다", "있는", "있어", "없다", "없는",
    "주는", "주며", "주고", "준다",
    "한", "된", "받은", "지는", "지고", "지며",
    "이고", "이다", "이며", "라고", "라는",
    # 형용사형 한자어
    "적인", "적이", "적으로", "적이다",
    # 어미 단독 / 동사 미정형
    "거나", "지만", "면서", "도록", "이라는",
    "할", "볼", "들", "올", "갈", "쓸", "둘",
    "함", "됨", "옴", "감",
    # 부사 어미 ("일관되게·명확히·정확히")
    "되게", "있게", "롭게", "스럽게",
    # 명사형 + 조사 ("있음을·없음은·됨이")
    "음을", "음은", "음이", "음에",
    # 동사 활용 ("드러내며·드러내고·없으면·아는데·하는데")
    "내며", "내고", "내어", "으면", "려고", "려는", "는데",
)


def _looks_like_inflection(token: str) -> bool:
    """동사·형용사 활용형으로 판단되면 True."""
    if not token:
        return False
    if len(token) >= 3 and token.endswith("적"):
        return True
    for end in _INFLECTION_ENDINGS:
        if token.endswith(end) and len(token) > len(end):
            return True
    if len(token) >= 3 and token.endswith("화"):
        return True
    if len(token) >= 3 and token.endswith("다"):
        return True
    if len(token) >= 3 and token.endswith("는"):
        return True
    # 2자+ "히"로 끝나면 부사 활용형 ("명확히·정확히·확실히")
    if len(token) >= 2 and token.endswith("히"):
        return True
    return False


def _get_kiwi():
    """Kiwi 형태소 분석기를 lazy-load. 미설치 시 None 반환."""
    global _kiwi_instance
    if _kiwi_instance is not None:
        return _kiwi_instance
    try:
        from kiwipiepy import Kiwi
        _kiwi_instance = Kiwi()
        return _kiwi_instance
    except Exception:
        return None


def extract_keywords_kiwi(text: str, top_n: int = 20) -> List[str]:
    """
    Kiwi 형태소 분석기로 명사만 추출 + 불용어 제거 + 빈도 정렬.
    Kiwi 미설치 시 정규식 fallback 사용.
    """
    if not text:
        return []

    kiwi = _get_kiwi()

    if kiwi is None:
        # Fallback: 한글 2자 이상 토큰 + 조사 분리 + 활용어미 제거 + 불용어 필터
        tokens = re.findall(r"[가-힣]{2,15}", text)
        filtered = []
        for t in tokens:
            cleaned = _strip_particles_and_endings(t)
            if not cleaned:
                continue
            if cleaned in DOMAIN_STOPWORDS:
                continue
            if len(cleaned) < _MIN_KEYWORD_LEN:
                continue
            # 2자 단순 한글은 화이트리스트만 통과 (변별력 낮은 추상명사 제거)
            if len(cleaned) == 2 and cleaned not in _GENERIC_2CHAR_PATTERN:
                continue
            # 활용형으로 끝나는 토큰(필요한·결합되어·나타난다·결정적·분석적) 제거
            if _looks_like_inflection(cleaned):
                continue
            filtered.append(cleaned)
        counter = Counter(filtered)
        return [w for w, _ in counter.most_common(top_n)]

    # Kiwi 분석: 일반명사(NNG), 고유명사(NNP)만 추출
    KEEP_POS = {"NNG", "NNP", "SL"}  # SL = 외국어 (AI, MMI 등)
    tokens = []
    try:
        result = kiwi.analyze(text, top_n=1)
        for sent in result:
            for morph in sent[0]:
                form, pos = morph.form, morph.tag
                if pos not in KEEP_POS:
                    continue
                if len(form) < _MIN_KEYWORD_LEN:
                    continue
                if form in DOMAIN_STOPWORDS or form.upper() in DOMAIN_STOPWORDS:
                    continue
                # 숫자만으로 구성된 토큰 제외
                if form.isdigit():
                    continue
                # 2자 일반명사(NNG)는 화이트리스트에 있을 때만 통과
                # (의대·논술·수상 등 변별력 있는 2자는 살리되, 일반 추상명사는 제거)
                if pos == "NNG" and len(form) == 2 and form not in _GENERIC_2CHAR_PATTERN:
                    continue
                tokens.append(form)
    except Exception:
        # Kiwi 분석 실패 시 정규식 fallback
        return extract_keywords_kiwi.__wrapped__(text, top_n) if hasattr(extract_keywords_kiwi, "__wrapped__") else []

    counter = Counter(tokens)
    return [w for w, _ in counter.most_common(top_n)]

# ── 모듈 로드 시 stopword 자동 확장 ──────────────────────────────
# DOMAIN_STOPWORDS 의 한국어 명사들에 1자/2자 조사 결합형을 추가해
# 정규식 fallback 에서도 '응답은·본인은·자원이' 같은 결합 토큰이 자동 제거되도록 한다.
DOMAIN_STOPWORDS = _expand_stopwords_with_particles(DOMAIN_STOPWORDS)
