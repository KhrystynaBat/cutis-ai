from types import SimpleNamespace

import pytest

from app.core.names import patient_greeting, staff_greeting, vocative

CASES = [
    # staff in the dev database
    ("Олена", "Віталіївна", "Олено Віталіївно"),
    ("Марія", "Іванівна", "Маріє Іванівно"),
    ("Світлана", "Олександрівна", "Світлано Олександрівно"),
    ("Ірина", "Степанівна", "Ірино Степанівно"),
    ("Тарас", "Миколайович", "Тарасе Миколайовичу"),
    ("Дмитро", "Ігорович", "Дмитре Ігоровичу"),
    # patients in the dev database
    ("Катерина", "Сергіївна", "Катерино Сергіївно"),
    ("Оксана", "Сергіївна", "Оксано Сергіївно"),
    ("Наталія", "Олегівна", "Наталіє Олегівно"),
    ("Ірина", "Іванівна", "Ірино Іванівно"),
    ("Ірина", "Вікторівна", "Ірино Вікторівно"),
    ("Лідія", "Петрівна", "Лідіє Петрівно"),
    ("Петро", "Іванович", "Петре Івановичу"),
    ("Василь", "Петрович", "Василю Петровичу"),
    ("Михайло", "Андрійович", "Михайле Андрійовичу"),
    # the rules
    ("Ольга", None, "Ольго"),
    ("Галя", None, "Галю"),
    ("Андрій", None, "Андрію"),
    ("Сергій", "Олексійович", "Сергію Олексійовичу"),
    ("Микола", "Іванович", "Миколо Івановичу"),
    ("Ігор", "Петрович", "Ігорю Петровичу"),
    ("Олег", None, "Олеже"),
    ("Іван", None, "Іване"),
    ("Олександр", "Васильович", "Олександре Васильовичу"),
    ("Олена", None, "Олено"),
    ("Наталія", "Андріївна", "Наталіє Андріївно"),
]


@pytest.mark.parametrize(("first", "middle", "expected"), CASES)
def test_vocative(first, middle, expected):
    assert vocative(first, middle) == expected


@pytest.mark.parametrize(
    ("first", "middle"),
    [
        (None, None),
        ("", "Іванівна"),
        ("Любов", "Іванівна"),
        ("Ілля", None),  # masculine -я
        ("Марк", None),
        ("Олена", "Ілліч"),  # unknown patronymic ending
        ("Х", None),
    ],
)
def test_no_rule_means_no_name(first, middle):
    assert vocative(first, middle) is None


def _p(first, middle=None):
    return SimpleNamespace(first_name=first, middle_name=middle, last_name="Прізвище")


def test_staff_greeting():
    assert staff_greeting(_p("Олена", "Віталіївна")) == "Доброго дня, Олено Віталіївно!"
    assert staff_greeting(_p("Олена")) == "Доброго дня, Олено!"
    assert staff_greeting(_p(None)) == "Доброго дня!"  # an administrator without a name
    assert staff_greeting(_p("Любов", "Іванівна")) == "Доброго дня!"


def test_patient_greeting():
    assert patient_greeting(_p("Ірина", "Вікторівна")) == "Шановна Ірино Вікторівно!"
    assert patient_greeting(_p("Тарас", "Миколайович")) == "Шановний Тарасе Миколайовичу!"
    assert patient_greeting(_p("Ганна")) == "Шановний(а) Ганно!"
    assert patient_greeting(_p("Любов", "Іванівна")) == "Доброго дня!"
