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
    "공대", "법대", "사대", "상대", "문과", "이과",
    "논술", "면접", "수상", "동아", "봉사",
}

# 진단 리포트에서 학생 특성으로 유의미한 키워드의 최소 길이
_MIN_KEYWORD_LEN = 2

_kiwi_instance = None

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
        # Fallback: 한글 2자 이상 토큰 + 불용어 필터
        tokens = re.findall(r"[가-힣]{2,15}", text)
        # 조사/어미가 붙은 토큰을 제거 (정규식 fallback 보정)
        suffix_patterns = (
            "으로", "이다", "이며", "한다", "했다", "된다", "되다",
            "이고", "라는", "라고", "이라", "에서", "에게", "까지",
            "음을", "응을", "있게", "되게", "이라는", "한테", "에는",
            "보다", "처럼", "마저", "조차", "거나", "이지만",
        )
        filtered = []
        for t in tokens:
            if t in DOMAIN_STOPWORDS:
                continue
            if any(t.endswith(s) for s in suffix_patterns) and len(t) > 2:
                continue
            if t in suffix_patterns:
                continue
            if len(t) < _MIN_KEYWORD_LEN:
                continue
            # 2자 단순 한글은 화이트리스트만 통과 (변별력 낮은 추상명사 제거)
            if len(t) == 2 and t not in _GENERIC_2CHAR_PATTERN:
                continue
            filtered.append(t)
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