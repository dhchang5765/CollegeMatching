"""
embeddings.py
─────────────────────────────────────────────────────────────────────
워드/문장 임베딩 기반 의미 유사도. 학생 신호 ↔ 대학 인재상 매칭에 사용.

3단 fallback (앞에서부터 시도):
  1) sentence-transformers + 한국어 모델 (로컬, 무료)
  2) Gemini embedding API (API 키 필요, 네트워크)
  3) 키워드 부분 일치 (의미 X, 항상 동작)

설계 원칙
- 대학 인재상 임베딩은 한 번만 계산하고 캐시한다(대학 수×벡터차원).
- 동일 입력 → 동일 출력(모델·시드 고정).
- 임베딩 모델 미사용 시에도 추천 시스템 전체가 정상 동작해야 한다.
"""
from __future__ import annotations
import os
import math
from typing import Dict, List, Optional, Tuple

# 모델 핸들(전역 캐시)
_st_model = None       # sentence-transformers 모델
_st_load_attempted = False
_gemini_client = None
_gemini_load_attempted = False

# 대학별 임베딩 캐시: { univ_name: vector }
_univ_embedding_cache: Dict[str, List[float]] = {}

# 사용된 백엔드 (UI 표시용)
_backend_used: str = "keyword"


def get_backend() -> str:
    """현재 사용 중인 임베딩 백엔드 식별자."""
    return _backend_used


def _try_load_sentence_transformers():
    """sentence-transformers + 한국어 모델 로드 시도. 성공 시 모델 반환."""
    global _st_model, _st_load_attempted, _backend_used
    if _st_load_attempted:
        return _st_model
    _st_load_attempted = True
    try:
        from sentence_transformers import SentenceTransformer
        # 한국어 + 다국어 지원, 비교적 가벼움(~120MB)
        # paraphrase-multilingual-MiniLM-L12-v2 는 한국어 포함 50개 언어 지원
        model_name = os.environ.get(
            "EMBEDDING_MODEL",
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        )
        _st_model = SentenceTransformer(model_name)
        _backend_used = f"sentence-transformers:{model_name.split('/')[-1]}"
        return _st_model
    except Exception:
        _st_model = None
        return None


def _try_load_gemini_embed():
    """Gemini embedding API 클라이언트 준비."""
    global _gemini_client, _gemini_load_attempted, _backend_used
    if _gemini_load_attempted:
        return _gemini_client
    _gemini_load_attempted = True
    try:
        from google import genai
        from password import get_secret_value
        api_key = get_secret_value("GEMINI_API_KEY")
        if not api_key:
            return None
        _gemini_client = genai.Client(api_key=api_key)
        if _backend_used == "keyword":  # st 가 없을 때만
            _backend_used = "gemini-embedding"
        return _gemini_client
    except Exception:
        _gemini_client = None
        return None


def embed_texts(texts: List[str]) -> Optional[List[List[float]]]:
    """
    텍스트 목록을 벡터로 임베딩. 실패 시 None.
    백엔드 자동 선택. 첫 호출 시 모델 로드.
    """
    if not texts:
        return []

    # 1) sentence-transformers 우선
    model = _try_load_sentence_transformers()
    if model is not None:
        try:
            arr = model.encode(texts, show_progress_bar=False,
                               convert_to_numpy=True, normalize_embeddings=True)
            return [list(map(float, v)) for v in arr]
        except Exception:
            pass

    # 2) Gemini embedding fallback
    client = _try_load_gemini_embed()
    if client is not None:
        try:
            vectors = []
            for t in texts:
                res = client.models.embed_content(
                    model="text-embedding-004",
                    contents=t,
                )
                emb = res.embeddings[0].values if hasattr(res, "embeddings") else res["embedding"]["values"]
                # 단위 벡터화
                n = math.sqrt(sum(v * v for v in emb)) or 1.0
                vectors.append([v / n for v in emb])
            return vectors
        except Exception:
            return None
    return None


def cosine(a: List[float], b: List[float]) -> float:
    """두 벡터의 코사인 유사도 (-1..1). 사전 정규화돼 있다면 내적과 동일."""
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


def get_university_embedding(univ_name: str, talent_keywords: List[str]) -> Optional[List[float]]:
    """대학 인재상 키워드를 단일 벡터로 임베딩하여 캐시."""
    if not talent_keywords:
        return None
    if univ_name in _univ_embedding_cache:
        return _univ_embedding_cache[univ_name]
    text = " · ".join(talent_keywords)
    vecs = embed_texts([text])
    if not vecs:
        return None
    _univ_embedding_cache[univ_name] = vecs[0]
    return vecs[0]


