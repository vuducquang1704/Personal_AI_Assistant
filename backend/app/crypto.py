"""Mã hoá đối xứng cho dữ liệu nhạy cảm lưu trong CSDL (token Google)."""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings


def _fernet() -> Fernet:
    key = hashlib.sha256(("token-encryption:" + get_settings().jwt_secret).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str | None:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:  # JWT_SECRET đã đổi -> token cũ không dùng được, cần kết nối lại
        return None
