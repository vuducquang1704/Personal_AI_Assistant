"""Bộ chuyển đổi Gemini: nhận hội thoại ở định dạng Anthropic (như assistant.chat dùng) và trả về
phản hồi có cùng hình dạng (stop_reason, content gồm khối text / tool_use), nhờ vậy vòng lặp gọi
công cụ trong assistant.py dùng chung cho cả hai nhà cung cấp."""
import copy
import logging
import uuid
from types import SimpleNamespace

import httpx

from ..config import get_settings

log = logging.getLogger(__name__)
BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# Cho phép test thay bằng httpx.MockTransport
transport: httpx.BaseTransport | None = None


class GeminiError(Exception):
    """Lỗi đã được diễn giải sang tiếng Việt, hiển thị thẳng cho người dùng."""


def _schema(node):
    """Chuyển JSON Schema của công cụ sang tập con OpenAPI mà Gemini chấp nhận."""
    if isinstance(node, list):
        return [_schema(x) for x in node]
    if not isinstance(node, dict):
        return node
    out = {}
    for k, v in node.items():
        if k in ("additionalProperties", "strict"):
            continue
        if k == "type" and isinstance(v, list):  # ["string","null"] -> string + nullable
            non_null = [t for t in v if t != "null"]
            out["type"] = non_null[0]
            if "null" in v:
                out["nullable"] = True
            continue
        out[k] = _schema(v)
    return out


def convert_tools(tools: list[dict]) -> list[dict]:
    decls = []
    for t in tools:
        d = {"name": t["name"], "description": t["description"]}
        params = _schema(copy.deepcopy(t["input_schema"]))
        if params.get("properties"):
            d["parameters"] = params
        decls.append(d)
    return [{"functionDeclarations": decls}]


def _blocks(content) -> list:
    return content if isinstance(content, list) else [SimpleNamespace(type="text", text=content)]


def convert_messages(messages: list[dict]) -> list[dict]:
    names: dict[str, str] = {}  # tool_use id -> tên hàm, để ghép với kết quả
    out: list[dict] = []
    for m in messages:
        parts: list[dict] = []
        if m["role"] == "assistant":
            for b in _blocks(m["content"]):
                if getattr(b, "raw", None):  # giữ nguyên part gốc (kèm thoughtSignature)
                    parts.append(b.raw)
                    if b.type == "tool_use":
                        names[b.id] = b.name
                elif b.type == "text" and b.text:
                    parts.append({"text": b.text})
            role = "model"
        else:
            if isinstance(m["content"], str):
                parts.append({"text": m["content"]})
            else:
                for b in m["content"]:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        body = {"error": b["content"]} if b.get("is_error") else {"result": b["content"]}
                        parts.append({"functionResponse": {"name": names.get(b["tool_use_id"], "unknown"),
                                                           "response": body}})
                    elif isinstance(b, dict) and b.get("type") == "text":
                        parts.append({"text": b["text"]})
            role = "user"
        if parts:
            out.append({"role": role, "parts": parts})
    return out


def _error_message(status: int, body: str) -> str:
    low = body.lower()
    if status in (400, 401, 403) and ("api key" in low or "api_key" in low or status in (401, 403)):
        return "Khoá Gemini không hợp lệ hoặc chưa được cấp quyền (GEMINI_API_KEY)."
    if status == 429:
        return "Gemini đang giới hạn lượt gọi (gói miễn phí có hạn mức theo phút và theo ngày), bạn thử lại sau ít phút nhé."
    if status == 404:
        return "Không tìm thấy mô hình Gemini đã chọn, hãy kiểm tra biến LLM_MODEL."
    return f"Lỗi từ dịch vụ Gemini ({status})."


def generate(messages: list[dict], *, system: str, tools: list[dict]) -> SimpleNamespace:
    s = get_settings()
    if not s.gemini_api_key:
        raise GeminiError("Chưa cấu hình khoá API cho Gemini (GEMINI_API_KEY).")
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": convert_messages(messages),
        "generationConfig": {"temperature": 0.3},
    }
    if tools:
        body["tools"] = convert_tools(tools)
    try:
        with httpx.Client(timeout=60, transport=transport) as http:
            r = http.post(f"{BASE}/{s.model}:generateContent", json=body, headers={"x-goog-api-key": s.gemini_api_key})
    except httpx.HTTPError:
        raise GeminiError("Không kết nối được tới dịch vụ Gemini.")
    if r.status_code != 200:
        log.warning("Gemini %s: %s", r.status_code, r.text[:300])
        raise GeminiError(_error_message(r.status_code, r.text))

    data = r.json()
    cands = data.get("candidates") or []
    if not cands or data.get("promptFeedback", {}).get("blockReason"):
        return SimpleNamespace(stop_reason="refusal", content=[])
    cand = cands[0]
    content = []
    for p in cand.get("content", {}).get("parts", []):
        if "functionCall" in p:
            fc = p["functionCall"]
            content.append(SimpleNamespace(type="tool_use", id=fc.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                                           name=fc["name"], input=fc.get("args") or {}, raw=p))
        elif p.get("text") and not p.get("thought"):
            content.append(SimpleNamespace(type="text", text=p["text"], raw=p))
    if any(b.type == "tool_use" for b in content):
        stop = "tool_use"
    elif cand.get("finishReason") in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION"):
        stop = "refusal"
    else:
        stop = "end_turn"
    return SimpleNamespace(stop_reason=stop, content=content)