def build_student_profile_text(signals: Dict, answer_result: Optional[Dict] = None) -> str:
    """
    학생 신호를 임베딩용 단일 텍스트로 합성.
    리포트 raw_text 가 아닌, '추출된 의미 신호'만 사용해
    UI 상용구 노이즈를 배제한다.
    """
    parts: List[str] = []
    # 추출된 핵심 키워드 (이미 stopword 필터링됨)
    parts += list(signals.get("top_keywords", []) or [])[:15]
    # 진로 클러스터·강점 과목
    if answer_result:
        rs = answer_result.get("rule_signals", {}) or {}
        parts += list(rs.get("career_clusters", []) or [])
        parts += list(rs.get("strong_subjects", []) or [])
        parts += list(rs.get("career_cluster_hints", []) or [])[:5]
    # 신호 플래그 → 자연어 단서
    if signals.get("essay_strength"): parts.append("논술 글쓰기 강점")
    if signals.get("self_directed"): parts.append("자기주도성 탐구")
    if signals.get("extracurricular_strong"): parts.append("비교과 활동 풍부")
    if signals.get("humanities_media_fit"): parts.append("인문 미디어 기획")
    if signals.get("sci_track_fit"): parts.append("이공계 분석")
    if signals.get("med_track_fit"): parts.append("의료 생명 임상")
    return " · ".join(p for p in parts if p) or "탐구 학습"


def compute_talent_similarities_normalized(student_text: str,
                                            universities: List[Dict]) -> Dict[str, float]:
    """
    학생 1명에 대한 모든 대학의 인재상 유사도를 한 번에 계산하고
    percentile 기반 상대 점수(30~95)로 변환한다.

    절대 코사인 값(0.05~0.25 범위)을 100점 스케일에 그대로 매핑하면
    모든 대학이 낮은 점수만 받는 문제가 있다. 대신 '이 학생에게 어느
    대학이 상대적으로 더 적합한가'를 후보 대학 내 순위로 환산한다.

    반환: { univ_name: score(30~95) }
    """
    if not universities or not student_text:
        return {}
    s_emb_list = embed_texts([student_text])
    if not s_emb_list:
        return {}
    s_emb = s_emb_list[0]

    sims: List[tuple] = []
    for u in universities:
        name = u.get("name", "")
        kws = u.get("talent_keywords", []) or []
        if not kws:
            sims.append((name, 0.0))
            continue
        u_emb = get_university_embedding(name, kws)
        if u_emb is None:
            sims.append((name, 0.0))
            continue
        sims.append((name, cosine(s_emb, u_emb)))

    if not sims:
        return {}
    sorted_sims = sorted(sims, key=lambda x: x[1])
    n = len(sorted_sims)
    if n == 1:
        return {sorted_sims[0][0]: 70.0}
    scores: Dict[str, float] = {}
    for rank, (name, _) in enumerate(sorted_sims):
        percentile = rank / (n - 1)  # 0.0 (최저) ~ 1.0 (최고)
        scores[name] = round(30.0 + percentile * 65.0, 2)
    return scores


def talent_similarity(student_text: str, univ_name: str,
                       talent_keywords: List[str]) -> Tuple[float, str]:
    """
    학생 텍스트 ↔ 대학 인재상 의미 유사도. (점수 0~100, 사용 방식 라벨)
    임베딩 가능 시: 코사인 유사도 × 100 (음수는 0 클램프)
    임베딩 불가 시: 키워드 부분 일치 비율
    """
    global _backend_used

    if not talent_keywords:
        return (0.0, "no_keywords")

    u_emb = get_university_embedding(univ_name, talent_keywords)
    if u_emb is not None:
        s_emb = embed_texts([student_text])
        if s_emb:
            sim = cosine(s_emb[0], u_emb)
            # 코사인 일반적 분포는 -0.1~0.5 정도. 가시성 위해 선형 매핑
            # 0.0(낮음) → 30점, 0.5(높음) → 95점
            score = max(0.0, min(100.0, 30.0 + sim * 130.0))
            return (round(score, 2), f"embedding:{_backend_used}")

    # Fallback: 키워드 부분 일치
    _backend_used = "keyword"
    student_low = student_text.lower()
    hits = sum(1 for kw in talent_keywords if kw and kw.lower() in student_low)
    score = min(100.0, hits / max(len(talent_keywords), 1) * 100.0 * 1.4)
    return (round(score, 2), "keyword")
