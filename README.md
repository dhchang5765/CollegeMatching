# CollegeMatching
VAMOS EDULAB MOS Application

## Cloud 배포

이 프로젝트는 Streamlit Community Cloud에 배포할 수 있도록 구성되어 있습니다.

### 저장소 루트 구조

아래 파일들을 GitHub 저장소 루트에 둡니다.

```text
your-repo/
├─ app.py
├─ university_db.json
├─ constants.py
├─ extractHTML.py
├─ password.py
├─ renderUI.py
├─ utils.py
├─ requirements.txt
├─ packages.txt
├─ README.md
└─ .streamlit/
   └─ secrets.toml.example
```


### 파일 별 기능

app.py - 메인 실행 함수
university_db.json - 대학 데이터 json
constants.py - 상수 저장
extractHTML.py - HTML 파싱 함수
password.py - 로그인 관련
renderUI.py - UI 관련
utils.py - 유틸리티
