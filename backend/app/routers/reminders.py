from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Reminder, User
from ..schemas import ReminderIn, ReminderOut
from ..security import get_current_user
from ..services import google_calendar as gc
from ..services import task_service as ts

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


@router.get("", response_model=list[ReminderOut])
def list_reminders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return list(db.scalars(select(Reminder).where(Reminder.user_id == user.id).order_by(Reminder.remind_at.desc())))


@router.post("", response_model=ReminderOut, status_code=201)
def create(body: ReminderIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.task_id is not None and not ts.get_task(db, user, body.task_id):
        raise HTTPException(404, "Không tìm thấy công việc")
    return ts.create_reminder(db, user, **body.model_dump())


@router.get("/due", response_model=list[ReminderOut])
def due(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Nhắc nhở đã kích hoạt nhưng người dùng chưa xem; frontend hỏi định kỳ."""
    return list(db.scalars(select(Reminder).where(Reminder.user_id == user.id, Reminder.fired_at.is_not(None),
                                                  Reminder.seen.is_(False)).order_by(Reminder.remind_at)))


@router.post("/{reminder_id}/seen", status_code=204)
def mark_seen(reminder_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = db.get(Reminder, reminder_id)
    if not r or r.user_id != user.id:
        raise HTTPException(404, "Không tìm thấy nhắc nhở")
    r.seen = True
    db.commit()


@router.delete("/{reminder_id}", status_code=204)
def delete(reminder_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = db.get(Reminder, reminder_id)
    if not r or r.user_id != user.id:
        raise HTTPException(404, "Không tìm thấy nhắc nhở")
    gc.unsync_reminder(db, r)
    gc.forget_reminder(db, r)
    db.delete(r)
    db.commit()
