"""Nghiệp vụ quản lý công việc, dùng chung cho REST API và cho công cụ (tool) của trợ lý AI."""
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models import Priority, Reminder, Task, TaskStatus, User
from ..timeutil import as_utc, from_db, local_tz, now_utc
from . import google_calendar as gc


def get_task(db: Session, user: User, task_id: int) -> Task | None:
    task = db.get(Task, task_id)
    return task if task and task.user_id == user.id else None


def create_task(db: Session, user: User, *, title: str, description: str | None = None,
                due_at: datetime | None = None, priority: Priority = Priority.medium,
                status: TaskStatus = TaskStatus.todo) -> Task:
    task = Task(user_id=user.id, title=title.strip(), description=description, due_at=as_utc(due_at),
                priority=priority, status=status)
    if status == TaskStatus.done:
        task.completed_at = now_utc()
    db.add(task)
    db.commit()
    db.refresh(task)
    gc.sync_task(db, task)
    return task


def update_task(db: Session, task: Task, **fields) -> Task:
    for key, value in fields.items():
        if key == "due_at":
            value = as_utc(value)
        if key == "status" and value is not None:
            value = TaskStatus(value)
            if value == TaskStatus.done and task.status != TaskStatus.done:
                task.completed_at = now_utc()
            elif value != TaskStatus.done:
                task.completed_at = None
        if key == "priority" and value is not None:
            value = Priority(value)
        setattr(task, key, value)
    db.commit()
    db.refresh(task)
    if fields.keys() & {"title", "description", "due_at", "priority", "status"}:
        gc.sync_task(db, task)
    return task


def delete_task(db: Session, task: Task) -> None:
    gc.unsync_task(db, task)
    gc.forget_task(db, task)  # nếu Google lỗi, bỏ liên kết; sự kiện cũ vẫn nằm trên lịch
    db.delete(task)
    db.commit()


def list_tasks(db: Session, user: User, *, status: str | None = None, priority: str | None = None,
               due_from: datetime | None = None, due_to: datetime | None = None,
               search: str | None = None, overdue: bool = False, limit: int = 100) -> list[Task]:
    q = select(Task).where(Task.user_id == user.id)
    if status:
        q = q.where(Task.status == TaskStatus(status))
    if priority:
        q = q.where(Task.priority == Priority(priority))
    if due_from:
        q = q.where(Task.due_at >= as_utc(due_from))
    if due_to:
        q = q.where(Task.due_at <= as_utc(due_to))
    if overdue:
        q = q.where(Task.due_at < now_utc(), Task.status != TaskStatus.done)
    if search:
        like = f"%{search.strip()}%"
        q = q.where(or_(Task.title.ilike(like), Task.description.ilike(like)))
    # Việc chưa xong lên trước, rồi theo hạn gần nhất
    q = q.order_by((Task.status == TaskStatus.done), Task.due_at.is_(None), Task.due_at, Task.id.desc())
    return list(db.scalars(q.limit(limit)))


def create_reminder(db: Session, user: User, *, message: str, remind_at: datetime,
                    task_id: int | None = None) -> Reminder:
    r = Reminder(user_id=user.id, task_id=task_id, message=message, remind_at=as_utc(remind_at))
    db.add(r)
    db.commit()
    db.refresh(r)
    gc.sync_reminder(db, r)
    return r


def stats(db: Session, user: User) -> dict:
    tz = local_tz()
    now = now_utc()
    today_local = now.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today_local + timedelta(days=1)
    week_end = today_local + timedelta(days=7)

    tasks = list(db.scalars(select(Task).where(Task.user_id == user.id)))
    open_tasks = [t for t in tasks if t.status != TaskStatus.done]

    def due(t):
        return from_db(t.due_at)

    total = len(tasks)
    done = sum(t.status == TaskStatus.done for t in tasks)
    by_day = []
    for i in range(6, -1, -1):
        start = today_local - timedelta(days=i)
        end = start + timedelta(days=1)
        n = sum(1 for t in tasks if t.completed_at and start <= from_db(t.completed_at) < end)
        by_day.append({"date": start.strftime("%Y-%m-%d"), "count": n})

    return {
        "total": total,
        "todo": sum(t.status == TaskStatus.todo for t in tasks),
        "in_progress": sum(t.status == TaskStatus.in_progress for t in tasks),
        "done": done,
        "overdue": sum(1 for t in open_tasks if due(t) and due(t) < now),
        "due_today": sum(1 for t in open_tasks if due(t) and today_local <= due(t) < tomorrow),
        "due_this_week": sum(1 for t in open_tasks if due(t) and now <= due(t) < week_end),
        "by_priority": {p.value: sum(t.priority == p for t in open_tasks) for p in Priority},
        "completion_rate": round(done / total, 3) if total else 0.0,
        "completed_last_7_days": by_day,
    }


def count_tasks(db: Session, user: User) -> int:
    return db.scalar(select(func.count()).select_from(Task).where(Task.user_id == user.id)) or 0
