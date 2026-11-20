"""Bearer-token auth with tenant scoping. Every handler gets a Principal and must filter by its merchant_id."""
import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from . import clock
from .config import get_settings
from .db import get_db
from .models import AuthSession, User


@dataclass
class Principal:
    user_id: str
    merchant_id: str
    role: str
    name: str


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_token(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    db.add(AuthSession(token_hash=_hash(token), user_id=user.id,
                       expires_at=clock.now() + timedelta(hours=get_settings().session_hours)))
    return token


def current_principal(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing bearer token")
    session = db.get(AuthSession, _hash(authorization[7:].strip()))
    if session is None or session.expires_at < clock.now():
        raise HTTPException(401, "Invalid or expired token")
    user = db.get(User, session.user_id)
    return Principal(user_id=user.id, merchant_id=user.merchant_id, role=user.role, name=user.name)


def require_role(*roles: str):
    def dep(p: Principal = Depends(current_principal)) -> Principal:
        if p.role not in roles:
            raise HTTPException(403, f"This action requires one of: {', '.join(roles)}")
        return p
    return dep


can_write = require_role("owner", "staff")
owner_only = require_role("owner")


def owned(db: Session, model, row_id: str, merchant_id: str):
    """Tenant-scoped fetch: rows of other merchants are indistinguishable from missing rows."""
    row = db.get(model, row_id)
    if row is None or row.merchant_id != merchant_id:
        raise HTTPException(404, f"{model.__name__} not found")
    return row
