"""Kiểm thử vòng lặp gọi công cụ của trợ lý với LLM giả lập (không cần API key)."""
from types import SimpleNamespace as NS

import pytest

from app.models import Conversation, User
from app.services import assistant


def text(t):
    return NS(type="text", text=t)


def tool(name, args, id="tu1"):
    return NS(type="tool_use", name=name, input=args, id=id)


def scripted(*responses):
    calls = []

    def llm(messages):
        calls.append(list(messages))
        return responses[len(calls) - 1]
    llm.calls = calls
    return llm


_open = []


def _setup(client, auth):
    from app.db import SessionLocal
    db = SessionLocal()
    _open.append(db)
    user = db.query(User).first()
    conv = Conversation(user_id=user.id)
    db.add(conv)
    db.commit()
    return db, user, conv


@pytest.fixture(autouse=True)
def _close_sessions():
    yield
    while _open:
        _open.pop().close()


def test_create_task_via_tool(client, auth):
    db, user, conv = _setup(client, auth)
    llm = scripted(
        NS(stop_reason="tool_use", content=[tool("create_task", {"title": "Nộp báo cáo", "description": None,
                                                              "due_at": "2026-11-07T17:00", "priority": "high"})]),
        NS(stop_reason="end_turn", content=[text("Đã tạo việc nộp báo cáo, hạn 5 giờ chiều thứ Sáu.")]),
    )
    msg, pending = assistant.chat(db, user, conv, "nhắc mình nộp báo cáo trước 5h chiều thứ 6, gấp nhé", llm=llm)
    assert msg.text.startswith("Đã tạo")
    assert msg.actions[0]["type"] == "create_task"
    assert msg.actions[0]["task"]["due_at"] == "2026-11-07 17:00"  # lưu UTC, đọc lại đúng giờ Việt Nam
    tasks = client.get("/api/tasks", headers=auth).json()
    assert tasks[0]["title"] == "Nộp báo cáo" and tasks[0]["priority"] == "high"
    # Lượt 2 gửi kèm kết quả công cụ
    assert llm.calls[1][-1]["content"][0]["type"] == "tool_result"
    assert "Thời điểm hiện tại" in llm.calls[0][-1]["content"]


def test_delete_requires_confirmation(client, auth):
    t = client.post("/api/tasks", json={"title": "Việc cũ"}, headers=auth).json()
    db, user, conv = _setup(client, auth)
    llm = scripted(
        NS(stop_reason="tool_use", content=[tool("delete_task", {"task_id": t["id"]})]),
        NS(stop_reason="end_turn", content=[text("Bạn bấm xác nhận để xoá nhé.")]),
    )
    _, pending = assistant.chat(db, user, conv, "xoá việc cũ đi", llm=llm)
    assert len(pending) == 1
    assert client.get(f"/api/tasks/{t['id']}", headers=auth).status_code == 200  # chưa bị xoá
    r = client.post(f"/api/chat/actions/{pending[0]['id']}/confirm", headers=auth)
    assert r.json()["status"] == "confirmed"
    assert client.get(f"/api/tasks/{t['id']}", headers=auth).status_code == 404
    assert client.post(f"/api/chat/actions/{pending[0]['id']}/confirm", headers=auth).status_code == 409


def test_tool_error_is_reported_to_llm(client, auth):
    db, user, conv = _setup(client, auth)
    llm = scripted(
        NS(stop_reason="tool_use", content=[tool("update_task", {"task_id": 999, "title": None, "description": None,
                                                              "due_at": None, "priority": "none", "status": "done"})]),
        NS(stop_reason="end_turn", content=[text("Mình không tìm thấy việc đó.")]),
    )
    assistant.chat(db, user, conv, "xong việc 999 rồi", llm=llm)
    result = llm.calls[1][-1]["content"][0]
    assert result["is_error"] is True and "Không tìm thấy" in result["content"]


def test_history_is_text_only_and_alternating(client, auth):
    db, user, conv = _setup(client, auth)
    llm = scripted(NS(stop_reason="end_turn", content=[text("Chào bạn!")]),
                   NS(stop_reason="end_turn", content=[text("Bạn có 0 việc.")]))
    assistant.chat(db, user, conv, "xin chào", llm=llm)
    db.refresh(conv)
    assistant.chat(db, user, conv, "hôm nay có việc gì", llm=llm)
    second = llm.calls[1]
    assert [m["role"] for m in second] == ["user", "assistant", "user"]
    assert second[1]["content"] == "Chào bạn!"
