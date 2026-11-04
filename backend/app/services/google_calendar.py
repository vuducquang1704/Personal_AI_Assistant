"""Đồng bộ công việc / nhắc nhở sang Google Calendar qua OAuth 2.0 và Calendar REST API v3.

Mọi thao tác đồng bộ đều "best-effort": nếu Google lỗi hoặc mất mạng thì chỉ ghi log và lưu
`last_error`, không làm hỏng thao tác chính (tạo/sửa/xoá công việc) của người dùng.
"""
import logging
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx
import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..crypto import decrypt, encrypt
from ..models import CalendarEvent, GoogleAccount, Priority, Reminder, Task, TaskStatus, User
from ..timeutil import from_db, local_tz, now_utc

log = logging.getLogger(__name__)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
SCOPES = "openid email https://www.googleapis.com/auth/calendar.events"
EVENT_MINUTES = 30
PRIORITY_LABEL = {Priority.low: "thấp", Priority.medium: "trung bình", Priority.high: "cao"}

# Cho phép test thay bằng httpx.MockTransport
transport: httpx.BaseTransport | None = None


class GoogleError(Exception):
    pass


class GoogleAuthError(GoogleError):
    """Refresh token hết hiệu lực (người dùng thu hồi quyền...) -> cần kết nối lại."""


def enabled() -> bool:
    s = get_settings()
    return bool(s.google_client_id and s.google_client_secret)


def _http() -> httpx.Client:
    return httpx.Client(timeout=8, transport=transport)


# ---------------------------------------------------------------- OAuth

def make_state(user_id: int, nonce: str) -> str:
    # "uid" thay vì "sub" và có "purpose" để không thể dùng làm token đăng nhập
    payload = {"uid": user_id, "nonce": nonce, "purpose": "google-oauth", "exp": now_utc() + timedelta(minutes=10)}
    return jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")


def new_nonce() -> str:
    return secrets.token_urlsafe(24)


