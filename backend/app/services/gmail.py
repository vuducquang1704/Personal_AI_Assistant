"""Đọc hộp thư đến (chỉ đọc), phân loại email và tạo việc 'Trả lời ...' cho email cần phản hồi.

Phân loại dựa trên quy tắc (không tốn lượt gọi AI):
- Quảng cáo / spam: Gmail đã gắn nhãn CATEGORY_PROMOTIONS hoặc SPAM.
- Thông báo: người gửi kiểu noreply, hoặc nhãn mạng xã hội / cập nhật.
- Cần trả lời: tiêu đề hoặc nội dung đầu thư có dấu hỏi, hoặc các cụm đề nghị phản hồi.
- Đọc sau: phần còn lại.
"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import EmailTask, Priority, Task, User
from ..timeutil import local_tz
from . import google_calendar as gc
from . import task_service as ts

GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
LABELS = {"needs_reply": "Cần trả lời", "notice": "Thông báo", "promo": "Quảng cáo", "read_later": "Đọc sau"}
NOREPLY = ("noreply", "no-reply", "donotreply", "do-not-reply", "mailer-daemon", "notification")
REPLY_CUES = ("?", "vui lòng", "xin vui", "cho mình biết", "cho tôi biết", "phản hồi", "trả lời",
              "xác nhận", "bạn có thể", "bạn có", "please", "could you", "can you", "let me know",
              "reply", "confirm", "feedback")
DUE_HOUR = 17  # việc "trả lời email" có hạn 17:00 cùng ngày


def classify(labels: list[str], sender: str, subject: str, snippet: str) -> str:
    if "CATEGORY_PROMOTIONS" in labels or "SPAM" in labels:
        return "promo"
    if any(n in sender.lower() for n in NOREPLY) or "CATEGORY_SOCIAL" in labels or "CATEGORY_UPDATES" in labels:
        return "notice"
    text = f"{subject} {snippet}".lower()
    if any(c in text for c in REPLY_CUES):
        return "needs_reply"
    return "read_later"


def _check(r) -> None:
    if r.status_code == 403:
        raise gc.GoogleError("Chưa có quyền đọc email. Hãy ngắt kết nối rồi kết nối lại Google và tick quyền đọc email")
    if r.status_code != 200:
        raise gc.GoogleError(f"Không đọc được email từ Gmail ({r.status_code})")


def list_inbox(db: Session, user_id: int, limit: int = 25) -> list[dict]:
    """Email chưa đọc trong 3 ngày gần đây, đã phân loại."""
    def work(http, token):
        h = {"Authorization": f"Bearer {token}"}
        r = http.get(GMAIL, params={"q": "in:inbox is:unread newer_than:3d", "maxResults": limit}, headers=h)
        _check(r)
        out = []
        for m in r.json().get("messages", []):
            r2 = http.get(f"{GMAIL}/{m['id']}", headers=h, params=[
                ("format", "metadata"), ("metadataHeaders", "From"),
                ("metadataHeaders", "Subject"), ("metadataHeaders", "Date")])
            _check(r2)
            data = r2.json()
            headers = {x["name"].lower(): x["value"] for x in data.get("payload", {}).get("headers", [])}
            sender = headers.get("from", "")
            subject = headers.get("subject") or "(không có tiêu đề)"
            snippet = data.get("snippet", "")
            out.append({
                "id": m["id"], "from": sender, "subject": subject, "snippet": snippet[:200],
                "date": headers.get("date"), "category": classify(data.get("labelIds", []), sender, subject, snippet),
            })
        return out

    return gc.call_google(db, user_id, work)


def make_tasks(db: Session, user: User, items: list[dict]) -> list[Task]:
    """Tạo việc 'Trả lời: <tiêu đề>' hạn 17:00 hôm nay cho các email cần trả lời chưa có việc."""
    due = datetime.now(local_tz()).replace(hour=DUE_HOUR, minute=0, second=0, microsecond=0, tzinfo=None)
    created = []
    for it in items:
        if it["category"] != "needs_reply":
            continue
        if db.scalar(select(EmailTask.id).where(EmailTask.message_id == it["id"])):
            continue
        task = ts.create_task(db, user, title=f"Trả lời: {it['subject']}"[:180],
                              description=f"Từ: {it['from']}\n{it['snippet']}", due_at=due,
                              priority=Priority.medium)
        db.add(EmailTask(user_id=user.id, message_id=it["id"], task_id=task.id))
        db.commit()
        created.append(task)
    return created
