import base64
import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import models
from .database import get_db

logger = logging.getLogger("freezefly.security")

# ---------------------------------------------------------------- config
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = int(os.getenv("ACCESS_TOKEN_EXPIRE_HOURS", "12"))

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    # ไม่ได้ตั้งค่าไว้ -> สุ่มใหม่ทุกครั้งที่เปิดเซิร์ฟเวอร์ (token เก่าจะใช้ไม่ได้หลังรีสตาร์ท)
    SECRET_KEY = secrets.token_urlsafe(48)
    logger.warning(
        "ไม่ได้ตั้งค่า SECRET_KEY: ใช้ค่าสุ่มชั่วคราว "
        "(ผู้ใช้ต้องล็อกอินใหม่ทุกครั้งที่รีสตาร์ท) กรุณาตั้งค่าใน .env"
    )

# โหมดเปลี่ยนผ่าน: ยอมรับ ?user_id=... แบบเดิมเมื่อไม่มี Bearer token
# ใช้เฉพาะระหว่างที่ frontend ยังไม่ได้แก้ให้ส่ง Authorization header
# (ไม่ปลอดภัย: ใครก็แอบอ้าง user_id ของคนอื่นได้) แก้ frontend เสร็จแล้วให้ตั้งเป็น false
ALLOW_LEGACY_USER_ID = os.getenv("ALLOW_LEGACY_USER_ID", "false").strip().lower() in {
    "1",
    "true",
    "yes",
}
if ALLOW_LEGACY_USER_ID:
    logger.warning(
        "ALLOW_LEGACY_USER_ID=true: ระบบยังยอมรับ user_id จาก query string "
        "ซึ่งไม่ปลอดภัย ควรปิดหลังจากแก้ frontend แล้ว"
    )

bearer_scheme = HTTPBearer(auto_error=False)


# -------------------------------------------------------------- passwords
def _prehash(password: str) -> bytes:
    # bcrypt รับได้ไม่เกิน 72 bytes -> ย่อด้วย SHA-256 ก่อน ได้ความยาวคงที่ 44 bytes
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt()).decode("utf-8")


def is_hashed(stored: str) -> bool:
    return bool(stored) and len(stored) == 60 and stored.startswith(("$2a$", "$2b$", "$2y$"))


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_prehash(password), stored_hash.encode("utf-8"))
    except ValueError:
        return False


# -------------------------------------------------------------------- JWT
def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _legacy_user(request: Request, db: Session) -> Optional[models.User]:
    raw = request.query_params.get("user_id") or request.path_params.get("user_id")
    if raw is not None and str(raw).isdigit() and int(raw) > 0:
        return db.get(models.User, int(raw))
    return None


def _resolve_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials],
    db: Session,
) -> Optional[models.User]:
    if credentials is not None:
        try:
            payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
            user = db.get(models.User, int(payload["sub"]))
            if user is not None:
                return user
        except (jwt.PyJWTError, KeyError, ValueError, TypeError):
            pass
        if not ALLOW_LEGACY_USER_ID:
            raise _unauthorized("โทเคนไม่ถูกต้องหรือหมดอายุ กรุณาเข้าสู่ระบบใหม่")

    if ALLOW_LEGACY_USER_ID:
        return _legacy_user(request, db)
    return None


def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    """บังคับล็อกอิน: ไม่มีตัวตนที่ตรวจสอบได้ -> 401"""
    user = _resolve_user(request, credentials, db)
    if user is None:
        raise _unauthorized("กรุณาเข้าสู่ระบบก่อนทำรายการ")
    return user


def get_optional_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Optional[models.User]:
    """ไม่บังคับล็อกอิน: ไม่มีตัวตน -> None (ใช้กับ endpoint สาธารณะที่ปรับผลตามผู้ใช้ได้)"""
    return _resolve_user(request, credentials, db)