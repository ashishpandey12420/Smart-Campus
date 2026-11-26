"""Departments and courses (reference data used by students, faculty, dashboard)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Course, Department, Faculty, Student, User
from ..schemas import (
    CourseCreate,
    CourseOut,
    CourseUpdate,
    DepartmentCreate,
    DepartmentOut,
    DepartmentUpdate,
)
from ..security import get_current_user, require_roles
from ..services.audit import log_activity

router = APIRouter(tags=["reference"])


# --------------------------------------------------------------------------- #
# Departments
# --------------------------------------------------------------------------- #
@router.get("/departments", response_model=list[DepartmentOut])
def list_departments(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.scalars(select(Department).order_by(Department.name)).all()
    s_counts = {k: v for k, v in db.execute(select(Student.department_id, func.count()).group_by(Student.department_id)).all()}
    f_counts = {k: v for k, v in db.execute(select(Faculty.department_id, func.count()).group_by(Faculty.department_id)).all()}
    c_counts = {k: v for k, v in db.execute(select(Course.department_id, func.count()).group_by(Course.department_id)).all()}
    out = []
    for d in rows:
        item = DepartmentOut.model_validate(d)
        item.student_count = s_counts.get(d.id, 0)
        item.faculty_count = f_counts.get(d.id, 0)
        item.course_count = c_counts.get(d.id, 0)
        out.append(item)
    return out


@router.post("/departments", response_model=DepartmentOut, status_code=201)
def create_department(
    payload: DepartmentCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "staff")),
):
    dept = Department(**payload.model_dump())
    db.add(dept)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "A department with this code or name already exists")
    log_activity(db, user, "create", "department", dept.id, f"{dept.code} {dept.name}", request)
    db.commit()
    db.refresh(dept)
    return DepartmentOut.model_validate(dept)


@router.put("/departments/{dept_id}", response_model=DepartmentOut)
def update_department(
    dept_id: int,
    payload: DepartmentUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "staff")),
):
    dept = db.get(Department, dept_id)
    if not dept:
        raise HTTPException(404, "Department not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(dept, k, v)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Another department already uses this code or name")
    log_activity(db, user, "update", "department", dept.id, dept.name, request)
    db.commit()
    db.refresh(dept)
    return DepartmentOut.model_validate(dept)


@router.delete("/departments/{dept_id}")
def delete_department(
    dept_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    dept = db.get(Department, dept_id)
    if not dept:
        raise HTTPException(404, "Department not found")
    in_use = db.scalar(select(func.count(Student.id)).where(Student.department_id == dept_id)) or 0
    in_use += db.scalar(select(func.count(Faculty.id)).where(Faculty.department_id == dept_id)) or 0
    in_use += db.scalar(select(func.count(Course.id)).where(Course.department_id == dept_id)) or 0
    if in_use:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Department still has {in_use} linked record(s). Reassign them first.",
        )
    log_activity(db, user, "delete", "department", dept_id, dept.name, request)
    db.delete(dept)
    db.commit()
    return {"detail": "Department deleted"}


# --------------------------------------------------------------------------- #
# Courses
# --------------------------------------------------------------------------- #
@router.get("/courses", response_model=list[CourseOut])
def list_courses(
    department_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Course).order_by(Course.name)
    if department_id:
        stmt = stmt.where(Course.department_id == department_id)
    rows = db.scalars(stmt).all()
    counts = {k: v for k, v in db.execute(select(Student.course_id, func.count()).group_by(Student.course_id)).all()}
    depts = {d.id: d.name for d in db.scalars(select(Department)).all()}
    out = []
    for c in rows:
        item = CourseOut.model_validate(c)
        item.department_name = depts.get(c.department_id)
        item.student_count = counts.get(c.id, 0)
        out.append(item)
    return out


@router.post("/courses", response_model=CourseOut, status_code=201)
def create_course(
    payload: CourseCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "staff")),
):
    if not db.get(Department, payload.department_id):
        raise HTTPException(400, "Department does not exist")
    course = Course(**payload.model_dump())
    db.add(course)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "A course with this code already exists")
    log_activity(db, user, "create", "course", course.id, f"{course.code} {course.name}", request)
    db.commit()
    db.refresh(course)
    return CourseOut.model_validate(course)


@router.put("/courses/{course_id}", response_model=CourseOut)
def update_course(
    course_id: int,
    payload: CourseUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "staff")),
):
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(404, "Course not found")
    data = payload.model_dump(exclude_unset=True)
    if data.get("department_id") and not db.get(Department, data["department_id"]):
        raise HTTPException(400, "Department does not exist")
    for k, v in data.items():
        setattr(course, k, v)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Another course already uses this code")
    log_activity(db, user, "update", "course", course.id, course.name, request)
    db.commit()
    db.refresh(course)
    return CourseOut.model_validate(course)


@router.delete("/courses/{course_id}")
def delete_course(
    course_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(404, "Course not found")
    in_use = db.scalar(select(func.count(Student.id)).where(Student.course_id == course_id)) or 0
    if in_use:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{in_use} student(s) are enrolled in this course")
    log_activity(db, user, "delete", "course", course_id, course.name, request)
    db.delete(course)
    db.commit()
    return {"detail": "Course deleted"}
