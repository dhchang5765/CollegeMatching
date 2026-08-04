# CollegeMatching

**VAMOS EDULAB MOS Application** — 학생 진단 자료(MOS 리포트 HTML + 답변 JSON)를 입력받아, 계열·학과 적합도를 산출하고 전국 179개 대학 입시 DB와 대조해 **대학·학과·전형**을 추천하는 Streamlit 애플리케이션.

---

## 1. 설계 목표

| 목표 | 구현 방식 |
|---|---|
| **재현성** | 최종 판정은 순수 결정론 함수(`decisionEngine.decide`). 동일 입력 → 항상 동일 출력. LLM은 판정에 관여하지 않는다. |
| **설명가능성** | 모든 점수 변동을 `audit_trail`에 기록. 각 신호는 근거 문항(evidence idx)을 동반하며, 근거 없는 신호는 생성하지 않는다. |
| **Graceful degradation** | Gemini API 키가 없거나 `sentence-transformers`가 없어도 규칙·lexical fallback으로 전체 파이프라인이 동작한다. |
| **버전 불변성** | 질문지가 200문항/162문항 등 버전별로 달라도 위치(idx)가 아닌 **시맨틱 슬롯**으로 정규화해 흡수한다. |
| **사실/추정 구분** | DB의 LLM 생성 인재상은 `talent_source="llm-generated-unverified"`로 태깅되어 검증 전까지 사실로 취급하지 않는다. |

---

## 2. 전체 아키텍처 (위계구조)

```
                        ┌──────────────────────────┐
                        │        app.py            │  L0 · 오케스트레이터
                        │  (UI 흐름 + 모듈 호출)    │
                        └───────────┬──────────────┘
            ┌───────────────┬───────┴────────┬────────────────┐
            ▼               ▼                ▼                ▼
     [입력 해석 계층]  [판정 계층]     [추천 계층]      [출력 계층]
            │               │                │                │
   extractHTML.py    answer_pipeline.py  signals.py      renderUI.py
   answer_schema.py   ├ extractAnswers   recommender.py  report_builder.py
   utils.py           ├ answerLLM        admission_tracks.py
                      ├ decisionEngine   dept_matching.py
                      ├ mlJudge          embeddings.py
                      └ validationLoop   student_profile.py
                                                │
                                    ┌───────────┴───────────┐
                                    │  university_db.json   │  데이터 계층
                                    │  constants.py         │
                                    └───────────────────────┘
```

### 2.1 3층 판정 파이프라인 (`answer_pipeline.run_answer_pipeline`)

이 프로젝트의 핵심 위계. `app.py`는 이 함수 **하나만** 호출한다.

```
Layer 1  신호 추출
  ├─ extractAnswers.extract_rule_signals()   규칙 기반, 결정론적, evidence 필수
  └─ answerLLM.structure_with_llm()          선택적 보강. temperature=0, enum 고정,
                                             enum 이탈·근거 없는 항목은 코드에서 폐기.
                                             키 없으면 None → 규칙 단독 동작
        ▼
Layer 2  최종 판정  ★ 유일한 판정자
  └─ decisionEngine.decide()                 순수 함수. LLM 호출 없음.
     신호 출처별 신뢰계수로만 가중:
       consensus(규칙·LLM 합의) 1.00 / rule 0.85 / llm 0.55 / html 0.40
     충돌(예: 의약학 지망 + 수학 약점)은 명시적 규칙으로 결정론 해소
        ▼
Layer 3  검증 · 자문
  ├─ validationLoop.record_prediction()      예측 스냅샷 누적 → 실제 합격결과와 대조
  └─ mlJudge.cross_check()                   현재는 '판정자'가 아닌 '교차검증 자문'.
                                             레이블 60건(MIN_LABELS) 미만에서는
                                             prototype distance만 계산해 low-confidence
                                             플래그만 표시 (피처 ~200 / 표본 <5 →
                                             지도학습은 통계적으로 과적합)
```

사람(입학사정관·컨설턴트)은 **Layer 3에만 개입**한다. 개별 학생 판정에는 개입하지 않는다.

### 2.2 신호 병합 규칙 (`app.py`)

HTML과 답변 JSON을 **모두** 업로드했을 때만 분석이 1회 실행된다 (AI API 중복 호출 방지).

