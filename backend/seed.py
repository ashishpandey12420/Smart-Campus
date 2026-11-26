"""Seed reference data + first administrator, and an optional demo-data generator.

Reference data (departments, courses) and the administrator account are created
on first boot. Student/faculty records are NEVER invented automatically — the
demo generator below is opt-in and clearly labelled, so a real deployment never
starts with fake student data.
"""
from __future__ import annotations

import argparse
import random
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import (
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_PASSWORD,
    DEFAULT_ADMIN_USERNAME,
)
from .database import Base, SessionLocal, engine
from .models import Attendance, Course, Department, Faculty, Student, User
from .security import hash_password

DEPARTMENTS = [
    ("CSE", "Computer Science & Engineering", "Dr. Meera Iyer"),
    ("ECE", "Electronics & Communication", "Dr. Rohit Verma"),
    ("ME", "Mechanical Engineering", "Dr. Anil Kulkarni"),
    ("CE", "Civil Engineering", "Dr. Sana Qureshi"),
    ("EE", "Electrical Engineering", "Dr. Vikram Rao"),
    ("MBA", "School of Management", "Dr. Priya Nair"),
]

COURSES = [
    ("BTECH-CSE", "B.Tech Computer Science", "CSE", 4, "Undergraduate", 180),
    ("MTECH-CSE", "M.Tech Software Engineering", "CSE", 2, "Postgraduate", 60),
    ("BTECH-ECE", "B.Tech Electronics", "ECE", 4, "Undergraduate", 120),
    ("BTECH-ME", "B.Tech Mechanical", "ME", 4, "Undergraduate", 120),
    ("BTECH-CE", "B.Tech Civil", "CE", 4, "Undergraduate", 120),
    ("BTECH-EE", "B.Tech Electrical", "EE", 4, "Undergraduate", 120),
    ("MBA", "Master of Business Administration", "MBA", 2, "Postgraduate", 90),
    ("BBA", "Bachelor of Business Administration", "MBA", 3, "Undergraduate", 90),
]

FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Ayaan",
    "Krishna", "Ishaan", "Ananya", "Diya", "Aadhya", "Saanvi", "Pari", "Anika",
    "Navya", "Myra", "Riya", "Ira", "Kabir", "Rohan", "Nikhil", "Sneha",
    "Pooja", "Meera", "Rahul", "Karan", "Tanvi", "Neha", "Siddharth", "Aisha",
]
LAST_NAMES = [
    "Sharma", "Verma", "Patel", "Reddy", "Nair", "Iyer", "Gupta", "Singh",
    "Khan", "Mehta", "Joshi", "Desai", "Kulkarni", "Bose", "Chopra", "Rao",
]


def seed_initial(db: Session) -> None:
    """Idempotent: reference data + first admin."""
    if db.scalar(select(func.count(Department.id))) == 0:
        for code, name, hod in DEPARTMENTS:
            db.add(Department(code=code, name=name, hod_name=hod))
        db.commit()

    if db.scalar(select(func.count(Course.id))) == 0:
        depts = {d.code: d.id for d in db.scalars(select(Department)).all()}
        for code, name, dept_code, years, level, seats in COURSES:
            if dept_code in depts:
                db.add(
                    Course(
                        code=code,
                        name=name,
                        department_id=depts[dept_code],
                        duration_years=years,
                        level=level,
                        total_seats=seats,
                    )
                )
        db.commit()

    if db.scalar(select(func.count(User.id))) == 0:
        db.add(
            User(
                email=DEFAULT_ADMIN_EMAIL,
                username=DEFAULT_ADMIN_USERNAME,
                full_name="Administrator",
                role="admin",
                password_hash=hash_password(DEFAULT_ADMIN_PASSWORD),
                must_change_password=True,
            )
        )
        db.commit()


