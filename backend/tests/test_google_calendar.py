import json
"""Kiểm thử tích hợp Google Calendar với máy chủ Google giả lập (httpx.MockTransport)."""
import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.config import get_settings
from app.services import google_calendar as gc
from app.services.gmail import GMAIL, classify


class FakeGoogle:
    def __init__(self):
        self.events: dict[str, dict] = {}
        self.calls: list[tuple[str, str]] = []
        self.next_id = 1
        self.refresh_ok = True
        self.revoked = False
        self.inbox: dict[str, dict] = {}
        self.gmail_forbidden = False

    def handler(self, req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        self.calls.append((req.method, url))
        if url == gc.TOKEN_URL:
            form = parse_qs(req.content.decode())
            if form["grant_type"] == ["authorization_code"]:
                assert form["code"] == ["good-code"]
                return httpx.Response(200, json={"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600})
            if not self.refresh_ok:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"access_token": "at-2", "expires_in": 3600})
        if url == gc.USERINFO_URL:
            return httpx.Response(200, json={"email": "quang@gmail.com"})
        if url.startswith(GMAIL):
            if self.gmail_forbidden:
                return httpx.Response(403, json={"error": {"message": "insufficient scopes"}})
            path = req.url.path
            if path.endswith("/messages"):
                return httpx.Response(200, json={"messages": [{"id": k} for k in self.inbox]})
            return httpx.Response(200, json=self.inbox[path.rsplit("/", 1)[-1]])
        if url == gc.REVOKE_URL:
            self.revoked = True
            return httpx.Response(200)
        assert req.headers["Authorization"].startswith("Bearer ")
        if url == gc.EVENTS_URL and req.method == "POST":
            eid = f"ev{self.next_id}"
            self.next_id += 1
            self.events[eid] = json.loads(req.content)
            return httpx.Response(200, json={"id": eid, **self.events[eid]})
        eid = url.rsplit("/", 1)[-1]
        if eid not in self.events:
            return httpx.Response(404)
        if req.method == "PUT":
            self.events[eid] = json.loads(req.content)
            return httpx.Response(200, json={"id": eid})
        if req.method == "DELETE":
            del self.events[eid]
            return httpx.Response(204)
        return httpx.Response(405)


@pytest.fixture()
def google(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "google_client_id", "cid")
    monkeypatch.setattr(s, "google_client_secret", "secret")
    fake = FakeGoogle()
    monkeypatch.setattr(gc, "transport", httpx.MockTransport(fake.handler))
    return fake


def _connect(client, auth):
    url = client.get("/api/google/auth-url", headers=auth).json()["url"]
    q = parse_qs(urlparse(url).query)
    assert q["access_type"] == ["offline"] and "calendar.events" in q["scope"][0]
    r = client.get("/api/google/callback", params={"code": "good-code", "state": q["state"][0]},
                   follow_redirects=False)  # TestClient giữ cookie nonce như trình duyệt
    assert r.status_code == 307 and r.headers["location"].endswith("/settings?google=connected")


def test_not_configured(client, auth):
    st = client.get("/api/google/status", headers=auth).json()
    assert st["configured"] is False and st["connected"] is False
    assert client.get("/api/google/auth-url", headers=auth).status_code == 400
    # không kết nối thì tạo việc vẫn bình thường
    assert client.post("/api/tasks", json={"title": "A", "due_at": "2026-11-05T09:00:00"}, headers=auth).status_code == 201


def test_bad_state_rejected(client, auth, google):
    r = client.get("/api/google/callback", params={"code": "good-code", "state": "xxx"}, follow_redirects=False)
    assert r.headers["location"].endswith("google=error")
    r = client.get("/api/google/callback", params={"error": "access_denied"}, follow_redirects=False)
    assert r.headers["location"].endswith("google=denied")


def test_connect_and_task_lifecycle(client, auth, google):
    # việc tạo trước khi kết nối sẽ được đẩy lên khi kết nối
    client.post("/api/tasks", json={"title": "Nộp báo cáo", "due_at": "2026-11-05T09:00:00", "priority": "high"},
                headers=auth)
    _connect(client, auth)
    st = client.get("/api/google/status", headers=auth).json()
    assert st == {"configured": True, "connected": True, "email": "quang@gmail.com", "sync_enabled": True,
                  "reminder_minutes": 30, "last_error": None}
    assert len(google.events) == 1
    ev = next(iter(google.events.values()))
    assert ev["summary"] == "Nộp báo cáo" and ev["colorId"] == "11"
    assert ev["start"]["dateTime"] == "2026-11-05T09:00:00+07:00"
    assert ev["reminders"]["overrides"] == [{"method": "popup", "minutes": 30}]

    # tạo việc mới -> sự kiện mới; việc không có hạn -> không tạo
    tid = client.post("/api/tasks", json={"title": "Họp nhóm", "due_at": "2026-11-06T14:00:00"}, headers=auth).json()["id"]
    client.post("/api/tasks", json={"title": "Đọc sách"}, headers=auth)
    assert len(google.events) == 2

    # đổi hạn -> cập nhật cùng sự kiện
    client.patch(f"/api/tasks/{tid}", json={"due_at": "2026-11-06T15:30:00"}, headers=auth)
    assert len(google.events) == 2
    assert any(e["start"]["dateTime"] == "2026-11-06T15:30:00+07:00" for e in google.events.values())

    # hoàn thành -> gỡ sự kiện
    client.patch(f"/api/tasks/{tid}", json={"status": "done"}, headers=auth)
    assert len(google.events) == 1
    # mở lại -> tạo lại
    client.patch(f"/api/tasks/{tid}", json={"status": "todo"}, headers=auth)
    assert len(google.events) == 2
    # xoá việc -> xoá sự kiện
    assert client.delete(f"/api/tasks/{tid}", headers=auth).status_code == 204
    assert len(google.events) == 1


def test_event_deleted_on_google_is_recreated(client, auth, google):
    _connect(client, auth)
    tid = client.post("/api/tasks", json={"title": "X", "due_at": "2026-11-05T09:00:00"}, headers=auth).json()["id"]
    google.events.clear()  # người dùng xoá sự kiện trực tiếp trên Google Calendar
    client.patch(f"/api/tasks/{tid}", json={"title": "X2"}, headers=auth)
    assert [e["summary"] for e in google.events.values()] == ["X2"]


def test_standalone_reminder_and_settings(client, auth, google):
    _connect(client, auth)
    r = client.post("/api/reminders", json={"message": "Gọi mẹ", "remind_at": "2026-11-05T20:00:00"}, headers=auth)
    ev = next(iter(google.events.values()))
    assert ev["summary"] == "🔔 Gọi mẹ" and ev["reminders"]["overrides"][0]["minutes"] == 0
    client.delete(f"/api/reminders/{r.json()['id']}", headers=auth)
    assert google.events == {}

    st = client.patch("/api/google", json={"sync_enabled": False}, headers=auth).json()
    assert st["sync_enabled"] is False
    client.post("/api/tasks", json={"title": "Y", "due_at": "2026-11-05T09:00:00"}, headers=auth)
    assert google.events == {}
    client.patch("/api/google", json={"sync_enabled": True, "reminder_minutes": 60}, headers=auth)
    assert next(iter(google.events.values()))["reminders"]["overrides"][0]["minutes"] == 60


def test_revoked_access_is_reported_not_raised(client, auth, google, monkeypatch):
    _connect(client, auth)
    # hết hạn access token và refresh token bị thu hồi
    from app.db import SessionLocal
    from app.models import GoogleAccount
    with SessionLocal() as db:
        acc = db.query(GoogleAccount).one()
        acc.access_expires_at = None
        db.commit()
    google.refresh_ok = False
    r = client.post("/api/tasks", json={"title": "Z", "due_at": "2026-11-05T09:00:00"}, headers=auth)
    assert r.status_code == 201  # việc vẫn được tạo
    assert "kết nối lại" in client.get("/api/google/status", headers=auth).json()["last_error"]

    assert client.delete("/api/google", headers=auth).status_code == 204
    assert google.revoked
    assert client.get("/api/google/status", headers=auth).json()["connected"] is False


def test_token_encrypted_at_rest(client, auth, google):
    _connect(client, auth)
    from app.db import SessionLocal
    from app.models import GoogleAccount
    with SessionLocal() as db:
        acc = db.query(GoogleAccount).one()
        assert "rt-1" not in acc.refresh_token_enc
        assert gc.decrypt(acc.refresh_token_enc) == "rt-1"


def test_state_cannot_be_used_as_login_token(client, auth, google):
    url = client.get("/api/google/auth-url", headers=auth).json()["url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {state}"})
    assert r.status_code == 401