def read_state(state: str, nonce: str | None) -> int:
    """Kiểm tra state và so nonce với cookie của trình duyệt đã bắt đầu kết nối (chống CSRF)."""
    try:
        payload = jwt.decode(state, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as e:
        raise GoogleError("Phiên kết nối Google không hợp lệ hoặc đã hết hạn") from e
    if payload.get("purpose") != "google-oauth":
        raise GoogleError("Phiên kết nối Google không hợp lệ")
    if not nonce or not secrets.compare_digest(str(payload.get("nonce", "")), nonce):
        raise GoogleError("Yêu cầu kết nối Google không xuất phát từ trình duyệt này")
    return int(payload["uid"])


def auth_url(user: User, nonce: str) -> str:
    s = get_settings()
    params = {
        "client_id": s.google_client_id,
        "redirect_uri": s.google_redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",  # để nhận refresh token
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": make_state(user.id, nonce),
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def connect(db: Session, user_id: int, code: str) -> GoogleAccount:
    """Đổi authorization code lấy token và lưu kết nối."""
    s = get_settings()
    with _http() as http:
        r = http.post(TOKEN_URL, data={
            "code": code, "client_id": s.google_client_id, "client_secret": s.google_client_secret,
            "redirect_uri": s.google_redirect_uri, "grant_type": "authorization_code",
        })
        if r.status_code != 200:
            raise GoogleError(f"Google từ chối mã xác thực: {r.text[:200]}")
        tok = r.json()
        email = None
        u = http.get(USERINFO_URL, headers={"Authorization": f"Bearer {tok['access_token']}"})
        if u.status_code == 200:
            email = u.json().get("email")

    acc = db.scalar(select(GoogleAccount).where(GoogleAccount.user_id == user_id))
    refresh = tok.get("refresh_token")
    if not refresh and not acc:
        raise GoogleError("Google không trả về refresh token, hãy thử kết nối lại")
    if not acc:
        acc = GoogleAccount(user_id=user_id, refresh_token_enc=encrypt(refresh))
        db.add(acc)
    elif refresh:
        acc.refresh_token_enc = encrypt(refresh)
    acc.email = email or acc.email
    acc.access_token_enc = encrypt(tok["access_token"])
    acc.access_expires_at = now_utc() + timedelta(seconds=int(tok.get("expires_in", 3600)) - 60)
    acc.last_error = None
    db.commit()
    db.refresh(acc)
    return acc


def get_account(db: Session, user_id: int) -> GoogleAccount | None:
    return db.scalar(select(GoogleAccount).where(GoogleAccount.user_id == user_id))


def disconnect(db: Session, user_id: int) -> None:
    """Thu hồi quyền và xoá kết nối. Các sự kiện đã tạo vẫn nằm trên lịch của người dùng."""
    acc = get_account(db, user_id)
    if not acc:
        return
    token = decrypt(acc.refresh_token_enc)
    if token:
        try:
            with _http() as http:
                http.post(REVOKE_URL, data={"token": token})
        except httpx.HTTPError:
            log.warning("Không thu hồi được token Google của user %s", user_id)
    for ev in db.scalars(select(CalendarEvent).where(CalendarEvent.user_id == user_id)):
        db.delete(ev)
    db.delete(acc)
    db.commit()


def _access_token(db: Session, acc: GoogleAccount, http: httpx.Client) -> str:
    if acc.access_token_enc and acc.access_expires_at and from_db(acc.access_expires_at) > now_utc():
        token = decrypt(acc.access_token_enc)
        if token:
            return token
    refresh = decrypt(acc.refresh_token_enc)
    if not refresh:
        raise GoogleAuthError("Không đọc được token đã lưu, hãy kết nối lại Google")
    s = get_settings()
    r = http.post(TOKEN_URL, data={"refresh_token": refresh, "client_id": s.google_client_id,
                                   "client_secret": s.google_client_secret, "grant_type": "refresh_token"})
    if r.status_code in (400, 401):
        raise GoogleAuthError("Quyền truy cập Google đã bị thu hồi hoặc hết hạn, hãy kết nối lại")
    if r.status_code != 200:
        raise GoogleError(f"Không làm mới được token Google ({r.status_code})")
    tok = r.json()
    acc.access_token_enc = encrypt(tok["access_token"])
    acc.access_expires_at = now_utc() + timedelta(seconds=int(tok.get("expires_in", 3600)) - 60)
    db.commit()
    return tok["access_token"]


# ---------------------------------------------------------------- Sự kiện

def _event_body(*, summary: str, description: str, start: datetime, popup_minutes: int,
                color: str | None = None) -> dict:
    tz = get_settings().timezone
    start = from_db(start).astimezone(local_tz())
    end = start + timedelta(minutes=EVENT_MINUTES)
    body = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start.isoformat(), "timeZone": tz},
        "end": {"dateTime": end.isoformat(), "timeZone": tz},
        "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": popup_minutes}]},
        "source": {"title": "Trợ lý AI cá nhân", "url": get_settings().frontend_url},
    }
    if color:
        body["colorId"] = color
    return body


def _task_body(task: Task, acc: GoogleAccount) -> dict:
    lines = []
    if task.description:
        lines.append(task.description)
    lines.append(f"Mức ưu tiên: {PRIORITY_LABEL.get(task.priority, task.priority)}")
    lines.append("Tạo bởi Trợ lý AI cá nhân")
    return _event_body(summary=task.title, description="\n".join(lines), start=task.due_at,
                       popup_minutes=acc.reminder_minutes,
                       color="11" if task.priority == Priority.high else None)  # 11 = đỏ


def _upsert(http: httpx.Client, token: str, event_id: str | None, body: dict) -> str:
    headers = {"Authorization": f"Bearer {token}"}
    if event_id:
        r = http.put(f"{EVENTS_URL}/{event_id}", json=body, headers=headers)
        if r.status_code == 200:
            return event_id
        if r.status_code not in (404, 410):  # sự kiện bị xoá trên lịch thì tạo lại
            raise GoogleError(f"Cập nhật sự kiện lỗi {r.status_code}: {r.text[:200]}")
    r = http.post(EVENTS_URL, json=body, headers=headers)
    if r.status_code not in (200, 201):
        raise GoogleError(f"Tạo sự kiện lỗi {r.status_code}: {r.text[:200]}")
    return r.json()["id"]


