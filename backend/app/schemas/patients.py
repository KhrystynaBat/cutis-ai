from __future__ import annotations

import re
import uuid
from datetime import date, datetime

from pydantic import EmailStr, Field, field_validator

from app.core.clock import today_local

from .common import ApiModel

_PHONE = re.compile(r"^\+?[0-9 ()\-]{5,32}$")
MIN_BIRTH_DATE = date(1900, 1, 1)


def _required_text(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    if not v:
        raise ValueError("Поле не може бути порожнім")
    return v


def _optional_text(v: object) -> object:
    if isinstance(v, str):
        return v.strip() or None
    return v


def _check_birth_date(v: date | None) -> date | None:
    if v is None:
        return None
    if v > today_local():
        raise ValueError("Дата народження не може бути в майбутньому")
    if v < MIN_BIRTH_DATE:
        raise ValueError("Дата народження не може бути раніше 1900 року")
    return v


def _check_phone(v: str | None) -> str | None:
    if v is not None and not _PHONE.match(v):
        raise ValueError("Некоректний номер телефону")
    return v


class PatientUpdate(ApiModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)  # по батькові, optional
    date_of_birth: date | None = None
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    notes: str | None = Field(default=None, max_length=2000)

    _names = field_validator("first_name", "last_name")(_required_text)
    _blank = field_validator("middle_name", "email", "phone", "notes", mode="before")(_optional_text)
    _dob = field_validator("date_of_birth")(_check_birth_date)
    _phone = field_validator("phone")(_check_phone)


class PatientCreate(PatientUpdate):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    date_of_birth: date


class PatientOut(ApiModel):
    id: uuid.UUID
    first_name: str
    last_name: str
    middle_name: str | None
    date_of_birth: date
    age: int
    email: str | None
    phone: str | None
    notes: str | None
    is_archived: bool
    cases_count: int
    last_visit: date | None
    created_at: datetime
    updated_at: datetime


class PatientRef(ApiModel):
    id: uuid.UUID
    first_name: str
    last_name: str
    middle_name: str | None = None
    date_of_birth: date
