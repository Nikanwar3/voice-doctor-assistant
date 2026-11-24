"""Mock clinic data: doctors, slots and appointments, backed by SQLite.

This is intentionally a thin, synchronous data layer. The whole app is a single
small process, so plain sqlite3 calls are simple and fast enough; callers from
async code (the voice pipeline's tool functions) wrap these in asyncio.to_thread
so a slow disk write never blocks the pipeline's event loop. FastAPI route
handlers below are declared as plain `def`, which FastAPI itself off-loads to a
worker thread.
"""

import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "clinic.db"

DOCTORS = [
    ("Dr. Anika Mehta", "Cardiologist"),
    ("Dr. Rohan Shah", "General Physician"),
    ("Dr. Priya Nair", "Dermatologist"),
    ("Dr. Karan Verma", "Pediatrician"),
    ("Dr. Leela Iyer", "Dentist"),
]

SLOT_TIMES = ["09:30", "10:00", "10:30", "11:00", "14:00", "14:30", "15:00", "16:00"]


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS doctors (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                specialty TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS slots (
                id INTEGER PRIMARY KEY,
                doctor_id INTEGER NOT NULL REFERENCES doctors(id),
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'available'
            );
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY,
                slot_id INTEGER NOT NULL REFERENCES slots(id),
                phone_number TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'booked',
                created_at TEXT NOT NULL
            );
            """
        )
        if conn.execute("SELECT COUNT(*) FROM doctors").fetchone()[0] == 0:
            _seed(conn)


def _seed(conn):
    doctor_ids = []
    for name, specialty in DOCTORS:
        cur = conn.execute(
            "INSERT INTO doctors (name, specialty) VALUES (?, ?)", (name, specialty)
        )
        doctor_ids.append(cur.lastrowid)

    today = datetime.now().date()
    for day_offset in range(4):
        date_str = (today + timedelta(days=day_offset)).isoformat()
        for doctor_id in doctor_ids:
            for time in SLOT_TIMES:
                conn.execute(
                    "INSERT INTO slots (doctor_id, date, time, status) VALUES (?, ?, ?, 'available')",
                    (doctor_id, date_str, time),
                )

    # Pre-book a few slots so availability looks realistic, not empty.
    demo_bookings = [
        (doctor_ids[0], today.isoformat(), "10:00", "9876543210"),
        (doctor_ids[1], today.isoformat(), "14:00", "9123456780"),
        (doctor_ids[3], (today + timedelta(days=1)).isoformat(), "09:30", "9988776655"),
    ]
    for doctor_id, date_str, time, phone in demo_bookings:
        row = conn.execute(
            "SELECT id FROM slots WHERE doctor_id = ? AND date = ? AND time = ?",
            (doctor_id, date_str, time),
        ).fetchone()
        if row:
            conn.execute("UPDATE slots SET status = 'booked' WHERE id = ?", (row["id"],))
            conn.execute(
                "INSERT INTO appointments (slot_id, phone_number, status, created_at) "
                "VALUES (?, ?, 'booked', ?)",
                (row["id"], phone, datetime.now().isoformat()),
            )


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) > 10:
        digits = digits[-10:]
    return digits


def normalize_date(raw: str) -> str:
    text = (raw or "").strip().lower()
    today = datetime.now().date()
    if text in ("", "any", "anytime", "any date"):
        return "any"
    if text == "today":
        return today.isoformat()
    if text == "tomorrow":
        return (today + timedelta(days=1)).isoformat()
    try:
        datetime.strptime(text, "%Y-%m-%d")
        return text
    except ValueError:
        return text  # let the query simply find nothing; caller surfaces that


def _doctor_matches(query: str, name: str, specialty: str) -> bool:
    q = query.strip().lower()
    if q in ("", "any", "anyone", "any doctor"):
        return True
    q = re.sub(r"^(dr\.?|doctor)\s*", "", q).strip()
    name_norm = re.sub(r"^(dr\.?|doctor)\s*", "", name.lower())
    return q in name_norm or q in specialty.lower()


def list_doctors():
    with _conn() as conn:
        rows = conn.execute("SELECT id, name, specialty FROM doctors ORDER BY name").fetchall()
        return [dict(r) for r in rows]


def find_matching_doctors(doctor_query: str):
    with _conn() as conn:
        rows = conn.execute("SELECT id, name, specialty FROM doctors").fetchall()
        return [dict(r) for r in rows if _doctor_matches(doctor_query, r["name"], r["specialty"])]


def list_available_slots(doctor_query: str, date_query: str):
    """Returns available slots across doctors that match doctor_query/date_query."""
    date_norm = normalize_date(date_query)
    today = datetime.now().date().isoformat()

    doctors = find_matching_doctors(doctor_query)
    if not doctors:
        return []

    with _conn() as conn:
        results = []
        for doc in doctors:
            query = (
                "SELECT date, time FROM slots "
                "WHERE doctor_id = ? AND status = 'available' AND date >= ? "
            )
            params = [doc["id"], today]
            if date_norm != "any":
                query += "AND date = ? "
                params.append(date_norm)
            query += "ORDER BY date, time"
            slots = conn.execute(query, params).fetchall()
            if slots:
                results.append(
                    {
                        "doctor_name": doc["name"],
                        "specialty": doc["specialty"],
                        "slots": [{"date": s["date"], "time": s["time"]} for s in slots],
                    }
                )
        return results


def book_slot(doctor_query: str, date_str: str, time_str: str, phone_number: str):
    phone = normalize_phone(phone_number)
    if len(phone) != 10:
        return {"ok": False, "error": "invalid_phone_number"}

    doctors = find_matching_doctors(doctor_query)
    if not doctors:
        return {"ok": False, "error": "doctor_not_found"}
    if len(doctors) > 1:
        return {
            "ok": False,
            "error": "ambiguous_doctor",
            "matches": [d["name"] for d in doctors],
        }
    doctor = doctors[0]

    with _conn() as conn:
        slot = conn.execute(
            "SELECT id FROM slots WHERE doctor_id = ? AND date = ? AND time = ? AND status = 'available'",
            (doctor["id"], date_str, time_str),
        ).fetchone()
        if not slot:
            return {"ok": False, "error": "slot_unavailable"}

        conn.execute("UPDATE slots SET status = 'booked' WHERE id = ?", (slot["id"],))
        conn.execute(
            "INSERT INTO appointments (slot_id, phone_number, status, created_at) "
            "VALUES (?, ?, 'booked', ?)",
            (slot["id"], phone, datetime.now().isoformat()),
        )
        return {
            "ok": True,
            "doctor_name": doctor["name"],
            "specialty": doctor["specialty"],
            "date": date_str,
            "time": time_str,
            "phone_number": phone,
        }


def cancel_by_phone(phone_number: str, date_query: str = "any"):
    phone = normalize_phone(phone_number)
    date_norm = normalize_date(date_query)

    with _conn() as conn:
        query = (
            "SELECT a.id as appointment_id, s.id as slot_id, s.date, s.time, "
            "d.name as doctor_name, d.specialty "
            "FROM appointments a "
            "JOIN slots s ON s.id = a.slot_id "
            "JOIN doctors d ON d.id = s.doctor_id "
            "WHERE a.phone_number = ? AND a.status = 'booked' "
        )
        params = [phone]
        if date_norm != "any":
            query += "AND s.date = ? "
            params.append(date_norm)
        query += "ORDER BY s.date, s.time"

        matches = conn.execute(query, params).fetchall()
        if not matches:
            return {"ok": False, "error": "not_found"}

        target = matches[0]
        conn.execute(
            "UPDATE appointments SET status = 'cancelled' WHERE id = ?",
            (target["appointment_id"],),
        )
        conn.execute(
            "UPDATE slots SET status = 'available' WHERE id = ?", (target["slot_id"],)
        )
        return {
            "ok": True,
            "doctor_name": target["doctor_name"],
            "specialty": target["specialty"],
            "date": target["date"],
            "time": target["time"],
            "phone_number": phone,
            "other_appointments_remaining": len(matches) - 1,
        }


def list_appointments():
    with _conn() as conn:
        rows = conn.execute(
            "SELECT a.id, a.phone_number, a.status, a.created_at, "
            "s.date, s.time, d.name as doctor_name, d.specialty "
            "FROM appointments a "
            "JOIN slots s ON s.id = a.slot_id "
            "JOIN doctors d ON d.id = s.doctor_id "
            "ORDER BY a.created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
