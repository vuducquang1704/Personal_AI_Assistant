"""Tiến trình nền: kiểm tra định kỳ các nhắc nhở đến hạn và đánh dấu đã kích hoạt.

Frontend hỏi /api/reminders/due để hiển thị thông báo (và đọc to bằng giọng nói).
Ngoài nhắc nhở người dùng đặt, worker tự tạo nhắc nhở cho công việc sắp đến hạn trong 1 giờ tới.
"""
import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select

from ..config import get_settings
from ..db import SessionLocal
from ..models import Reminder, Task, TaskStatus
from ..timeutil import now_utc, to_local_str

log = logging.getLogger(__name__)


def run_once() -> int:
    now = now_utc()
    fired = 0
    with SessionLocal() as db:
        # 1) Tự tạo nhắc nhở cho công việc sắp đến hạn (trong 60 phút) nếu chưa có
        soon = db.scalars(
            select(Task).where(
                Task.status != TaskStatus.done,
                Task.due_at.is_not(None),
                Task.due_at > now,
                Task.due_at <= now + timedelta(minutes=60),
            )
        )
        for task in soon:
            exists = db.scalar(select(Reminder.id).where(Reminder.task_id == task.id,
                                                        Reminder.message.like("[auto]%")))
            if not exists:
                db.add(Reminder(user_id=task.user_id, task_id=task.id, remind_at=now,
                                message=f"[auto] Công việc \"{task.title}\" sắp đến hạn lúc {to_local_str(task.due_at)}"))
        db.commit()

        # 2) Kích hoạt các nhắc nhở đã đến giờ
        due = db.scalars(select(Reminder).where(Reminder.fired_at.is_(None), Reminder.remind_at <= now))
        for r in due:
            r.fired_at = now
            fired += 1
        db.commit()
    return fired


async def reminder_loop() -> None:
    interval = get_settings().reminder_poll_seconds
    while True:
        try:
            await asyncio.to_thread(run_once)
        except Exception:  # không để worker chết vì một lỗi tạm thời
            log.exception("reminder worker error")
        await asyncio.sleep(interval)