```
merged_score(cat) = html_score(cat) × 0.5  +  decision_score(cat) × 3.0
                    └ HTML_DAMPENING          └ ANSWER_WEIGHT
```
답변 JSON은 학생의 1인칭 직접 응답, HTML은 2차 재가공물이므로 답변을 6배 강하게 신뢰한다.

### 2.3 대학 추천 4축 스코어 (`recommender.py`)

| 축 | 배점 | 근거 모듈 |
|---|---|---|
| 합격선 적합도 | 35 | `admission_band_score` — DB `min_grade_band` / `cutoff_p50·p70·p90` |
| 진로 적합도 | 25 | `career_match_score` — 학과 카테고리 ↔ 계열 점수 |
| 전형 적합도 | 25 | `track_match_score` — `admission_tracks.recommend_tracks` 결과와 대조 |
| 인재상 유사도 | 15 | `embeddings.talent_similarity` — 학생 프로파일 ↔ 대학 `talent_keywords` |

추가로 목표대학 보너스(`target_bonus`)가 붙고, 결과는 **안정·적정·상향·도전** 지원군으로 분류되어 `_distribute_by_support_level`로 균형 분배된다.

### 2.4 임베딩 3단 fallback (`embeddings.py`)

```
1) sentence-transformers 한국어 모델  (로컬, 무료)
      ↓ 실패
2) Gemini embedding API              (GEMINI_API_KEY 필요)
      ↓ 실패
3) 키워드 부분 일치                   (의미 X, 항상 동작)
```
대학 인재상 벡터는 1회 계산 후 전역 캐시(`_univ_embedding_cache`)된다. `dept_matching.py`는 비용 절감을 위해 문자 2-gram lexical prefilter로 후보를 좁힌 뒤 그 후보만 임베딩으로 재순위한다.

---

## 3. 파일별 역할

### 3.1 진입점 · 공통

| 파일 | 역할 |
|---|---|
| `app.py` | 메인 오케스트레이터. 화면 흐름과 모듈 호출만 담당(v9 리팩터링에서 1,778행 단일 파일을 분리). |
| `constants.py` | `GEMINI_MODEL`, `JSON_DB_PATH`, `CATEGORY_KEYWORDS`(계열별 키워드 사전), `DEPT_ALIAS` 등 전역 상수. |
| `utils.py` | 텍스트 정제, JSON DB 로더, 학과명 정규화, Kiwi 형태소 기반 키워드 추출(`extract_keywords_kiwi`). |
| `password.py` | PBKDF2-SHA256(240,000 iters) 로그인 게이트, `.env`/`st.secrets` 통합 시크릿 조회. UTF-8 BOM 자동 제거 포함. |

### 3.2 입력 해석

| 파일 | 역할 |
|---|---|
| `extractHTML.py` | BeautifulSoup로 MOS 리포트 HTML 파싱 → 메타/요약/진단/SWOT/시뮬레이션/로드맵/결론 섹션 추출. |
| `answer_schema.py` | 답변 JSON을 **시맨틱 슬롯**으로 정규화. `sub_category`·질문 텍스트의 부분 문자열 패턴으로 매칭하며 **절대 idx로 키잉하지 않는다**. `persona`/`reason`은 임의 작성이므로 사용 금지. |
| `extractAnswers.py` | 정규화 슬롯 → 규칙 기반 신호(강점/약점 과목, 진로 클러스터 등). 모든 신호에 evidence 동반. |
| `signals.py` | HTML 텍스트 → 학생 신호 + 계열 점수(`infer_category_scores`) + 학과 후보(`choose_target_departments`). |

### 3.3 판정 · 추천

