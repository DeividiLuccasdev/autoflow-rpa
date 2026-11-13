"""Convites de uso único, senhas derivadas e sessões opacas revogáveis."""

import re
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import is_secure
from ..db import get_db
from ..models import Invitation, LoginSession, User
from ..security import current_identity, digest, password_hash, verify_password

router = APIRouter(prefix="/auth", tags=["Contas"])


# Mesmo custo de derivação para e-mail inexistente, sem hash extra por requisição.
DUMMY_HASH = password_hash("not-a-real-account-password")


class EmailBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("E-mail inválido")
        return value


class LoginBody(EmailBody):
    password: str = Field(min_length=1, max_length=128, repr=False)


class RegisterBody(EmailBody):
    password: str = Field(min_length=15, max_length=128, repr=False)
    invitation: str = Field(min_length=32, max_length=128, repr=False)


@router.post("/invitations", status_code=201)
def invite(body: EmailBody, identity=Depends(current_identity), db: Session = Depends(get_db)):
    if not identity["legacy"]:
        raise HTTPException(403, "Somente o operador pode emitir convites")
    token = secrets.token_urlsafe(32)
    expires = datetime.now(UTC) + timedelta(hours=24)
    db.add(Invitation(token_hash=digest(token), email=body.email, expires_at=expires))
    db.commit()
    return {"invitation": token, "expires_at": expires, "email": body.email}


@router.post("/register", status_code=201)
def register(body: RegisterBody, db: Session = Depends(get_db)):
    hashed = password_hash(body.password)
    now = datetime.now(UTC)
    claimed = db.execute(
        update(Invitation)
        .where(
            Invitation.token_hash == digest(body.invitation),
            Invitation.email == body.email,
            Invitation.consumed_at.is_(None),
            Invitation.expires_at > now,
        )
        .values(consumed_at=now)
    )
    if claimed.rowcount != 1:
        db.rollback()
        raise HTTPException(400, "Convite inválido, utilizado ou expirado")
    user = User(email=body.email, password_hash=hashed)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(400, "Não foi possível ativar esta conta") from None
    return {"message": "Conta ativada. Entre com seu e-mail e senha."}


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email))
    valid = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid:
        raise HTTPException(401, "E-mail ou senha inválidos")
    now = datetime.now(UTC)
    db.execute(delete(LoginSession).where(LoginSession.expires_at <= now))
    token, csrf = secrets.token_urlsafe(32), secrets.token_hex(32)
    db.add(
        LoginSession(token_hash=digest(token), user_id=user.id, csrf_token=csrf, expires_at=now + timedelta(hours=8))
    )
    db.commit()
    response.set_cookie(
        "autoflow_session",
        token,
        max_age=8 * 3600,
        httponly=True,
        secure=is_secure(request),
        samesite="strict",
        path="/",
    )
    return {"email": user.email, "csrf_token": csrf}


@router.get("/me")
def me(identity=Depends(current_identity)):
    if identity["legacy"]:
        raise HTTPException(403, "Entre com uma conta individual")
    return {"email": identity["email"], "csrf_token": identity["csrf_token"]}


@router.post("/logout", status_code=204)
def logout(response: Response, identity=Depends(current_identity), db: Session = Depends(get_db)):
    if not identity["legacy"]:
        db.execute(delete(LoginSession).where(LoginSession.token_hash == identity["session_hash"]))
        db.commit()
    response.delete_cookie("autoflow_session", path="/", httponly=True, samesite="strict")
