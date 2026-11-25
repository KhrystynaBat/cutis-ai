from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.core.names import full_name, patient_greeting, staff_greeting
from app.db.models import Patient, Role, User

SIGNATURE = "З повагою,\nкоманда CutisAI"
AUTO_NOTE = "Це автоматичний лист, відповідати на нього не потрібно."
ROLE_UK = {Role.DOCTOR: "лікар", Role.LAB_SPECIALIST: "лабораторний спеціаліст", Role.ADMIN: "адміністратор"}

_URL = re.compile(r"https?://[^\s<]+")
_P = "margin:0 0 16px"
_HTML = (
    '<!DOCTYPE html><html lang="uk"><head><meta charset="utf-8"></head>'
    '<body style="margin:0;padding:24px;background:#ffffff">'
    '<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.5;'
    'color:#1f2933;max-width:600px">{content}</div></body></html>'
)


@dataclass(frozen=True)
class Attachment:
    filename: str
    content: bytes
    maintype: str = "application"
    subtype: str = "pdf"


@dataclass(frozen=True)
class Letter:
    subject: str
    body: str
    attachments: tuple[Attachment, ...] = field(default=())
    personal: bool = False
    dev_link: str | None = None
    html: str | None = None
    dev_link_kind: str = "SIGN-IN"


def _html_paragraph(text: str) -> str:
    escaped = html.escape(text, quote=False)
    linked = _URL.sub(lambda m: f'<a href="{m.group(0)}" style="color:#0b5cad">{m.group(0)}</a>', escaped)
    return f'<p style="{_P}">{linked.replace(chr(10), "<br>")}</p>'


def compose(
    subject: str,
    greeting: str,
    paragraphs: list[str],
    *,
    attachments: tuple[Attachment, ...] = (),
    personal: bool = True,
    dev_link: str | None = None,
    dev_link_kind: str = "SIGN-IN",
) -> Letter:
    text = "\n\n".join([greeting, *paragraphs, SIGNATURE, AUTO_NOTE])
    content = "".join(_html_paragraph(p) for p in [greeting, *paragraphs, SIGNATURE])
    content += f'<p style="margin:24px 0 0;font-size:12px;color:#8a94a0">{html.escape(AUTO_NOTE)}</p>'
    return Letter(
        subject=subject,
        body=text,
        attachments=attachments,
        personal=personal,
        dev_link=dev_link,
        html=_HTML.format(content=content),
        dev_link_kind=dev_link_kind,
    )


def minutes_uk(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        word = "хвилину"
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        word = "хвилини"
    else:
        word = "хвилин"
    return f"{n} {word}"


def local_time(moment: datetime) -> str:
    return moment.astimezone(ZoneInfo(get_settings().display_timezone)).strftime("%d.%m.%Y, %H:%M")


def invitation(user: User, link: str, expires_at: datetime) -> Letter:
    return compose(
        "Запрошення до системи CutisAI",
        staff_greeting(user),
        [
            f"Для вас створено обліковий запис у системі CutisAI. Ваша роль — {ROLE_UK.get(user.role, '')}.",
            f"Щоб встановити пароль і почати роботу, перейдіть за посиланням:\n{link}",
            f"Посилання спрацює лише один раз і діє до {local_time(expires_at)} (за київським часом).",
            "Якщо ви не очікували цього листа, просто проігноруйте його.",
        ],
    )


def password_reset(user: User, link: str, expires_at: datetime) -> Letter:
    return compose(
        "Відновлення пароля в системі CutisAI",
        staff_greeting(user),
        [
            "Адміністратор системи CutisAI надіслав вам посилання для встановлення нового пароля "
            f"(ваша роль — {ROLE_UK.get(user.role, '')}).",
            f"Щоб встановити новий пароль, перейдіть за посиланням:\n{link}",
            f"Посилання спрацює лише один раз і діє до {local_time(expires_at)} (за київським часом).",
            "Якщо ви не просили змінити пароль, повідомте про це адміністратора.",
        ],
    )


def login_link(user: User, link: str, requested_at: datetime) -> Letter:
    minutes = get_settings().login_link_ttl_minutes
    return compose(
        "Підтвердження входу в CutisAI",
        staff_greeting(user),
        [
            "Ми отримали запит на вхід до вашого облікового запису в системі CutisAI.",
            f"Щоб увійти, перейдіть за посиланням:\n{link}",
            f"Посилання діє {minutes_uk(minutes)} і спрацює лише один раз. "
            "Відкрийте його в тому самому браузері, у якому ви входили в систему.",
            f"Час запиту: {local_time(requested_at)} (за київським часом)",
            "Якщо це були не ви, просто проігноруйте цей лист — без підтвердження вхід не відбудеться. "
            "Радимо також змінити пароль: хтось міг його дізнатися.",
        ],
        dev_link=link,
    )


def email_change_confirm(user: User, link: str, expires_at: datetime) -> Letter:
    return compose(
        "Підтвердження нової адреси в CutisAI",
        staff_greeting(user),
        [
            "Ви попросили змінити адресу електронної пошти для входу в систему CutisAI на цю адресу.",
            f"Підтвердіть нову адресу за посиланням:\n{link}",
            f"Посилання спрацює лише один раз і діє до {local_time(expires_at)} (за київським часом). "
            "Доки адресу не підтверджено, вхід і листи — на попередню адресу.",
            "Якщо ви не просили змінити адресу, просто проігноруйте цей лист — адреса не зміниться.",
        ],
        dev_link=link,
        dev_link_kind="EMAIL-CHANGE",
    )


def email_changed(user: User, new_email_masked: str) -> Letter:
    return compose(
        "Адресу електронної пошти в CutisAI змінено",
        staff_greeting(user),
        [
            f"Адресу вашого облікового запису CutisAI змінено на {new_email_masked}. "
            "Якщо це були не ви — зверніться до адміністратора.",
        ],
    )


def lab_result_with_pdf(patient: Patient, doctor: User, pdf: Attachment) -> Letter:
    return compose(
        "Результат дослідження — CutisAI",
        patient_greeting(patient),
        [
            "Результат вашого гістопатологічного дослідження готовий. Він у вкладенні до цього листа (PDF-файл).",
            f"Щоб обговорити результат, зверніться, будь ласка, до свого лікаря. Ваш лікар — {full_name(doctor)}.",
        ],
        attachments=(pdf,),
    )


def lab_result_neutral(patient: Patient) -> Letter:
    return compose(
        "Інформація щодо результату дослідження",
        patient_greeting(patient),
        [
            "Результат вашого дослідження готовий. Щоб отримати й обговорити висновок, "
            "зверніться, будь ласка, до свого лікаря.",
        ],
    )


TEST_LETTER = compose(
    "CutisAI: перевірка налаштувань пошти",
    "Доброго дня!",
    ["Це тестовий лист від системи CutisAI. Якщо ви його отримали, пошту налаштовано правильно."],
    personal=False,
)
