from __future__ import annotations

import argparse
import csv
import getpass
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from clinical_texts import TEXTS  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]

PATIENTS = [
    ("Оксана", "Демченко", "Миколаївна", "1978-03-14", "+380 (50) 000-01-01", "mel"),
    ("Богдан", "Кравець", "Петрович", "1965-11-02", "+380 (67) 000-02-02", "bcc"),
    ("Ірина", "Мельничук", "Андріївна", "1990-07-21", None, "nv"),
    ("Тарас", "Гнатюк", "Степанович", "1952-01-30", "+380 (93) 000-04-04", "akiec"),
    ("Марта", "Савчук", "Іванівна", "1983-09-09", None, "bkl"),
    ("Андрій", "Бондар", "Васильович", "1999-05-17", "+380 (66) 000-06-06", "df"),
    ("Галина", "Петрук", "Олегівна", "1971-12-05", None, "vasc"),
]
DEFAULT_PHOTO = "ISIC_0027175.jpg"


def pick_photos(images: Path, metadata: Path | None) -> dict[str, Path]:
    by_class: dict[str, Path] = {}
    if metadata and metadata.is_file():
        rows = sorted(csv.DictReader(metadata.open(encoding="utf-8")), key=lambda r: r["image_id"])
        for r in rows:
            p = images / f"{r['image_id']}.jpg"
            if r["dx"] not in by_class and p.is_file():
                by_class[r["dx"]] = p
    if not by_class:
        files = sorted(images.glob("ISIC_*.jpg"))
        if not files:
            sys.exit(f"У теці {images} немає фото ISIC_*.jpg")
        codes = ["mel", "bcc", "nv", "akiec", "bkl", "df", "vasc"]
        by_class = {c: files[i % len(files)] for i, c in enumerate(codes)}
    return by_class


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--email", required=True, help="an existing doctor's e-mail")
    ap.add_argument("--base-url", default="http://localhost:8080")
    ap.add_argument("--images", type=Path, default=BACKEND.parent / "data" / "images")
    ap.add_argument("--metadata", type=Path, default=BACKEND.parent / "data" / "HAM10000_metadata.csv")
    ap.add_argument("--analyze", action="store_true")
    ap.add_argument("--patient-email")
    args = ap.parse_args()

    password = os.environ.get("DEMO_DOCTOR_PASSWORD") or getpass.getpass(f"Пароль лікаря {args.email}: ")
    photos = pick_photos(args.images, args.metadata)
    c = httpx.Client(base_url=args.base_url.rstrip("/") + "/api/v1", timeout=60)
    r = c.post("/auth/login", json={"email": args.email, "password": password})
    if r.status_code == 200 and r.json().get("status") == "confirmation_required":
        link = input(f"Посилання для входу надіслано на {r.json()['emailMasked']}. Вставте його сюди: ").strip()
        token = link.split("token=", 1)[-1].split("&", 1)[0]
        r = c.post("/auth/login/confirm", json={"token": token})
    if r.status_code != 200:
        sys.exit(f"Не вдалося увійти: {r.status_code} {r.json().get('error', {}).get('message', '')}")
    if r.json()["role"] != "Doctor":
        sys.exit("Це не обліковий запис лікаря")
    c.headers["X-CSRF-Token"] = c.cookies["dl_csrf"]

    existing = {
        (p["lastName"], p["firstName"], p["dateOfBirth"])
        for p in c.get("/patients", params={"pageSize": 100}).json()["items"]
    }
    created = 0
    for i, (first, last, middle, dob, phone, dx) in enumerate(PATIENTS):
        location, description = TEXTS[dx].location, TEXTS[dx].description
        if (last, first, dob) in existing:
            print(f"  пропущено (вже є): {last} {first} {middle}")
            continue
        p = c.post(
            "/patients",
            json={
                "firstName": first,
                "lastName": last,
                "middleName": middle,
                "dateOfBirth": dob,
                "email": args.patient_email,
                "phone": phone,
                "notes": "Вигаданий демо-пацієнт (scripts/seed_demo.py)",
            },
        )
        p.raise_for_status()
        examined = (date.today() - timedelta(days=i)).isoformat()
        case = c.post(
            "/cases",
            json={
                "patientId": p.json()["id"],
                "examinedAt": examined,
                "bodyLocation": location,
                "clinicalDescription": description,
            },
        )
        case.raise_for_status()
        photo = photos.get(dx) or args.images / DEFAULT_PHOTO
        with photo.open("rb") as f:
            up = c.post(f"/cases/{case.json()['id']}/images", files={"file": (photo.name, f, "image/jpeg")})
        up.raise_for_status()
        line = f"  {last} {first} {middle}: випадок «{location}», фото {photo.name} (HAM10000: {dx})"
        if args.analyze:
            a = c.post(f"/cases/{case.json()['id']}/analyses")
            if a.status_code != 202:
                line += f"; AI недоступний ({a.json()['error']['code']})"
            else:
                for _ in range(120):
                    a = c.get(f"/analyses/{a.json()['id']}")
                    if a.json()["status"] in ("Completed", "Failed"):
                        break
                    time.sleep(0.5)
                res = a.json()
                line += f"; AI: {res['predictedClass']['code'] if res['predictedClass'] else res['status']}"
        print(line)
        created += 1
    print(f"Створено пацієнтів із випадками: {created}")
    c.post("/auth/logout")
    return 0


if __name__ == "__main__":
    sys.exit(main())
