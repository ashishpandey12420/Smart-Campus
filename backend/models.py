"""Relational model.

Indexes are deliberate: every column the UI searches or sorts on is indexed,
every foreign key is indexed, and attendance carries composite indexes on
(person, date) so month reports stay fast at millions of rows.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    hod_name: Mapped[str | None] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    courses: Mapped[list["Course"]] = relationship(back_populates="department")
    students: Mapped[list["Student"]] = relationship(back_populates="department")
    faculty: Mapped[list["Faculty"]] = relationship(back_populates="department")


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(24), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    duration_years: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    level: Mapped[str] = mapped_column(String(32), default="Undergraduate", nullable=False)
    total_seats: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    department: Mapped[Department] = relationship(back_populates="courses")
    students: Mapped[list["Student"]] = relationship(back_populates="course")


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    father_name: Mapped[str | None] = mapped_column(String(160))
    mother_name: Mapped[str | None] = mapped_column(String(160))
    date_of_birth: Mapped[date | None] = mapped_column(Date, index=True)
    gender: Mapped[str] = mapped_column(String(16), default="other", nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(190), unique=True, nullable=False, index=True)
    mobile: Mapped[str | None] = mapped_column(String(24), index=True)
    address: Mapped[str | None] = mapped_column(Text)
    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL"), index=True
    )
    semester: Mapped[int] = mapped_column(Integer, default=1, nullable=False, index=True)
    admission_date: Mapped[date | None] = mapped_column(Date, index=True)
    enrollment_no: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    academic_status: Mapped[str] = mapped_column(
        String(24), default="active", nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False, index=True
    )

    department: Mapped[Department] = relationship(back_populates="students")
    course: Mapped[Course | None] = relationship(back_populates="students")

    __table_args__ = (
        Index("ix_students_dept_semester", "department_id", "semester"),
        Index("ix_students_status_created", "academic_status", "created_at"),
    )


class Faculty(Base):
    __tablename__ = "faculty"

    id: Mapped[int] = mapped_column(primary_key=True)
    faculty_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(190), unique=True, nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(24), index=True)
    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    subject: Mapped[str | None] = mapped_column(String(160), index=True)
    qualification: Mapped[str | None] = mapped_column(String(160))
    joining_date: Mapped[date | None] = mapped_column(Date, index=True)
    experience_years: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    employment_status: Mapped[str] = mapped_column(
        String(24), default="active", nullable=False, index=True
    )
    gender: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False, index=True
    )

    department: Mapped[Department] = relationship(back_populates="faculty")

    __table_args__ = (
        Index("ix_faculty_dept_status", "department_id", "employment_status"),
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(190), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="staff", nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    faculty_id: Mapped[int | None] = mapped_column(
        ForeignKey("faculty.id", ondelete="SET NULL"), index=True
    )
    last_login: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    faculty: Mapped[Faculty | None] = relationship()


class Attendance(Base):
    __tablename__ = "attendance"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    student_id: Mapped[int | None] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True
    )
    faculty_id: Mapped[int | None] = mapped_column(
        ForeignKey("faculty.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(String(255))
    marked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    student: Mapped[Student | None] = relationship()
    faculty: Mapped[Faculty | None] = relationship()

    __table_args__ = (
        # NULLs are distinct in both SQLite and PostgreSQL, so each of these
        # acts as a partial unique index for its own person type.
        UniqueConstraint("student_id", "date", name="uq_attendance_student_date"),
        UniqueConstraint("faculty_id", "date", name="uq_attendance_faculty_date"),
        Index("ix_attendance_date_status", "date", "status"),
        Index("ix_attendance_type_date", "person_type", "date"),
    )


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    user_email: Mapped[str | None] = mapped_column(String(190), index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    entity: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    entity_id: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)

    __table_args__ = (Index("ix_activity_entity_created", "entity", "created_at"),)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=func.now(), nullable=False
    )
