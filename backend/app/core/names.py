from __future__ import annotations

from typing import Protocol

from sqlalchemy import ColumnElement, func, or_


class Named(Protocol):
    first_name: str | None
    last_name: str | None
    middle_name: str | None


NO_NAME = "Адміністратор"  # an administrator may have no name


def full_name(p: Named) -> str:
    return " ".join(x for x in (p.last_name, p.first_name, p.middle_name) if x) or NO_NAME


def short_name(p: Named) -> str:
    initials = " ".join(f"{x[0]}." for x in (p.first_name, p.middle_name) if x)
    return f"{p.last_name or ''} {initials}".strip() or NO_NAME


def given_names(p: Named) -> str:
    return " ".join(x for x in (p.first_name, p.middle_name) if x)


def name_matches(model, like: str) -> ColumnElement[bool]:
    middle = func.coalesce(model.middle_name, "")
    variants = (
        model.last_name + " " + model.first_name + " " + middle,
        model.first_name + " " + middle + " " + model.last_name,
        model.first_name + " " + model.last_name,
    )
    return or_(*(func.lower(v).like(like) for v in variants))


_CONSONANTS = set("бвгґджзйклмнпрстфхцчшщ")
_TAKES_E = set("бвдзлмнпрстф")
_MALE_EXCEPTIONS = {"ігор": "Ігорю", "олег": "Олеже"}
_NOT_INFLECTED = {"ілля"}


def _gender_by_patronymic(middle: str) -> str | None:
    low = middle.lower()
    if low.endswith("ович"):
        return "m"
    if low.endswith(("івна", "ївна")):
        return "f"
    return None


def _vocative_patronymic(middle: str) -> str | None:
    low = middle.lower()
    if low.endswith("ович"):  # also -йович
        return middle + "у"
    if low.endswith(("івна", "ївна")):
        return middle[:-1] + "о"
    return None


def _vocative_first(first: str, gender: str | None) -> str | None:
    low = first.lower()
    if len(low) < 2 or low in _NOT_INFLECTED:
        return None
    if low in _MALE_EXCEPTIONS and gender != "f":
        return _MALE_EXCEPTIONS[low]
    if low.endswith("ія"):
        return first[:-1] + "є"
    if low.endswith("а"):
        return first[:-1] + "о"
    if low.endswith("я") and low[-2] in _CONSONANTS:
        return first[:-1] + "ю"
    if gender == "f":
        return None
    if low.endswith("ій"):
        return first[:-1] + "ю"
    if low.endswith("ь"):
        return first[:-1] + "ю"
    if low.endswith("о"):
        return first[:-1] + "е"
    if low[-1] in _TAKES_E:
        return first + "е"
    return None


def vocative(first_name: str | None, middle_name: str | None) -> str | None:
    first = (first_name or "").strip()
    middle = (middle_name or "").strip()
    if not first:
        return None
    gender = _gender_by_patronymic(middle) if middle else None
    first_v = _vocative_first(first, gender)
    if first_v is None:
        return None
    if not middle:
        return first_v
    middle_v = _vocative_patronymic(middle)
    return f"{first_v} {middle_v}" if middle_v else None


def staff_greeting(p: Named) -> str:
    v = vocative(p.first_name, p.middle_name)
    return f"Доброго дня, {v}!" if v else "Доброго дня!"


def patient_greeting(p: Named) -> str:
    v = vocative(p.first_name, p.middle_name)
    if not v:
        return "Доброго дня!"
    gender = _gender_by_patronymic(p.middle_name or "") if p.middle_name else None
    title = {"m": "Шановний", "f": "Шановна"}.get(gender or "", "Шановний(а)")
    return f"{title} {v}!"
