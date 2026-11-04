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
from ..models import EmailDigest, GoogleAccount, Reminder, Task, TaskStatus, User
from ..timeutil import local_tz, now_utc, to_local_str
from . import gmail

log = logging.getLogger(__name__)
DIGEST_HOUR = 8  # 8 giờ sáng giờ Việt Nam: nhắc các email cần trả lời


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
    daily_email_digests(now)
    return fired


def daily_email_digests(now=None) -> int:
    """Mỗi ngày sau DIGEST_HOUR, với người đã kết nối Gmail: tạo việc và một nhắc nhở có số email cần trả lời."""
    now = now or now_utc()
    local = now.astimezone(local_tz())
    if local.hour < DIGEST_HOUR:
        return 0
    today = local.strftime("%Y-%m-%d")
    sent = 0
    with SessionLocal() as db:
        for acc in list(db.scalars(select(GoogleAccount).where(GoogleAccount.sync_enabled.is_(True)))):
            done = db.get(EmailDigest, acc.user_id)
            if done and done.day == today:
                continue
            try:
                user = db.get(User, acc.user_id)
                items = [i for i in gmail.list_inbox(db, user.id) if i["category"] == "needs_reply"]
                gmail.make_tasks(db, user, items)
                if items:
                    names = "; ".join(i["subject"] for i in items[:3])
                    db.add(Reminder(user_id=user.id, remind_at=now,
                                    message=f"Sáng nay có {len(items)} email cần trả lời: {names}"))
                    sent += 1
            except Exception:  # một người lỗi (vd. chưa cấp quyền đọc email) không làm dừng những người khác
                log.warning("Nhắc email hằng ngày lỗi cho user %s", acc.user_id, exc_info=True)
                db.rollback()
            db.merge(EmailDigest(user_id=acc.user_id, day=today))
            db.commit()
    return sent


async def reminder_loop() -> None:
    interval = get_settings().reminder_poll_seconds
    while True:
        try:
            await asyncio.to_thread(run_once)
        except Exception:  # không để worker chết vì một lỗi tạm thời
            log.exception("reminder worker error")
        await asyncio.sleep(interval)