| 파일 | 역할 |
|---|---|
| `answer_pipeline.py` | 3층 파이프라인 오케스트레이터. `run_answer_pipeline()` 단일 진입점. HTML 없이 JSON만 있을 때 signals를 합성하는 `synthesize_signals_from_answers()` 포함. |
| `answerLLM.py` | Layer 1 LLM 구조화기. 나열형 답변·복합 선택지·융합 진로만 보강. 분류·점수 산정은 하지 않음. |
| `decisionEngine.py` | Layer 2 최종 판정자. `RULE_VERSION = decision-2026.05-v1.0`. |
| `mlJudge.py` | Layer 3 ML 교차검증 자문. 프로토타입 Hamming 거리 기반. |
| `validationLoop.py` | Layer 3 검증 루프. `validation_outcomes.jsonl`에 예측·실제 결과 누적, 분기별 적중률 집계. |
| `recommender.py` | 4축 적합도 추천 + 등급 기반 추천(`recommend_universities_by_grade`) + 지원군 분류. |
| `admission_tracks.py` | 학생 신호 → 전형 추천(학종·교과·논술·특기자·지역균형/지역인재·정시). |
| `dept_matching.py` | 사용자가 직접 입력한 희망 학과("컴공", "신방과")를 DB 실제 학과명과 의미 유사도 매칭. 추출 학과와 유사도 < 0.45면 **충돌**로 경고. |
| `embeddings.py` | 3단 fallback 임베딩 · 코사인 유사도 · 인재상 매칭. |
| `student_profile.py` | 강점/약점/관심/위험 4슬롯 진단 카드 합성(결정론적, LLM 자유 생성 금지). |

### 3.4 출력

| 파일 | 역할 |
|---|---|
| `renderUI.py` | Streamlit UI 컴포넌트 — CSS 주입, 히어로, 계열 도넛(Plotly), 학생 프로파일 카드, 전형 추천, 지원군 헤더, 입결 상세 패널, 대학 카드. |
| `report_builder.py` | Gemini 요약(`summarize_with_gemini`, 실패 시 `fallback_summary`) + 다운로드 HTML 2종: 전체 상세본 / 추천 대학·근거만 담은 요약본. |

### 3.5 데이터

| 파일 | 내용 |
|---|---|
| `university_db.json` | 약 22MB. `metadata` / `universities`(179개) / `data_source_note`. 스키마 v2. |

```jsonc
universities[] {
  "name", "region", "type", "aliases",
  "talent_keywords": ["전문성", "글로벌", ...],   // 표준 8범주
  "talent_statement", "notes",
  "departments": [{
    "name", "category", "aliases",
    "admissions": [{
      "type": "학생부교과", "track_name",
      "min_grade_band": "3.38-4.28",
      "cutoff_p50", "cutoff_p70", "cutoff_p90", "cutoff_sigma_est",
      "applicants", "competition_ratio", "fill_rank",
      "cutoff_sample_count", "cutoff_latest_year", "cutoff_source"
    }]
  }]
}
```

**데이터 한계(반드시 인지):** 합격선은 대교협 2020–2024 5개년 수시입결 공시를 **정규분포 근사**로 산출한 값이다. 공시가 없는 학과·전형은 DB에서 제외됐고, 일부 전형의 세부 입결·수능최저는 추정 규칙으로 채워져 있다. 대학별 설치학과 완전성 역시 공식 모집요강 재검증이 필요하다.

### 3.6 `tools/` — 오프라인 유틸리티 (앱에서 import하지 않음)

| 파일 | 역할 |
|---|---|
| `merge_talents.py` | 인재상 자료를 DB에 통합. `OO대` ↔ `OO대학교` 표기 자동 정규화. |
| `merge_univ_aliases.py` | 대학 별칭 파일을 DB에 병합. |
| `enrich_talents.py` | 인재상 공백 대학을 LLM으로 보강. 생성물은 `llm-generated-unverified`로 태깅(비파괴 출력). |
| `apply_talents.py` | 사용자 제공 인재상 키워드 반영. 기존 값은 `talent_keywords_original`에 백업. |
| `standardize_and_dedup.py` | 8범주 이탈 키워드 표준화 + 중복 대학 병합. |
| `group_dept_aliases.py` | 학과명 정규화 후 동일 키 학과끼리 자동 alias 등록("컴퓨터공학과/학부/AI학과" → 한 그룹). |
| `action_library.py` | 컨설턴트가 큐레이션한 표준 행동 라이브러리(IP 자산). 2028 대입 개편·자소서 폐지·지역인재 40% 등 정책 근거를 `source_basis`로 명시. |
| `roadmap.py` | 갭 분석 → 분기별 액션 로드맵 생성. `action_library`를 import하므로 `tools/` 내부에서 실행해야 한다. **현재 `app.py`에 연결되어 있지 않다**(UI에서 로드맵 제거됨). |

