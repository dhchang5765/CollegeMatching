import hashlib
import hmac
import os
import secrets
import streamlit as st

try:
    from dotenv import load_dotenv, find_dotenv

    def _strip_bom(path: str) -> None:
        """Windows 에디터가 붙인 UTF-8 BOM 제거(키 이름 깨짐 방지)."""
        try:
            with open(path, "rb") as f:
                raw = f.read()
            if raw.startswith(b"\xef\xbb\xbf"):
                with open(path, "wb") as f:
                    f.write(raw[3:])
        except Exception:
            pass

    # 탐색: CWD → password.py 동일 폴더
    _env_path = find_dotenv(usecwd=True)
    if not _env_path:
        _cand = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        _env_path = _cand if os.path.exists(_cand) else ""

    if _env_path:
        _strip_bom(_env_path)
        # override=True: 비어있거나 오래된 기존 환경변수를 .env 값으로 덮어씀
        load_dotenv(_env_path, override=True)
except ImportError:
    import warnings
    warnings.warn(
        "python-dotenv 미설치 — .env 파일이 로드되지 않습니다. "
        "'pip install python-dotenv' 후 Streamlit 을 재실행하십시오."
    )


def _secrets_available() -> bool:
    """st.secrets 접근 가능 여부(로컬에 secrets.toml 없으면 False)."""
    try:
        return hasattr(st, "secrets") and len(dict(st.secrets)) >= 0
    except Exception:
        return False


def get_secret_value(key: str, default: str | None = None) -> str | None:
    # 1순위: Streamlit secrets (Streamlit Cloud 배포 환경)
    try:
        if hasattr(st, "secrets") and key in st.secrets:
            value = st.secrets[key]
            if value is None:
                return default
            return str(value).strip()
    except Exception:
        pass

    # 2순위: 환경변수 (load_dotenv 로 로드된 .env 포함, 로컬 환경)
    value = os.getenv(key)
    if value is None:
        return default
    return str(value).strip()

def require_secret(key: str) -> str:
    value = get_secret_value(key)
    if not value:
        st.error(f"필수 설정값 누락: {key}")
        st.stop()
    return value

def hash_password(password: str, iterations: int = 240000) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algo, iter_str, salt_hex, digest_hex = stored_hash.split('$', 3)
        if algo != 'pbkdf2_sha256':
            return False
        iterations = int(iter_str)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        candidate = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
        return hmac.compare_digest(candidate, expected)
    except Exception:
        return False


def require_login() -> bool:
    stored_hash = get_secret_value("APP_PASSWORD_HASH", "")
    if not stored_hash:
        st.warning('APP_PASSWORD_HASH를 찾을 수 없습니다.')
        # 진단 정보: 어디서 막혔는지 즉시 식별
        try:
            import importlib.util
            dotenv_installed = importlib.util.find_spec("dotenv") is not None
        except Exception:
            dotenv_installed = False
        env_in_cwd = os.path.exists(os.path.join(os.getcwd(), ".env"))
        with st.expander("진단 정보", expanded=True):
            diag = {
                "python-dotenv 설치됨": dotenv_installed,
                "현재 작업 디렉터리": os.getcwd(),
                "CWD에 .env 존재": env_in_cwd,
                "환경변수에 키 존재": os.getenv("APP_PASSWORD_HASH") is not None,
                "st.secrets 사용 가능": _secrets_available(),
            }
            # .env 실제 파싱 결과·BOM 확인
            try:
                from dotenv import dotenv_values
                _p = os.path.join(os.getcwd(), ".env")
                if os.path.exists(_p):
                    with open(_p, "rb") as _f:
                        _head = _f.read(3)
                    diag["UTF-8 BOM 존재(원인일 수 있음)"] = _head == b"\xef\xbb\xbf"
                    _keys = list(dotenv_values(_p).keys())
                    diag[".env에서 파싱된 키 목록"] = _keys
                    diag["키 이름 정확히 일치"] = "APP_PASSWORD_HASH" in _keys
            except Exception as _e:
                diag["dotenv 파싱 오류"] = str(_e)
            st.write(diag)
            if not dotenv_installed:
                st.error("원인: python-dotenv 미설치 → `pip install python-dotenv` 후 재실행")
            elif diag.get("UTF-8 BOM 존재(원인일 수 있음)"):
                st.error("원인: .env 파일에 BOM 존재 → UTF-8(BOM 없음)으로 재저장하거나 앱 재시작(자동 제거됨)")
            elif not env_in_cwd:
                st.error("원인: streamlit 실행 위치에 .env 없음 → .env 폴더에서 `streamlit run` 실행")
            elif not diag.get("키 이름 정확히 일치", True):
                st.error("원인: .env 키 이름 불일치(공백/오타/특수문자) → 위 '파싱된 키 목록' 확인")
            else:
                st.error("원인: 기존 환경변수가 빈 값으로 선점 가능 → 새 터미널에서 재실행")
        st.stop()
        
    if st.session_state.get('authenticated'):
        return True
        
    st.markdown('<div class="login-wrap">', unsafe_allow_html=True)
    st.subheader('로그인')
    password = st.text_input('비밀번호', type='password', placeholder='앱 비밀번호 입력')
    submitted = st.button('로그인', width='stretch')
    st.markdown('</div>', unsafe_allow_html=True)
    if submitted:
        if verify_password(password, stored_hash):
            st.session_state['authenticated'] = True
            st.success('인증되었습니다.')
            st.rerun()
        else:
            st.error('비밀번호가 일치하지 않습니다.')
    st.stop()
