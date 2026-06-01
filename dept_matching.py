"""
dept_matching.py
─────────────────────────────────────────────────────────────────────
신규 기능 — 사용자가 직접 입력한 희망 학과를, DB 의 '실제 학과명'과
의미 유사도로 매칭한다.

배경
- 기존 파이프라인은 HTML/JSON 에서 학과를 추출하지만, 키워드 매칭에
  실패하면 추천이 비거나 무관한 학과가 잡힐 수 있다(요약본의 알려진 한계).
- 사용자가 적은 학과명은 DB 표기와 다를 수 있다(예: "컴공" → "컴퓨터공학과",
  "AI학과" → "인공지능학과", "신방과" → "미디어커뮤니케이션학과").

해결
- DB 의 고유 학과명 어휘를 만들고, embeddings 모듈(sentence-transformers
  → Gemini → 키워드 fallback)로 사용자 입력과의 유사도를 계산해 후보를 반환.
- 임베딩 비용 절감을 위해 먼저 문자 n-gram 기반 어휘 prefilter 로 후보를
  좁힌 뒤, 그 후보들만 임베딩으로 정밀 재순위한다.
- 추출 학과와 사용자 학과가 서로 유사하지 않으면 '충돌'로 판정해 경고.

설계 원칙
- 임베딩 미가용 환경에서도 lexical fallback 으로 항상 동작.
- 결과는 점수와 함께 반환해 호출부(app.py)가 임계값으로 판단.
"""
from __future__ import annotations
import re
from typing import Dict, List, Optional, Tuple

# 충돌 판정 임계값: 사용자 학과 ↔ 추출 학과 간 최대 유사도가 이 값 미만이면 충돌
CONFLICT_SIM_THRESHOLD = 0.45


def _norm(s: str) -> str:
    """학과명 정규화: 공백·기호·접미어 제거, 소문자화."""
    s = (s or "").lower().strip()
    s = re.sub(r"[\s·\-_/()]", "", s)
    for suf in ("학과", "학부", "전공", "계열"):
        s = s.replace(suf, "")
    return s


def _char_ngrams(s: str, n: int = 2) -> set:
    s = _norm(s)
    if len(s) < n:
        return {s} if s else set()
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def _lexical_sim(a: str, b: str) -> float:
    """문자 bigram Jaccard + 포함 보너스 (0~1)."""
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ga, gb = _char_ngrams(na), _char_ngrams(nb)
    inter = len(ga & gb)
    union = len(ga | gb) or 1
    jac = inter / union
    if na in nb or nb in na:
        jac = max(jac, 0.7)
    return jac


def collect_department_vocab(db: Dict) -> List[Dict]:
    """
    DB 의 고유 학과 어휘 수집.
    반환: [{ "name": 표준명, "category": 계열, "aliases": [...] }, ...]
    동일 표준명은 1회만 (학과명 → 대표 카테고리).
    """
    seen: Dict[str, Dict] = {}
    for u in db.get("universities", []):
        for d in u.get("departments", []):
            name = (d.get("name") or "").strip()
            if not name:
                continue
            if name not in seen:
                seen[name] = {
                    "name": name,
                    "category": d.get("category", ""),
                    "aliases": list(d.get("aliases") or []),
                }
            else:
                for a in (d.get("aliases") or []):
                    if a not in seen[name]["aliases"]:
                        seen[name]["aliases"].append(a)
    return list(seen.values())


def resolve_user_department(user_text: str, db: Dict,
                            top_k: int = 5,
                            prefilter_n: int = 40) -> List[Dict]:
    """
    사용자 입력 학과 → DB 실제 학과명 후보(점수순).
    반환: [{ "name", "category", "score"(0~1), "backend" }, ...]
    """
    user_text = (user_text or "").strip()
    if not user_text:
        return []

    vocab = collect_department_vocab(db)
    if not vocab:
        return []

    # 1) lexical prefilter — 모든 학과명/별칭과의 문자 유사도 최댓값
    scored_lex: List[Tuple[float, Dict]] = []
    for v in vocab:
        cand_strs = [v["name"]] + v["aliases"]
        lex = max(_lexical_sim(user_text, c) for c in cand_strs)
        scored_lex.append((lex, v))
    scored_lex.sort(key=lambda x: -x[0])
    prefiltered = [v for _, v in scored_lex[:prefilter_n]]

    # 2) 임베딩 정밀 재순위 (가용 시). embeddings 는 3단 fallback 내장.
    backend = "lexical"
    try:
        from embeddings import embed_texts, cosine
        names = [v["name"] for v in prefiltered]
        vecs = embed_texts([user_text] + names)
        if vecs and len(vecs) == len(names) + 1:
            uvec = vecs[0]
            ranked: List[Tuple[float, Dict]] = []
            for v, nv in zip(prefiltered, vecs[1:]):
                sim = cosine(uvec, nv)  # 정규화 벡터 → 0~1 근처
                ranked.append((sim, v))
            ranked.sort(key=lambda x: -x[0])
            backend = "embedding"
            return [{"name": v["name"], "category": v["category"],
                     "score": round(max(0.0, min(1.0, s)), 3), "backend": backend}
                    for s, v in ranked[:top_k]]
    except Exception:
        pass

    # 3) 임베딩 실패 → lexical 결과 그대로
    return [{"name": v["name"], "category": v["category"],
             "score": round(s, 3), "backend": backend}
            for s, v in scored_lex[:top_k]]


def assess_department_conflict(user_resolved_name: str,
                               extracted_departments: List[str]) -> Tuple[bool, float, str]:
    """
    사용자가 지정(해석)한 학과와, HTML/JSON 에서 추출된 학과 목록의 충돌 여부.
    반환: (is_conflict, best_similarity, 설명문)
    """
    if not extracted_departments:
        return (False, 0.0, "추출된 학과가 없어 사용자 지정 학과를 그대로 사용합니다.")
    sims = [(_lexical_sim(user_resolved_name, d), d) for d in extracted_departments]
    sims.sort(key=lambda x: -x[0])
    best_sim, best_dep = sims[0]
    if best_sim < CONFLICT_SIM_THRESHOLD:
        msg = (f"사용자 지정 학과 '{user_resolved_name}'가 추출된 학과"
               f"({', '.join(extracted_departments[:3])})와 유사도가 낮습니다"
               f"(최대 {best_sim:.2f}). 사용자 지정 학과를 우선합니다.")
        return (True, best_sim, msg)
    return (False, best_sim,
            f"사용자 지정 학과가 추출 학과 '{best_dep}'와 일치도가 높습니다(유사도 {best_sim:.2f}).")


def merge_user_department(user_resolved_name: str,
                          extracted_departments: List[str],
                          max_n: int = 3) -> List[str]:
    """
    사용자 지정 학과를 1순위로 올리고 추출 학과를 뒤에 병합(중복 제거).
    요구사항: 충돌 시에도 사용자가 작성한 학과를 우선시한다.
    """
    out: List[str] = []
    if user_resolved_name:
        out.append(user_resolved_name)
    for d in extracted_departments:
        if d and d not in out:
            out.append(d)
    return out[:max_n]