def demo_students(db: Session, count: int, *, seed: int = 42, chunk: int = 2000) -> int:
    rng = random.Random(seed)
    depts = db.scalars(select(Department)).all()
    courses = db.scalars(select(Course)).all()
    if not depts or not courses:
        raise SystemExit("Run the app once (or python -m backend.seed --init) first")

    statuses = ["active"] * 8 + ["inactive", "graduated", "suspended"]
    genders = (["male", "female", "other"], [48, 48, 4])
    start_year = 2018
    today = date.today()

    existing = db.scalar(select(func.count(Student.id))) or 0
    made = 0
    while made < count:
        batch = []
        for _ in range(min(chunk, count - made)):
            n = existing + made + len(batch) + 1
            dept = rng.choice(depts)
            course = rng.choice([c for c in courses if c.department_id == dept.id] or courses)
            first = rng.choice(FIRST_NAMES)
            last = rng.choice(LAST_NAMES)
            # Spread admissions over the last ~24 months so the dashboard
            # trend and cohort charts have a realistic shape.
            admission = today - timedelta(days=rng.randint(0, 730))
            year = admission.year
            batch.append(
                {
                    "student_id": f"SC{year}{n:06d}",
                    "full_name": f"{first} {last}",
                    "father_name": f"{rng.choice(FIRST_NAMES)} {last}",
                    "mother_name": f"{rng.choice(FIRST_NAMES)} {last}",
                    "date_of_birth": date(year - 18, rng.randint(1, 12), rng.randint(1, 28)),
                    "gender": rng.choices(genders[0], genders[1])[0],
                    "email": f"student{n}@example.edu",
                    "mobile": f"9{rng.randint(100000000, 999999999)}",
                    "address": f"{rng.randint(1, 200)} {rng.choice(['MG Road', 'Park Street', 'Ring Road', 'Station Road'])}, {rng.choice(['Pune', 'Mumbai', 'Delhi', 'Bengaluru', 'Hyderabad'])}",
                    "department_id": dept.id,
                    "course_id": course.id,
                    "semester": rng.randint(1, max(1, course.duration_years * 2)),
                    "admission_date": admission,
                    "enrollment_no": f"ENR{year}{n:06d}",
                    "academic_status": rng.choice(statuses),
                }
            )
        db.execute(Student.__table__.insert(), batch)
        db.commit()
        made += len(batch)
    return made


def demo_faculty(db: Session, count: int, *, seed: int = 7) -> int:
    rng = random.Random(seed)
    depts = db.scalars(select(Department)).all()
    subjects = ["Data Structures", "Thermodynamics", "Signals", "Finance", "Structures", "Power Systems", "Machine Learning", "Marketing"]
    quals = ["Ph.D.", "M.Tech", "M.Sc.", "MBA", "M.E."]
    existing = db.scalar(select(func.count(Faculty.id))) or 0
    batch = []
    for i in range(count):
        n = existing + i + 1
        dept = rng.choice(depts)
        batch.append(
            {
                "faculty_id": f"FAC{n:05d}",
                "full_name": f"Dr. {rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
                "email": f"faculty{n}@example.edu",
                "phone": f"8{rng.randint(100000000, 999999999)}",
                "department_id": dept.id,
                "subject": rng.choice(subjects),
                "qualification": rng.choice(quals),
                "joining_date": date(rng.randint(2005, 2024), rng.randint(1, 12), rng.randint(1, 28)),
                "experience_years": rng.randint(1, 25),
                "employment_status": rng.choice(["active"] * 8 + ["on_leave", "retired"]),
                "gender": rng.choice(["male", "female"]),
            }
        )
    db.execute(Faculty.__table__.insert(), batch)
    db.commit()
    return len(batch)


def demo_attendance(db: Session, days: int, people: int, *, seed: int = 11) -> int:
    """Attendance for the most recent `days` days for the first `people` students."""
    rng = random.Random(seed)
    student_ids = db.scalars(select(Student.id).order_by(Student.id).limit(people)).all()
    if not student_ids:
        return 0
    rows = []
    for offset in range(days):
        day = date.today() - timedelta(days=offset)
        if day.weekday() == 6:
            continue
        for sid in student_ids:
            rows.append(
                {
                    "person_type": "student",
                    "student_id": sid,
                    "faculty_id": None,
                    "date": day,
                    "status": rng.choices(["present", "absent", "late", "excused"], [80, 12, 5, 3])[0],
                }
            )
    if rows:
        for i in range(0, len(rows), 5000):
            db.execute(Attendance.__table__.insert(), rows[i : i + 5000])
            db.commit()
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Smart Campus database utilities")
    parser.add_argument("--init", action="store_true", help="create tables and reference data only")
    parser.add_argument("--students", type=int, default=0, help="number of demo students to generate")
    parser.add_argument("--faculty", type=int, default=0, help="number of demo faculty to generate")
    parser.add_argument("--attendance-days", type=int, default=0, help="days of demo attendance")
    parser.add_argument("--attendance-people", type=int, default=2000, help="students to include in attendance")
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_initial(db)
        print("Reference data and admin account ready.")
        if args.students:
            print("Warning: demo records are for testing only — never for production.")
            print(f"Inserted {demo_students(db, args.students)} demo students")
        if args.faculty:
            print(f"Inserted {demo_faculty(db, args.faculty)} demo faculty")
        if args.attendance_days:
            print(f"Inserted {demo_attendance(db, args.attendance_days, args.attendance_people)} attendance rows")
    finally:
        db.close()


if __name__ == "__main__":
    main()
