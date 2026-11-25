from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.auth.deps import AuthContext, get_auth, get_current_user
from app.auth.security import hash_password, needs_rehash, verify_password
from app.auth.sessions import (
    SESSION_COOKIE,
    clear_auth_cookies,
    create_session,
    now_utc,
    resolve_session,
    revoke_user_sessions,
    set_auth_cookies,
)
from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.models import User
from app.db.session import get_db
from app.email import outbox
from app.schemas.users import (
    PROFILE_OPTIONAL_FIELDS,
    ChangePasswordRequest,
    EmailChangeConfirm,
    EmailChangeConfirmed,
    EmailChangePending,
    EmailChangeStart,
    LoginConfirmRequest,
    LoginPending,
    LoginRequest,
    Profile,
    ProfileUpdate,
    SetPasswordRequest,
)
from app.services import audit, email_change
from app.services import login_confirmation as confirmation
from app.services import users as user_service

router = APIRouter(prefix="/auth", tags=["auth"])

INVALID_CREDENTIALS = "Невірна електронна пошта або пароль"


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _pending(user: User) -> LoginPending:
    return LoginPending(
        status="confirmation_required",
        email_masked=outbox.mask_email(user.email),
        expires_in_minutes=get_settings().login_link_ttl_minutes,
    )


@router.post("/login", response_model=Profile | LoginPending)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> User | LoginPending:
    limiter = request.app.state.login_limiter
    key = f"{_client_ip(request)}|{user_service.normalize_email(body.email)}"
    retry = limiter.retry_after(key)
    if retry:
        raise ApiError(429, "TOO_MANY_ATTEMPTS", f"Забагато спроб входу. Спробуйте через {retry // 60 + 1} хв")

    user = user_service.get_by_email(db, body.email)
    if not verify_password(user.password_hash if user else None, body.password) or user is None:
        limiter.record_failure(key)
        audit.record(db, "login_failed", "user", user.id if user else None)
        db.commit()
        raise ApiError(401, "INVALID_CREDENTIALS", INVALID_CREDENTIALS)
    if not user.is_active:
        raise ApiError(403, "ACCOUNT_DISABLED", "Обліковий запис заблоковано. Зверніться до адміністратора")

    limiter.reset(key)
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    if get_settings().login_email_confirmation:
        issued, nonce = confirmation.start(db, user, _client_ip(request), request.headers.get("user-agent"))
        db.commit()
        background.add_task(
            outbox.send_user_link,
            issued.outbox_id,
            issued.token,
            issued.expires_at,
            requested_at=issued.requested_at,
        )
        confirmation.set_pending_cookie(response, nonce)
        return _pending(user)
    user.last_login_at = now_utc()
    token = create_session(db, user)
    audit.record(db, "login", "user", user.id, actor_id=user.id)
    db.commit()
    set_auth_cookies(response, token)
    return user


@router.post("/login/confirm", response_model=Profile)
def confirm_login(
    body: LoginConfirmRequest, request: Request, response: Response, db: Session = Depends(get_db)
) -> User:
    user = confirmation.confirm(db, body.token, request.cookies.get(confirmation.PENDING_COOKIE))
    user.last_login_at = now_utc()
    token = create_session(db, user)
    db.commit()
    confirmation.clear_pending_cookie(response)
    set_auth_cookies(response, token)
    return user


@router.post("/login/resend", response_model=LoginPending)
def resend_login_link(
    request: Request, response: Response, background: BackgroundTasks, db: Session = Depends(get_db)
) -> LoginPending:
    nonce = request.cookies.get(confirmation.PENDING_COOKIE)
    issued, user = confirmation.resend(db, nonce)
    db.commit()
    background.add_task(
        outbox.send_user_link,
        issued.outbox_id,
        issued.token,
        issued.expires_at,
        requested_at=issued.requested_at,
    )
    confirmation.set_pending_cookie(response, nonce)
    return _pending(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> None:
    auth.session.revoked_at = now_utc()
    audit.record(db, "logout", "user", auth.user.id, actor_id=auth.user.id)
    db.commit()
    clear_auth_cookies(response)


def _profile(db: Session, user: User) -> Profile:
    profile = Profile.model_validate(user)
    req = email_change.pending(db, user)
    if req is not None:
        profile.pending_email_masked = outbox.mask_email(req.new_email)
    return profile


@router.get("/me", response_model=Profile)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Profile:
    return _profile(db, user)


@router.patch("/me", response_model=Profile)
def update_my_profile(
    body: ProfileUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Profile:
    changed: list[str] = []
    for field in ("first_name", "last_name"):
        value = getattr(body, field)
        if value is not None and value != getattr(user, field):
            setattr(user, field, value)
            changed.append(field)
    for field in PROFILE_OPTIONAL_FIELDS:  # absent = unchanged, null/"" = removed
        if field in body.model_fields_set and getattr(body, field) != _plain(getattr(user, field)):
            setattr(user, field, user_service.column_value(field, getattr(body, field)))
            changed.append(field)
    if changed:
        audit.record(db, "profile_updated", "user", user.id, actor_id=user.id, metadata={"fields": changed})
    db.commit()
    return _profile(db, user)


def _plain(value: object) -> object:
    return getattr(value, "value", value)


@router.post("/me/email-change", response_model=EmailChangePending, status_code=status.HTTP_202_ACCEPTED)
def request_email_change(
    body: EmailChangeStart,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EmailChangePending:
    issued = email_change.request_change(db, user, body.new_email, body.current_password)
    db.commit()
    background.add_task(outbox.send_user_link, issued.outbox_id, issued.token, issued.expires_at)
    return EmailChangePending(pending_email_masked=outbox.mask_email(issued.new_email), expires_at=issued.expires_at)


@router.delete("/me/email-change", status_code=status.HTTP_204_NO_CONTENT)
def cancel_email_change(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    email_change.cancel(db, user)
    db.commit()


@router.post("/email-change/confirm", response_model=EmailChangeConfirmed)
def confirm_email_change(
    body: EmailChangeConfirm, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)
) -> EmailChangeConfirmed:
    token = request.cookies.get(SESSION_COOKIE)
    resolved = resolve_session(db, token, touch=False) if token else None
    sess = resolved[0] if resolved else None
    user = email_change.confirm(db, body.token, sess.user_id if sess else None, sess.id if sess else None)
    db.commit()
    background.add_task(outbox.dispatch_in_background)  # the notice to the old address
    return EmailChangeConfirmed(
        email_masked=outbox.mask_email(user.email), signed_in=sess is not None and sess.user_id == user.id
    )


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(body: ChangePasswordRequest, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    user = auth.user
    if not verify_password(user.password_hash, body.current_password):
        raise ApiError(400, "WRONG_PASSWORD", "Поточний пароль невірний")
    if body.new_password == body.current_password:
        raise ApiError(422, "WEAK_PASSWORD", "Новий пароль має відрізнятися від поточного")
    user_service.set_password(db, user, body.new_password)
    revoke_user_sessions(db, user.id, except_session_id=auth.session.id)
    audit.record(db, "password_changed", "user", user.id, actor_id=user.id)
    db.commit()


@router.post("/set-password", status_code=status.HTTP_204_NO_CONTENT)
def set_password_with_token(body: SetPasswordRequest, db: Session = Depends(get_db)) -> None:
    user_service.consume_password_token(db, body.token, body.new_password)
    db.commit()
