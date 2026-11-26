"""Request/response schemas with validation.

Validation lives here so the API rejects bad data before it touches the
database: enums as Literals, ranges on semester/experience, real e-mail
addresses, and phone numbers restricted to a sane character set.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

T = TypeVar("T")

GENDERS = Literal["male", "female", "other"]
STUDENT_STATUS = Literal["active", "inactive", "graduated", "suspended", "dropped"]
FACULTY_STATUS = Literal["active", "on_leave", "retired", "resigned"]
ATTENDANCE_STATUS = Literal["present", "absent", "late", "excused"]
ROLES = Literal["admin", "faculty", "staff"]
PHONE_RE = r"^[0-9+()\-\s]{6,24}$"


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


# --------------------------------------------------------------------------- #
# Auth / users
# --------------------------------------------------------------------------- #
class LoginRequest(BaseModel):
    username: str = Field(min_length=2, max_length=190)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserOut"


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def strong(cls, v: str) -> str:
        if not any(c.isdigit() for c in v) or not any(c.isalpha() for c in v):
            raise ValueError("Password must contain both letters and numbers")
        return v


class UserBase(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9._-]+$")
    full_name: str = Field(min_length=2, max_length=160)
    role: ROLES = "staff"
    faculty_id: int | None = None
    is_active: bool = True


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, max_length=160)
    role: ROLES | None = None
    is_active: bool | None = None
    faculty_id: int | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    username: str
    full_name: str
    role: str
    is_active: bool
    must_change_password: bool
    faculty_id: int | None = None
    last_login: datetime | None = None
    created_at: datetime


# --------------------------------------------------------------------------- #
# Departments / courses
# --------------------------------------------------------------------------- #
class DepartmentBase(BaseModel):
    code: str = Field(min_length=2, max_length=20)
    name: str = Field(min_length=2, max_length=160)
    hod_name: str | None = Field(default=None, max_length=160)
    description: str | None = None


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=2, max_length=20)
    name: str | None = Field(default=None, min_length=2, max_length=160)
    hod_name: str | None = None
    description: str | None = None


class DepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    hod_name: str | None = None
    description: str | None = None
    created_at: datetime
    student_count: int = 0
    faculty_count: int = 0
    course_count: int = 0


class CourseBase(BaseModel):
    code: str = Field(min_length=2, max_length=24)
    name: str = Field(min_length=2, max_length=160)
    department_id: int
    duration_years: int = Field(default=4, ge=1, le=8)
    level: str = Field(default="Undergraduate", max_length=32)
    total_seats: int | None = Field(default=None, ge=0)


class CourseCreate(CourseBase):
    pass


class CourseUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=2, max_length=24)
    name: str | None = Field(default=None, min_length=2, max_length=160)
    department_id: int | None = None
    duration_years: int | None = Field(default=None, ge=1, le=8)
    level: str | None = None
    total_seats: int | None = Field(default=None, ge=0)


class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    department_id: int
    department_name: str | None = None
    duration_years: int
    level: str
    total_seats: int | None = None
    student_count: int = 0


# --------------------------------------------------------------------------- #
# Students
# --------------------------------------------------------------------------- #
class StudentBase(BaseModel):
    student_id: str = Field(min_length=2, max_length=32)
    full_name: str = Field(min_length=2, max_length=160)
    father_name: str | None = Field(default=None, max_length=160)
    mother_name: str | None = Field(default=None, max_length=160)
    date_of_birth: date | None = None
    gender: GENDERS = "other"
    email: EmailStr
    mobile: str | None = Field(default=None, pattern=PHONE_RE)
    address: str | None = None
    department_id: int
    course_id: int | None = None
    semester: int = Field(default=1, ge=1, le=12)
    admission_date: date | None = None
    enrollment_no: str = Field(min_length=2, max_length=40)
    academic_status: STUDENT_STATUS = "active"

    @field_validator("date_of_birth", "admission_date")
    @classmethod
    def not_in_future(cls, v: date | None) -> date | None:
        if v and v > date.today():
            raise ValueError("Date cannot be in the future")
        return v

    @field_validator("student_id", "enrollment_no")
    @classmethod
    def strip_code(cls, v: str) -> str:
        return v.strip().upper()


class StudentCreate(StudentBase):
    pass


class StudentUpdate(BaseModel):
    student_id: str | None = Field(default=None, min_length=2, max_length=32)
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    father_name: str | None = None
    mother_name: str | None = None
    date_of_birth: date | None = None
    gender: GENDERS | None = None
    email: EmailStr | None = None
    mobile: str | None = Field(default=None, pattern=PHONE_RE)
    address: str | None = None
    department_id: int | None = None
    course_id: int | None = None
    semester: int | None = Field(default=None, ge=1, le=12)
    admission_date: date | None = None
    enrollment_no: str | None = Field(default=None, min_length=2, max_length=40)
    academic_status: STUDENT_STATUS | None = None


class StudentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: str
    full_name: str
    father_name: str | None = None
    mother_name: str | None = None
    date_of_birth: date | None = None
    gender: str
    email: str
    mobile: str | None = None
    address: str | None = None
    department_id: int
    department_name: str | None = None
    course_id: int | None = None
    course_name: str | None = None
    semester: int
    admission_date: date | None = None
    enrollment_no: str
    academic_status: str
    created_at: datetime
    updated_at: datetime
    attendance_percentage: float | None = None


# --------------------------------------------------------------------------- #
# Faculty
# --------------------------------------------------------------------------- #
class FacultyBase(BaseModel):
    faculty_id: str = Field(min_length=2, max_length=32)
    full_name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    phone: str | None = Field(default=None, pattern=PHONE_RE)
    department_id: int
    subject: str | None = Field(default=None, max_length=160)
    qualification: str | None = Field(default=None, max_length=160)
    joining_date: date | None = None
    experience_years: int = Field(default=0, ge=0, le=70)
    employment_status: FACULTY_STATUS = "active"
    gender: GENDERS | None = None

    @field_validator("faculty_id")
    @classmethod
    def strip_code(cls, v: str) -> str:
        return v.strip().upper()


class FacultyCreate(FacultyBase):
    pass


class FacultyUpdate(BaseModel):
    faculty_id: str | None = Field(default=None, min_length=2, max_length=32)
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, pattern=PHONE_RE)
    department_id: int | None = None
    subject: str | None = None
    qualification: str | None = None
    joining_date: date | None = None
    experience_years: int | None = Field(default=None, ge=0, le=70)
    employment_status: FACULTY_STATUS | None = None
    gender: GENDERS | None = None


class FacultyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    faculty_id: str
    full_name: str
    email: str
    phone: str | None = None
    department_id: int
    department_name: str | None = None
    subject: str | None = None
    qualification: str | None = None
    joining_date: date | None = None
    experience_years: int
    employment_status: str
    gender: str | None = None
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Attendance
# --------------------------------------------------------------------------- #
class AttendanceRecord(BaseModel):
    person_id: int
    status: ATTENDANCE_STATUS


class AttendanceBulkRequest(BaseModel):
    person_type: Literal["student", "faculty"]
    date: date
    records: list[AttendanceRecord] = Field(min_length=1, max_length=5000)

    @field_validator("date")
    @classmethod
    def no_future(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("Attendance cannot be marked for a future date")
        return v


class AttendanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    person_type: str
    student_id: int | None = None
    faculty_id: int | None = None
    person_name: str | None = None
    person_code: str | None = None
    date: date
    status: str
    note: str | None = None
    created_at: datetime


class MonthlyAttendanceRow(BaseModel):
    person_id: int
    person_code: str
    person_name: str
    department: str | None = None
    present: int = 0
    absent: int = 0
    late: int = 0
    excused: int = 0
    total: int = 0
    percentage: float = 0.0


# --------------------------------------------------------------------------- #
# Dashboard / activity / system
# --------------------------------------------------------------------------- #
class DashboardStats(BaseModel):
    total_students: int
    total_faculty: int
    total_departments: int
    total_courses: int
    active_students: int
    today_attendance_percentage: float | None = None
    attendance_marked_today: int = 0
    today_present: int = 0
    today_absent: int = 0
    recent_students: list[StudentOut]
    recent_updates: list[dict] = []
    recent_activity: list["ActivityOut"]
    students_by_department: list[dict]
    faculty_by_department: list[dict]
    admissions_by_month: list[dict]
    gender_split: list[dict]
    semester_split: list[dict]
    attendance_trend: list[dict]


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_email: str | None = None
    action: str
    entity: str
    entity_id: str | None = None
    detail: str | None = None
    ip: str | None = None
    created_at: datetime


class BackupOut(BaseModel):
    name: str
    size: int
    created_at: datetime


class MessageResponse(BaseModel):
    detail: str


TokenResponse.model_rebuild()
DashboardStats.model_rebuild()
