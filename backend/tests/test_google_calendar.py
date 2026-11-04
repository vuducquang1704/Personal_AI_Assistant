"""Kiểm thử tích hợp Google Calendar với máy chủ Google giả lập (httpx.MockTransport)."""
import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.config import get_settings
from app.services import google_calendar as gc


class FakeGoogle:
    def __init__(self):
        self.events: dict[str, dict] = {}
        self.calls: list[tuple[str, str]] = []
        self.next_id = 1
        self.refresh_ok = True
        self.revoked = False

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
