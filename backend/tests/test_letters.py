from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.db.models import Role
from app.email import letters

SIGNATURE_AND_NOTE = "З повагою,\nкоманда CutisAI\n\nЦе автоматичний лист, відповідати на нього не потрібно."
LINK = "http://localhost:8080/login/confirm?token=abc-DEF_123"


def staff(first="Олена", middle="Віталіївна", role=Role.DOCTOR):
    return SimpleNamespace(first_name=first, middle_name=middle, last_name="Гончаренко", role=role)


def patient(first="Ірина", middle="Вікторівна"):
    return SimpleNamespace(first_name=first, middle_name=middle, last_name="Кактус")


def all_letters():
    now = datetime(2026, 11, 14, 22, 55, tzinfo=UTC)
    pdf = letters.Attachment("REF-1-lab-result.pdf", b"%PDF-1.4")
    doctor = SimpleNamespace(first_name="Олена", middle_name="Віталіївна", last_name="Гончаренко")
    return {
        "invitation": letters.invitation(staff(), "http://localhost:8080/set-password#token=x", now),
        "reset": letters.password_reset(staff(), "http://localhost:8080/set-password#token=x", now),
        "login": letters.login_link(staff(), LINK, now),
        "result_pdf": letters.lab_result_with_pdf(patient(), doctor, pdf),
        "result_neutral": letters.lab_result_neutral(patient()),
        "test": letters.TEST_LETTER,
    }


@pytest.mark.parametrize("kind", list(all_letters()))
def test_every_letter_ends_the_same_and_has_html(kind):
    letter = all_letters()[kind]
    assert letter.body.endswith(SIGNATURE_AND_NOTE)
    assert "команда CutisAI" in letter.html
    assert 'font-size:12px;color:#8a94a0">Це автоматичний лист, відповідати на нього не потрібно.' in letter.html
    for word in ("Вітаємо", "Шановний(а) Ірина", "​"):
        assert word not in letter.body


def test_staff_letters_greet_in_the_vocative():
    for kind in ("invitation", "reset", "login"):
        assert all_letters()[kind].body.startswith("Доброго дня, Олено Віталіївно!\n\n")
    no_name = letters.login_link(staff(None, None, Role.ADMIN), LINK, datetime.now(UTC))
    assert no_name.body.startswith("Доброго дня!\n\n")


def test_patient_letters_greet_in_the_vocative_and_carry_no_diagnosis():
    pdf_letter = all_letters()["result_pdf"]
    assert pdf_letter.body.startswith("Шановна Ірино Вікторівно!\n\n")
    assert "Ваш лікар — Гончаренко Олена Віталіївна." in pdf_letter.body
    assert [a.filename for a in pdf_letter.attachments] == ["REF-1-lab-result.pdf"]
    assert letters.lab_result_neutral(patient("Тарас", "Миколайович")).body.startswith("Шановний Тарасе Миколайовичу!")
    assert letters.lab_result_neutral(patient("Ганна", None)).body.startswith("Шановний(а) Ганно!")
    assert letters.lab_result_neutral(patient(None, None)).body.startswith("Доброго дня!")


def test_login_letter_text(monkeypatch):
    letter = all_letters()["login"]
    assert letter.subject == "Підтвердження входу в CutisAI"
    assert letter.body == (
        "Доброго дня, Олено Віталіївно!\n\n"
        "Ми отримали запит на вхід до вашого облікового запису в системі CutisAI.\n\n"
        f"Щоб увійти, перейдіть за посиланням:\n{LINK}\n\n"
        "Посилання діє 10 хвилин і спрацює лише один раз. "
        "Відкрийте його в тому самому браузері, у якому ви входили в систему.\n\n"
        "Час запиту: 15.11.2026, 00:55 (за київським часом)\n\n"
        "Якщо це були не ви, просто проігноруйте цей лист — без підтвердження вхід не відбудеться. "
        "Радимо також змінити пароль: хтось міг його дізнатися.\n\n" + SIGNATURE_AND_NOTE
    )
    assert f'<a href="{LINK}" style="color:#0b5cad">{LINK}</a>' in letter.html
    assert "<button" not in letter.html and "<table" not in letter.html


@pytest.mark.parametrize(
    ("minutes", "text"),
    [
        (1, "1 хвилину"),
        (2, "2 хвилини"),
        (4, "4 хвилини"),
        (5, "5 хвилин"),
        (10, "10 хвилин"),
        (11, "11 хвилин"),
        (12, "12 хвилин"),
        (21, "21 хвилину"),
        (22, "22 хвилини"),
        (25, "25 хвилин"),
    ],
)
def test_link_lifetime_follows_the_setting(minutes, text, monkeypatch):
    monkeypatch.setattr(get_settings(), "login_link_ttl_minutes", minutes)
    body = letters.login_link(staff(), LINK, datetime.now(UTC)).body
    assert f"Посилання діє {text} і спрацює лише один раз." in body


def test_request_time_is_in_display_timezone(monkeypatch):
    monkeypatch.setattr(get_settings(), "display_timezone", "UTC")
    when = datetime(2026, 1, 2, 3, 4, tzinfo=UTC) + timedelta(seconds=30)
    assert "Час запиту: 02.01.2026, 03:04" in letters.login_link(staff(), LINK, when).body


def test_html_escapes_names():
    evil = staff("<b>Олена</b>", None)
    assert "<b>" not in letters.invitation(evil, "http://x/set-password#token=t", datetime.now(UTC)).html