def test_callback_requires_same_browser(client, auth, google):
    url = client.get("/api/google/auth-url", headers=auth).json()["url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    client.cookies.clear()  # trình duyệt khác (nạn nhân bấm liên kết của kẻ tấn công)
    r = client.get("/api/google/callback", params={"code": "good-code", "state": state}, follow_redirects=False)
    assert r.headers["location"].endswith("google=error")
    assert client.get("/api/google/status", headers=auth).json()["connected"] is False


def test_calendar_state_reports_real_sync(client, auth, google):
    from app.db import SessionLocal
    from app.models import User
    from app.services import ai_tools
    _connect(client, auth)
    with SessionLocal() as db:
        user = db.query(User).one()
        ex = ai_tools.ToolExecutor(db, user)
        out = json.loads(ex.run("create_task", {"title": "Họp nhóm", "description": None,
                                     "due_at": "2026-11-05T15:00", "priority": "none"}))
        assert out["calendar"] == {"connected": True, "synced": True}
        out = json.loads(ex.run("create_task", {"title": "Đọc sách", "description": None, "due_at": None, "priority": "none"}))
        assert out["calendar"] is None  # không có hạn thì không áp dụng
    assert len(google.events) == 1



def _mail(sender, subject, snippet, labels=("INBOX", "UNREAD")):
    import base64
    body = base64.urlsafe_b64encode(f"Nội dung đầy đủ: {snippet}".encode()).decode().rstrip("=")
    return {"labelIds": list(labels), "snippet": snippet,
            "payload": {"mimeType": "multipart/alternative", "parts": [
                {"mimeType": "text/plain", "body": {"data": body}}], "headers": [
        {"name": "From", "value": sender}, {"name": "Subject", "value": subject},
        {"name": "Date", "value": "Wed, 4 Nov 2026 08:00:00 +0700"}]}}


def test_classify_rules():
    assert classify(["CATEGORY_PROMOTIONS"], "shop@x.com", "Giảm 50%?", "") == "promo"
    assert classify([], "no-reply@bank.vn", "Thông báo giao dịch", "Bạn có giao dịch mới") == "notice"
    assert classify([], "thay@hust.edu.vn", "Báo cáo đồ án", "Em gửi bản nháp trước thứ Sáu được không?") == "needs_reply"
    assert classify([], "ban@gmail.com", "Ảnh chuyến đi", "Gửi cậu ảnh hôm qua") == "read_later"


def _inbox(google):
    google.inbox = {
        "m1": _mail("Thầy Liêm <liem@hust.edu.vn>", "Lịch duyệt đồ án", "Em xác nhận giúp thầy lịch thứ Năm nhé?"),
        "m2": _mail("Shopee <no-reply@shopee.vn>", "Đơn hàng đã giao", "Đơn hàng của bạn đã giao thành công"),
        "m3": _mail("Sale <deal@shop.vn>", "Siêu sale 11.11", "Giảm giá", labels=("INBOX", "CATEGORY_PROMOTIONS")),
    }


def test_emails_endpoint_and_tasks(client, auth, google):
    _connect(client, auth)
    _inbox(google)
    r = client.get("/api/google/emails", headers=auth).json()
    assert r["counts"] == {"needs_reply": 1, "notice": 1, "promo": 1, "read_later": 0}
    r = client.post("/api/google/emails/tasks", headers=auth).json()
    assert r == {"created": 1, "titles": ["Trả lời: Lịch duyệt đồ án"]}
    # chạy lại không tạo trùng
    assert client.post("/api/google/emails/tasks", headers=auth).json()["created"] == 0
    task = next(t for t in client.get("/api/tasks", headers=auth).json() if t["title"].startswith("Trả lời"))
    assert task["due_at"] is not None
    # việc có hạn nên cũng lên Google Calendar
    assert any(e["summary"] == "Trả lời: Lịch duyệt đồ án" for e in google.events.values())


def test_emails_without_gmail_permission(client, auth, google):
    _connect(client, auth)
    google.gmail_forbidden = True
    r = client.get("/api/google/emails", headers=auth)
    assert r.status_code == 400 and "quyền đọc email" in r.json()["detail"]


def test_daily_digest_runs_once_per_day(client, auth, google):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.services.reminder_worker import daily_email_digests
    _connect(client, auth)
    _inbox(google)
    vn = ZoneInfo("Asia/Ho_Chi_Minh")
    assert daily_email_digests(datetime(2026, 11, 4, 7, 30, tzinfo=vn)) == 0  # trước 8 giờ chưa chạy
    assert daily_email_digests(datetime(2026, 11, 4, 8, 5, tzinfo=vn)) == 1
    assert daily_email_digests(datetime(2026, 11, 4, 9, 0, tzinfo=vn)) == 0  # đã chạy hôm nay
    rems = client.get("/api/reminders", headers=auth).json()
    assert any("1 email quan trọng" in r["message"] for r in rems)
    titles = [t["title"] for t in client.get("/api/tasks", headers=auth).json()]
    assert titles.count("Trả lời: Lịch duyệt đồ án") == 1


def _fake_ai(monkeypatch):
    calls = []

    def fake(system, prompt):
        calls.append(prompt)
        assert "Nội dung đầy đủ" in prompt  # đọc thân thư, không chỉ đoạn trích
        return "Thầy hỏi lịch duyệt đồ án thứ Năm, cần xác nhận."
    from app.services import assistant
    monkeypatch.setattr(assistant, "complete_text", fake)
    return calls


def test_important_summaries_are_cached(client, auth, google, monkeypatch):
    calls = _fake_ai(monkeypatch)
    _connect(client, auth)
    _inbox(google)
    r = client.get("/api/google/emails", headers=auth).json()
    assert r["important"] == 1 and all(i["summary"] is None for i in r["items"])  # chưa yêu cầu tóm tắt
    r = client.get("/api/google/emails?summarize=true", headers=auth).json()
    imp = [i for i in r["items"] if i["important"]]
    assert len(imp) == 1 and imp[0]["summary"].startswith("Thầy hỏi")
    client.get("/api/google/emails?summarize=true", headers=auth)
    assert len(calls) == 1  # lần hai dùng bản đã lưu, không gọi AI nữa


def test_assistant_tool_check_emails(client, auth, google, monkeypatch):
    from app.db import SessionLocal
    from app.models import User
    from app.services import ai_tools
    _fake_ai(monkeypatch)
    _connect(client, auth)
    _inbox(google)
    with SessionLocal() as db:
        out = json.loads(ai_tools.ToolExecutor(db, db.query(User).one()).run("check_emails", {}))
    assert out["total_unread"] == 3 and out["counts"]["Cần trả lời"] == 1
    assert out["important"][0]["summary"].startswith("Thầy hỏi")


def test_digest_reminder_contains_summary(client, auth, google, monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.services.reminder_worker import daily_email_digests
    _fake_ai(monkeypatch)
    _connect(client, auth)
    _inbox(google)
    daily_email_digests(datetime(2026, 11, 4, 8, 5, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")))
    rems = client.get("/api/reminders", headers=auth).json()
    assert any("1 email quan trọng" in r["message"] and "duyệt đồ án thứ Năm" in r["message"] for r in rems)
