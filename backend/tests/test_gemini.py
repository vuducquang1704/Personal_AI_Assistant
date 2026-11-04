"""Kiểm thử bộ chuyển đổi Gemini với máy chủ giả lập."""
import json

import httpx
import pytest

from app.config import get_settings
from app.services import assistant, gemini
from app.services.ai_tools import TOOLS


@pytest.fixture()
def fake(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "gemini_api_key", "test-key")
    monkeypatch.setattr(s, "llm_provider", "gemini")
    monkeypatch.setattr(s, "llm_model", None)
    state = {"requests": [], "script": []}

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.headers["x-goog-api-key"] == "test-key"
        state["requests"].append(json.loads(req.content))
        status, body = state["script"].pop(0)
        return httpx.Response(status, json=body)

    monkeypatch.setattr(gemini, "transport", httpx.MockTransport(handler))
    return state


def _text(t):
    return (200, {"candidates": [{"content": {"parts": [{"text": t}]}, "finishReason": "STOP"}]})


def test_provider_selection(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "llm_provider", "auto")
    monkeypatch.setattr(s, "anthropic_api_key", None)
    monkeypatch.setattr(s, "gemini_api_key", "k")
    monkeypatch.setattr(s, "llm_model", None)
    assert s.provider == "gemini" and s.model == "gemini-3.5-flash-lite"
    monkeypatch.setattr(s, "anthropic_api_key", "a")
    assert s.provider == "anthropic" and s.model == "claude-opus-5-5"


def test_tool_schema_conversion():
    decls = gemini.convert_tools(TOOLS)[0]["functionDeclarations"]
    text = json.dumps(decls)
    assert "additionalProperties" not in text and '"strict"' not in text and '["string", "null"]' not in text
    create = next(d for d in decls if d["name"] == "create_task")
    assert create["parameters"]["properties"]["due_at"]["nullable"] is True
    assert "parameters" not in next(d for d in decls if d["name"] == "get_statistics")


def test_plain_reply(fake):
    fake["script"] = [_text("Xin chào")]
    resp = gemini.generate([{"role": "user", "content": "chào"}], system="sys", tools=TOOLS)
    assert resp.stop_reason == "end_turn" and resp.content[0].text == "Xin chào"
    assert fake["requests"][0]["systemInstruction"]["parts"][0]["text"] == "sys"


def test_full_chat_with_tool_call(client, auth, fake):
    call = {"functionCall": {"name": "create_task", "args": {"title": "Nộp báo cáo", "description": None,
                                                              "due_at": "2026-11-05T09:00", "priority": "high"}},
            "thoughtSignature": "sig123"}
    fake["script"] = [(200, {"candidates": [{"content": {"parts": [call]}, "finishReason": "STOP"}]}),
                      _text("Mình đã tạo việc nộp báo cáo.")]
    r = client.post("/api/chat", json={"message": "Mai 9 giờ nộp báo cáo, gấp"}, headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["reply"]["text"] == "Mình đã tạo việc nộp báo cáo."
    tasks = client.get("/api/tasks", headers=auth).json()
    assert [t["title"] for t in tasks] == ["Nộp báo cáo"] and tasks[0]["priority"] == "high"
    # lượt 2 gửi lại functionCall gốc (kèm thoughtSignature) và functionResponse đúng tên hàm
    contents = fake["requests"][1]["contents"]
    assert contents[-2]["parts"][0]["thoughtSignature"] == "sig123"
    fr = contents[-1]["parts"][0]["functionResponse"]
    assert fr["name"] == "create_task" and "result" in fr["response"]


def test_errors_are_friendly(client, auth, fake):
    fake["script"] = [(400, {"error": {"message": "API key not valid. Please pass a valid API key."}})]
    r = client.post("/api/chat", json={"message": "chào"}, headers=auth)
    assert r.status_code >= 400 and "GEMINI_API_KEY" in r.text
    fake["script"] = [(429, {"error": {"message": "quota"}})]
    r = client.post("/api/chat", json={"message": "chào"}, headers=auth)
    assert "giới hạn" in r.text
