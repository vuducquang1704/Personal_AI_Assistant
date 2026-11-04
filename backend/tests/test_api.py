from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

VN = ZoneInfo("Asia/Ho_Chi_Minh")


def test_register_login_me(client):
    r = client.post("/api/auth/register", json={"email": "a@b.com", "full_name": "A", "password": "123456"})
    assert r.status_code == 201
    assert client.post("/api/auth/register", json={"email": "A@b.com", "full_name": "A", "password": "123456"}).status_code == 409
    assert client.post("/api/auth/login", json={"email": "a@b.com", "password": "wrong!!"}).status_code == 401
    tok = client.post("/api/auth/login", json={"email": "a@b.com", "password": "123456"}).json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"}).json()
    assert me["email"] == "a@b.com"
    assert client.get("/api/auth/me").status_code == 401


def test_task_crud_and_stats(client, auth):
    due = (datetime.now(VN) + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")
    t = client.post("/api/tasks", json={"title": "Nộp báo cáo", "due_at": due, "priority": "high"}, headers=auth).json()
    assert t["priority"] == "high" and t["status"] == "todo"
    client.post("/api/tasks", json={"title": "Đọc sách"}, headers=auth)
    assert len(client.get("/api/tasks", headers=auth).json()) == 2
    assert len(client.get("/api/tasks?q=báo cáo", headers=auth).json()) == 1
    u = client.patch(f"/api/tasks/{t['id']}", json={"status": "done"}, headers=auth).json()
    assert u["status"] == "done" and u["completed_at"]
    s = client.get("/api/tasks/stats", headers=auth).json()
    assert s["total"] == 2 and s["done"] == 1 and s["completion_rate"] == 0.5
    assert client.delete(f"/api/tasks/{t['id']}", headers=auth).status_code == 204
    assert client.get(f"/api/tasks/{t['id']}", headers=auth).status_code == 404


def test_users_cannot_see_each_other(client, auth):
    t = client.post("/api/tasks", json={"title": "Bí mật"}, headers=auth).json()
    tok = client.post("/api/auth/register", json={"email": "x@y.com", "full_name": "X", "password": "123456"}).json()["access_token"]
    other = {"Authorization": f"Bearer {tok}"}
    assert client.get(f"/api/tasks/{t['id']}", headers=other).status_code == 404
    assert client.get("/api/tasks", headers=other).json() == []


def test_reminder_worker(client, auth):
    from app.services.reminder_worker import run_once
    past = (datetime.now(VN) - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M")
    client.post("/api/reminders", json={"message": "Uống nước", "remind_at": past}, headers=auth)
    soon = (datetime.now(VN) + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M")
    client.post("/api/tasks", json={"title": "Họp nhóm", "due_at": soon}, headers=auth)
    assert run_once() == 2  # 1 nhắc nhở người dùng + 1 nhắc nhở tự động cho việc sắp đến hạn
    due = client.get("/api/reminders/due", headers=auth).json()
    assert {d["message"].split(" ")[0] for d in due} == {"Uống", "[auto]"}
    client.post(f"/api/reminders/{due[0]['id']}/seen", headers=auth)
    assert len(client.get("/api/reminders/due", headers=auth).json()) == 1
    assert run_once() == 0  # không tạo trùng
