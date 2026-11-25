from app.db.models import Role

USERS = "/api/v1/admin/users"


def test_staff_and_patient_emails_accept_plus(login_as, make_user):
    admin = login_as(make_user(Role.ADMIN))
    base = {"firstName": "Олена", "lastName": "Гончаренко", "role": "Doctor"}
    r1 = admin.post(USERS, json={**base, "email": "katerynakalyna2026+doctor1@gmail.com"})
    r2 = admin.post(USERS, json={**base, "email": "katerynakalyna2026+doctor2@gmail.com"})
    assert r1.status_code == 201, r1.text
    assert r2.status_code == 201, r2.text
    assert r1.json()["user"]["email"] == "katerynakalyna2026+doctor1@gmail.com"
    dup = admin.post(USERS, json={**base, "email": "KaterynaKalyna2026+Doctor1@gmail.com"})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "EMAIL_TAKEN"

    doctor = login_as(make_user(Role.DOCTOR, email="katerynakalyna2026+doctor9@gmail.com"))
    p = doctor.post(
        "/api/v1/patients",
        json={
            "firstName": "Ірина",
            "lastName": "Кактус",
            "dateOfBirth": "1985-04-12",
            "email": "katerynakalyna2026+patient1@gmail.com",
        },
    )
    assert p.status_code == 201, p.text
    assert p.json()["email"] == "katerynakalyna2026+patient1@gmail.com"
