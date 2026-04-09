import os
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Cookie, Request
from sqlalchemy.orm import Session
from database import get_db
import models

SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production-please")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 8

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_admin(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("admin_token")
    if not token:
        raise HTTPException(status_code=302, headers={"Location": "/admin/login"})
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        role: str = payload.get("role", "")
        if not email or role != "admin":
            raise HTTPException(status_code=302, headers={"Location": "/admin/login"})
    except JWTError:
        raise HTTPException(status_code=302, headers={"Location": "/admin/login"})
    admin = db.query(models.AdminAccount).filter(models.AdminAccount.email == email).first()
    if not admin or not admin.is_active:
        raise HTTPException(status_code=302, headers={"Location": "/admin/login"})
    return admin


def get_current_admin_optional(request: Request, db: Session = Depends(get_db)):
    try:
        return get_current_admin(request, db)
    except HTTPException:
        return None
