from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

import email_validator
from pydantic import ConfigDict, EmailStr, Field, computed_field, field_validator

from app.core.clock import today_local
from app.core.names import vocative
from app.db.models import Role, User

from .common import ApiModel
from .patients import _check_phone

if "test" in email_validator.SPECIAL_USE_DOMAIN_NAMES:
    email_validator.SPECIAL_USE_DOMAIN_NAMES.remove("test")

UserStatus = Literal["Active", "Blocked", "Deactivated"]
SexValue = Literal["Female", "Male"]
STAFF_MIN_AGE, STAFF_MAX_AGE = 18, 100
StaffRole = Literal["Doctor", "LabSpecialist"]  # admins are created only by the seed command


def user_status(user: User) -> UserStatus:
    if user.deactivated_at is not None:
        return "Deactivated"
    return "Active" if user.is_active else "Blocked"


def _age_on(born: date, day: date) -> int:
    return day.year - born.year - ((day.month, day.day) < (born.month, born.day))


def _check_staff_birth_date(v: date | None) -> date | None:
    if v is None:
        return None
    today = today_local()
    if v > today:
        raise ValueError("Дата народження не може бути в майбутньому")
    age = _age_on(v, today)
    if age < STAFF_MIN_AGE or age > STAFF_MAX_AGE:
        raise ValueError(f"Вік має бути від {STAFF_MIN_AGE} до {STAFF_MAX_AGE} років")
    return v


def _strip(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("Поле не може бути порожнім")
    return v


class Profile(ApiModel):
    id: uuid.UUID
    first_name: str | None = None
    last_name: str | None = None
    middle_name: str | None = None
    phone: str | None = None
    birth_date: date | None = None
    sex: SexValue | None = None
    email: str
    role: Role
    pending_email_masked: str | None = None
    last_login_at: datetime | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def greeting_name(self) -> str | None:
        return vocative(self.first_name, self.middle_name)


class LoginRequest(ApiModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class LoginPending(ApiModel):
    status: Literal["confirmation_required"]
    email_masked: str
    expires_in_minutes: int


class LoginConfirmRequest(ApiModel):
    token: str = Field(min_length=20, max_length=128)


class ChangePasswordRequest(ApiModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class SetPasswordRequest(ApiModel):
    token: str = Field(min_length=20, max_length=128)
    new_password: str = Field(min_length=1, max_length=256)


class UserOut(ApiModel):
    id: uuid.UUID
    first_name: str | None
    last_name: str | None
    middle_name: str | None
    phone: str | None
    birth_date: date | None = None
    sex: SexValue | None = None
    email: str
    role: Role
    status: UserStatus
    has_password: bool
    created_at: datetime
    last_login_at: datetime | None

    @classmethod
    def of(cls, u: User) -> UserOut:
        return cls(
            id=u.id,
            first_name=u.first_name,
            last_name=u.last_name,
            middle_name=u.middle_name,
            phone=u.phone,
            birth_date=u.birth_date,
            sex=u.sex.value if u.sex else None,
            email=u.email,
            role=u.role,
            status=user_status(u),
            has_password=u.password_hash is not None,
            created_at=u.created_at,
            last_login_at=u.last_login_at,
        )


def _optional_name(v: object) -> object:
    if isinstance(v, str):
        return v.strip() or None
    return v


class UserCreate(ApiModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=32)
    birth_date: date | None = None
    sex: SexValue | None = None
    email: EmailStr
    role: StaffRole
    is_active: bool = True

    _strip_names = field_validator("first_name", "last_name")(_strip)
    _middle = field_validator("middle_name", "phone", mode="before")(_optional_name)
    _phone = field_validator("phone")(_check_phone)
    _birth = field_validator("birth_date")(_check_staff_birth_date)


class UserUpdate(ApiModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=32)  # same rules as for patients
    birth_date: date | None = None
    sex: SexValue | None = None
    email: EmailStr | None = None
    role: StaffRole | None = None

    _middle = field_validator("middle_name", "phone", mode="before")(_optional_name)
    _phone = field_validator("phone")(_check_phone)
    _birth = field_validator("birth_date")(_check_staff_birth_date)

    @field_validator("first_name", "last_name")
    @classmethod
    def _strip_optional(cls, v: str | None) -> str | None:
        return None if v is None else _strip(v)


PROFILE_OPTIONAL_FIELDS = ("middle_name", "phone", "birth_date", "sex")


class ProfileUpdate(ApiModel):
    model_config = ConfigDict(extra="forbid")

    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=32)
    birth_date: date | None = None
    sex: SexValue | None = None

    _middle = field_validator("middle_name", "phone", mode="before")(_optional_name)
    _phone = field_validator("phone")(_check_phone)
    _birth = field_validator("birth_date")(_check_staff_birth_date)

    @field_validator("first_name", "last_name")
    @classmethod
    def _strip_optional(cls, v: str | None) -> str | None:
        return None if v is None else _strip(v)


class EmailChangeStart(ApiModel):
    new_email: EmailStr
    current_password: str = Field(min_length=1, max_length=256)


class EmailChangePending(ApiModel):
    pending_email_masked: str
    expires_at: datetime


class EmailChangeConfirm(ApiModel):
    token: str = Field(min_length=20, max_length=128)


class EmailChangeConfirmed(ApiModel):
    email_masked: str
    signed_in: bool


class PasswordToken(ApiModel):
    token: str
    expires_at: datetime
    purpose: Literal["Invitation", "PasswordReset"]
    email_queued: bool = False


class UserCreated(ApiModel):
    user: UserOut
    invitation: PasswordToken