def _delete(http: httpx.Client, token: str, event_id: str) -> None:
    r = http.delete(f"{EVENTS_URL}/{event_id}", headers={"Authorization": f"Bearer {token}"})
    if r.status_code not in (200, 204, 404, 410):
        raise GoogleError(f"Xoá sự kiện lỗi {r.status_code}: {r.text[:200]}")


def _run(db: Session, user_id: int, fn) -> bool:
    """Chạy một thao tác đồng bộ nếu người dùng đã kết nối và bật đồng bộ. Không bao giờ ném lỗi."""
    if not enabled():
        return False
    acc = get_account(db, user_id)
    if not acc or not acc.sync_enabled:
        return False
    try:
        with _http() as http:
            token = _access_token(db, acc, http)
            fn(http, token, acc)
        if acc.last_error:
            acc.last_error = None
        db.commit()
        return True
    except (GoogleError, httpx.HTTPError) as e:
        db.rollback()
        log.warning("Đồng bộ Google Calendar thất bại (user %s): %s", user_id, e)
        acc = get_account(db, user_id)
        if acc:
            acc.last_error = str(e)[:500]
            db.commit()
        return False


def _task_link(db: Session, task_id: int) -> CalendarEvent | None:
    return db.scalar(select(CalendarEvent).where(CalendarEvent.task_id == task_id))


def sync_task(db: Session, task: Task) -> bool:
    """Tạo/cập nhật sự kiện cho việc có hạn chót; xoá sự kiện nếu việc đã xong hoặc bỏ hạn."""
    def work(http, token, acc):
        link = _task_link(db, task.id)
        if task.due_at is None or task.status == TaskStatus.done:
            if link:
                _delete(http, token, link.event_id)
                db.delete(link)
            return
        event_id = _upsert(http, token, link.event_id if link else None, _task_body(task, acc))
        if link:
            link.event_id = event_id
        else:
            db.add(CalendarEvent(user_id=task.user_id, task_id=task.id, event_id=event_id))

    return _run(db, task.user_id, work)


def unsync_task(db: Session, task: Task) -> bool:
    """Gọi trước khi xoá công việc."""
    link = _task_link(db, task.id)
    if not link:
        return False

    def work(http, token, acc):
        _delete(http, token, link.event_id)
        db.delete(link)

    return _run(db, task.user_id, work)


def forget_task(db: Session, task: Task) -> None:
    link = _task_link(db, task.id)
    if link:
        db.delete(link)


def sync_reminder(db: Session, reminder: Reminder) -> bool:
    """Nhắc nhở độc lập (không gắn công việc) -> một sự kiện có thông báo đúng giờ nhắc."""
    if reminder.task_id is not None:
        return False  # việc đã có sự kiện riêng kèm nhắc trước hạn

    def work(http, token, acc):
        body = _event_body(summary=f"🔔 {reminder.message}", description="Nhắc nhở tạo bởi Trợ lý AI cá nhân",
                           start=reminder.remind_at, popup_minutes=0)
        db.add(CalendarEvent(user_id=reminder.user_id, reminder_id=reminder.id,
                             event_id=_upsert(http, token, None, body)))

    return _run(db, reminder.user_id, work)


def unsync_reminder(db: Session, reminder: Reminder) -> bool:
    link = db.scalar(select(CalendarEvent).where(CalendarEvent.reminder_id == reminder.id))
    if not link:
        return False

    def work(http, token, acc):
        _delete(http, token, link.event_id)
        db.delete(link)

    return _run(db, reminder.user_id, work)


def forget_reminder(db: Session, reminder: Reminder) -> None:
    link = db.scalar(select(CalendarEvent).where(CalendarEvent.reminder_id == reminder.id))
    if link:
        db.delete(link)


def sync_all(db: Session, user: User) -> int:
    """Đẩy toàn bộ việc chưa xong có hạn chót lên lịch (dùng sau khi vừa kết nối)."""
    tasks = db.scalars(select(Task).where(Task.user_id == user.id, Task.due_at.is_not(None),
                                          Task.status != TaskStatus.done))
    return sum(1 for t in list(tasks) if sync_task(db, t))
