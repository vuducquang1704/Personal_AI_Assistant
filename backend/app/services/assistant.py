"""Trợ lý AI: nhận câu lệnh tiếng Việt (gõ hoặc nói), dùng LLM (Claude) gọi công cụ để thao tác công việc."""
import json
import logging
import time
from datetime import timedelta

import anthropic
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import ChatMessage, Conversation, User
from ..timeutil import local_tz, now_utc
from . import gemini
from .ai_tools import TOOLS, ToolError, ToolExecutor

log = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 8
WEEKDAYS = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]

SYSTEM_PROMPT = """Bạn là trợ lý AI cá nhân giúp người dùng quản lý công việc, giao tiếp bằng tiếng Việt.

Bạn có các công cụ để tạo, tra cứu, cập nhật, xoá công việc, đặt nhắc nhở và xem thống kê.
Cách làm việc:
- Khi người dùng nhắc tới một việc cần làm, hãy gọi create_task, tự trích xuất tên việc, hạn chót và mức ưu tiên
  ("gấp", "quan trọng", "ưu tiên cao" -> high; "không gấp", "khi rảnh" -> low).
- Quy đổi thời gian tương đối ("mai", "thứ sáu tuần sau", "8 giờ tối nay", "cuối tháng") ra thời điểm cụ thể
  dựa vào thời điểm hiện tại được cung cấp trong tin nhắn. Nếu chỉ có ngày mà không có giờ, dùng 23:59 cho hạn chót
  và 08:00 cho nhắc nhở.
- Trước khi sửa, xoá hoặc đánh dấu hoàn thành, nếu chưa biết id thì gọi list_tasks để tìm. Nếu có nhiều việc khớp,
  hỏi lại người dùng muốn chọn việc nào.
- Xoá chỉ tạo yêu cầu xác nhận; hãy nói rõ người dùng cần bấm xác nhận.
- Không bịa ra công việc không có trong kết quả công cụ.
- Kết quả tạo/sửa việc hoặc đặt nhắc nhở có trường "calendar". Nếu calendar.synced là true, hãy nói đã ghi lên Google Calendar.
  Nếu synced là false và có "error", nói rõ lỗi đó và gợi ý kết nối lại trong Cài đặt. Nếu connected là false, nói người dùng
  chưa kết nối Google Calendar. Tuyệt đối không nói "chưa ghi được" khi không có trường calendar hoặc synced là null
  mà việc không có hạn chót.

Câu trả lời của bạn sẽ được đọc thành giọng nói, vì vậy:
- Trả lời ngắn gọn, tự nhiên, thường 1-3 câu. Không dùng markdown, bảng, ký hiệu đầu dòng hay emoji.
- Khi liệt kê nhiều việc, nói số lượng và đọc tối đa khoảng 5 việc quan trọng nhất.
- Đọc ngày giờ theo cách nói tự nhiên, ví dụ "9 giờ sáng thứ Sáu, ngày 7 tháng 11"."""


class AssistantError(Exception):
    pass


def _client() -> anthropic.Anthropic:
    s = get_settings()
    return anthropic.Anthropic(api_key=s.anthropic_api_key) if s.anthropic_api_key else anthropic.Anthropic()


def call_llm(messages: list[dict]):
    """Gọi LLM (Claude hoặc Gemini). Tách thành hàm riêng để dễ thay thế (mock) khi kiểm thử."""
    s = get_settings()
    if s.provider == "gemini":
        return gemini.generate(messages, system=SYSTEM_PROMPT, tools=TOOLS)
    extra: dict = {}
    if "haiku" not in s.model:  # mô hình nhỏ có thể không hỗ trợ fallback phía máy chủ
        # Nếu bộ lọc an toàn từ chối nhầm, API tự chạy lại trên mô hình dự phòng phù hợp
        extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
    return _client().beta.messages.create(
        model=s.model,
        max_tokens=16000,
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        tools=TOOLS,
        messages=messages,
        thinking={"type": "adaptive"},
        output_config={"effort": s.llm_effort},
        **extra,
    )


