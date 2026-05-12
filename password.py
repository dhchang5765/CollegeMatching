import hashlib
import hmac
import os
import secrets
import streamlit as st

def get_secret_value(key: str, default: str | None = None) -> str | None:
    try:
        if hasattr(st, "secrets") and key in st.secrets:
            value = st.secrets[key]
            if value is None:
                return default
            return str(value).strip()
    except Exception:
        pass

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
        st.warning('APP_PASSWORD_HASH가 설정되지 않았습니다. Streamlit Cloud의 Secrets를 확인하십시오.')
        st.stop()
        
    if st.session_state.get('authenticated'):
        return True
        
    st.markdown('<div class="login-wrap">', unsafe_allow_html=True)
    st.subheader('로그인')
    password = st.text_input('비밀번호', type='password', placeholder='앱 비밀번호 입력')
    submitted = st.button('로그인', use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)
    if submitted:
        if verify_password(password, stored_hash):
            st.session_state['authenticated'] = True
            st.success('인증되었습니다.')
            st.rerun()
        else:
            st.error('비밀번호가 일치하지 않습니다.')
    st.stop()