---

## 4. 실행 방법

### 4.1 로컬

```bash
git clone https://github.com/dhchang5765/CollegeMatching.git
cd CollegeMatching

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

streamlit run app.py
```
기본 주소: `http://localhost:8501`

### 4.2 시크릿 설정

`.streamlit/secrets.toml.example`을 `.streamlit/secrets.toml`로 복사해 채운다. 또는 `.env` / 환경변수도 동일하게 인식된다.

```toml
GEMINI_API_KEY = "your_api_key_here"
APP_PASSWORD_HASH = "pbkdf2_sha256$240000$<salt_hex>$<hash_hex>"
```

해시 생성:
```python
from password import hash_password
print(hash_password("원하는_비밀번호"))
```

`GEMINI_API_KEY`가 없어도 앱은 동작한다. 다만 LLM 구조화 보강·Gemini 요약·Gemini 임베딩이 비활성화되고 규칙/로컬 모델/lexical fallback으로 대체된다.

### 4.3 사용 흐름

1. 로그인 (`APP_PASSWORD_HASH` 검증)
2. **학생 분석 HTML**과 **학생 답변 JSON**을 **둘 다** 업로드 — 한쪽만 올리면 안내만 표시되고 분석은 실행되지 않는다
3. (선택) 희망 학과 직접 입력 → DB 학과명과 임베딩 매칭. 추출 학과와 충돌하면 경고 후 **사용자 입력을 우선**
4. 결과 확인: 계열 도넛, 학생 프로파일 4슬롯, 전형 추천, 지원군별 대학 카드, 입결 상세
5. 리포트 다운로드: 전체 상세 HTML / 추천 요약 HTML
6. 디버그 확장 패널에서 추출 신호·원시 텍스트·파싱 구조 확인

### 4.4 배포

- **Streamlit Community Cloud**: 저장소 연결 후 Main file을 `app.py`로 지정, Secrets에 위 두 값 입력.
- **Dev Container / Codespaces**: `.devcontainer/devcontainer.json` 포함. Python 3.11-bookworm 이미지, 8501 포트 자동 포워딩, attach 시 `streamlit run app.py` 자동 실행.

> 참고: 이전 README는 저장소 루트에 `packages.txt`를 두도록 안내했으나 현재 저장소에는 존재하지 않는다. `kiwipiepy`·`sentence-transformers` 빌드에 시스템 패키지가 필요한 환경에서만 추가하면 된다.

### 4.5 의존성

```
streamlit>=1.32.0          UI
beautifulsoup4>=4.12.0     HTML 파싱
plotly>=5.20.0             계열 도넛 차트
kiwipiepy>=0.17.0          한국어 형태소 분석
google-genai>=0.4.0        Gemini (선택)
python-dotenv>=1.0.0       .env 로딩
sentence-transformers>=2.7.0  로컬 임베딩 (선택, 용량 큼)
```

---

## 5. 런타임 생성 파일

| 파일 | 생성 주체 | 내용 |
|---|---|---|
| `validation_outcomes.jsonl` | `validationLoop` | 예측 스냅샷 및 실제 합격결과 로그 |
| `ml_prototypes.json` | `mlJudge` | 검증 승격된 레이블 프로토타입 |

두 파일은 축적된 학생 데이터를 담으므로 커밋하지 않는다(`.gitignore` 확인 권장).

---

## 6. 수정 시 지켜야 할 규칙

1. **판정 로직은 `decisionEngine.py`에만** 둔다. LLM에 분류·점수 산정을 위임하지 않는다.
2. 가중치를 바꿀 때는 `RULE_VERSION`을 올린다. 검증 루프의 버전별 적중률 집계가 깨진다.
3. 답변 슬롯을 추가할 때는 `answer_schema.SEMANTIC_SLOTS`에 패턴을 추가한다. idx 하드코딩 금지.
4. 새 신호는 반드시 evidence(출처 문항)를 동반시킨다.
5. DB를 수정할 때는 `tools/`의 비파괴 스크립트를 사용하고 원본을 백업한다.
6. 임베딩·LLM 의존 코드는 항상 `try/except` + fallback 경로를 유지한다.
