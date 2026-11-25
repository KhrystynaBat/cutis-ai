import uuid

import pytest

from app.core.names import staff_greeting, vocative
from app.db.models import Role, User
from app.schemas.users import Profile


@pytest.mark.parametrize(
    ("first", "middle", "expected"),
    [
        ("Олена", "Віталіївна", "Олено Віталіївно"),
        ("Тарас", "Миколайович", "Тарасе Миколайовичу"),
        ("Марія", "Іванівна", "Маріє Іванівно"),
        ("Андрій", None, "Андрію"),
        ("Любов", "Петрівна", None),
        (None, None, None),
    ],
)
def test_profile_greeting_name(first, middle, expected):
    user = User(id=uuid.uuid4(), first_name=first, middle_name=middle, email="x@example.test", role=Role.DOCTOR)
    data = Profile.model_validate(user).model_dump(by_alias=True)
    assert data["greetingName"] == expected
    assert data["greetingName"] == vocative(first, middle)


def test_me_returns_greeting_name(make_user, login_as):
    user = make_user(Role.DOCTOR, first_name="Олена", middle_name="Віталіївна")
    me = login_as(user).get("/api/v1/auth/me").json()
    assert me["greetingName"] == "Олено Віталіївно"


def test_letters_and_pages_share_the_rules():
    user = User(first_name="Олена", middle_name="Віталіївна")
    assert staff_greeting(user) == f"Доброго дня, {vocative('Олена', 'Віталіївна')}!"