def context_note() -> str:
    now = now_utc().astimezone(local_tz())
    return (f"[Thời điểm hiện tại: {WEEKDAYS[now.weekday()]}, {now:%Y-%m-%d %H:%M} (giờ Việt Nam). "
            f"Ngày mai là {(now + timedelta(days=1)):%Y-%m-%d}.]")


def _history(conv: Conversation, limit_turns: int) -> list[dict]:
    """Lịch sử dạng văn bản thuần (không gửi lại thinking/tool blocks của các lượt trước)."""
    msgs = [m for m in conv.messages if m.role in ("user", "assistant")][-2 * limit_turns:]
    out: list[dict] = []
    for m in msgs:
        if out and out[-1]["role"] == m.role:  # đảm bảo xen kẽ user/assistant
            out[-1]["content"] += "\n" + m.text
        else:
            out.append({"role": m.role, "content": m.text})
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out


def _actions_summary(actions: list[dict]) -> str:
    return "; ".join(a["type"] for a in actions) or "không có"


def chat(db: Session, user: User, conv: Conversation, text: str, input_mode: str = "text",
         llm=None) -> tuple[ChatMessage, list[dict]]:
    llm = llm or call_llm
    settings = get_settings()
    started = time.perf_counter()

    messages = _history(conv, settings.history_turns)
    if messages and messages[-1]["role"] == "user":  # lượt trước bị lỗi, chưa có trả lời
        messages.pop()
    messages.append({"role": "user", "content": f"{context_note()}\n{text}"})

    db.add(ChatMessage(conversation_id=conv.id, role="user", text=text, input_mode=input_mode))
    db.commit()

    executor = ToolExecutor(db, user)
    reply_text = ""
    try:
        for _ in range(MAX_TOOL_ROUNDS):
            resp = llm(messages)
            if resp.stop_reason == "refusal":
                reply_text = "Xin lỗi, mình không thể xử lý yêu cầu này. Bạn thử diễn đạt lại nhé."
                break
            messages.append({"role": "assistant", "content": resp.content})
            tool_uses = [b for b in resp.content if b.type == "tool_use"]
            if resp.stop_reason != "tool_use" or not tool_uses:
                reply_text = "".join(b.text for b in resp.content if b.type == "text").strip()
                break
            results = []
            for tu in tool_uses:
                try:
                    args = tu.input if isinstance(tu.input, dict) else json.loads(tu.input)
                    out = executor.run(tu.name, args)
                    results.append({"type": "tool_result", "tool_use_id": tu.id, "content": out})
                except (ToolError, ValueError, TypeError) as e:
                    db.rollback()
                    results.append({"type": "tool_result", "tool_use_id": tu.id,
                                    "content": f"Lỗi: {e}", "is_error": True})
            messages.append({"role": "user", "content": results})
        else:
            reply_text = "Yêu cầu này hơi phức tạp, mình đã làm được một phần. Bạn kiểm tra lại giúp mình nhé."
    except gemini.GeminiError as e:
        raise AssistantError(str(e))
    except anthropic.AuthenticationError:
        raise AssistantError("Chưa cấu hình khoá API cho mô hình ngôn ngữ (ANTHROPIC_API_KEY).")
    except anthropic.RateLimitError:
        raise AssistantError("Hệ thống AI đang quá tải, bạn thử lại sau ít phút nhé.")
    except anthropic.APIStatusError as e:
        log.exception("LLM error")
        raise AssistantError(f"Lỗi từ dịch vụ AI ({e.status_code}).")
    except anthropic.APIConnectionError:
        raise AssistantError("Không kết nối được tới dịch vụ AI.")

    if not reply_text:
        reply_text = "Mình đã xử lý xong." if executor.actions else "Mình chưa hiểu ý bạn, bạn nói lại giúp mình nhé."

    latency = int((time.perf_counter() - started) * 1000)
    msg = ChatMessage(conversation_id=conv.id, role="assistant", text=reply_text,
                      actions=executor.actions, latency_ms=latency)
    db.add(msg)
    if conv.title == "Cuộc trò chuyện mới":
        conv.title = text[:60]
    db.commit()
    db.refresh(msg)
    log.info("chat user=%s latency=%dms actions=%s", user.id, latency, _actions_summary(executor.actions))
    return msg, executor.pending
