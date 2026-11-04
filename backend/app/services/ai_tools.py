"""Định nghĩa công cụ (tool) cho LLM và bộ thực thi tương ứng.

Mỗi công cụ ánh xạ tới một thao tác nghiệp vụ trong task_service. Thao tác xoá không chạy ngay mà
tạo PendingAction để người dùng xác nhận trên giao diện (cơ chế xác nhận thao tác).
"""
import json
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import PendingAction, Priority, Task, TaskStatus, User
from ..timeutil import to_local_str
from . import gmail
from . import google_calendar as gc
from . import task_service as ts


def _nullable(t: str, **extra) -> dict:
    return {"type": [t, "null"], **extra}


# Dùng giá trị "none" thay cho null trong enum để schema strict đơn giản và rõ ràng
_PRIORITY = {"type": "string", "enum": ["low", "medium", "high", "none"]}
_STATUS = {"type": "string", "enum": ["todo", "in_progress", "done", "none"]}
_DT_DESC = "Thời điểm theo giờ Việt Nam, định dạng ISO 8601 'YYYY-MM-DDTHH:MM' (không kèm múi giờ)."

TOOLS: list[dict] = [
    {
        "name": "create_task",
        "description": "Tạo một công việc mới cho người dùng. Dùng khi người dùng muốn thêm/ghi lại một việc cần làm.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["title", "description", "due_at", "priority"],
            "properties": {
                "title": {"type": "string", "description": "Tên công việc ngắn gọn, viết hoa chữ cái đầu."},
                "description": _nullable("string", description="Mô tả thêm nếu có, ngược lại null."),
                "due_at": _nullable("string", description="Hạn chót. " + _DT_DESC + " null nếu không có hạn."),
                "priority": {**_PRIORITY, "description": "Mức ưu tiên. 'none' nếu người dùng không nói (mặc định medium)."},
            },
        },
    },
    {
        "name": "list_tasks",
        "description": "Tra cứu danh sách công việc theo bộ lọc. Dùng để trả lời câu hỏi về công việc, "
                       "hoặc để tìm id công việc trước khi sửa/xoá.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["status", "priority", "due_from", "due_to", "search", "overdue"],
            "properties": {
                "status": _STATUS,
                "priority": _PRIORITY,
                "due_from": _nullable("string", description="Lọc hạn từ thời điểm này. " + _DT_DESC),
                "due_to": _nullable("string", description="Lọc hạn đến thời điểm này. " + _DT_DESC),
                "search": _nullable("string", description="Từ khoá tìm trong tên/mô tả."),
                "overdue": {"type": "boolean", "description": "true để chỉ lấy việc đã quá hạn mà chưa xong."},
            },
        },
    },
    {
        "name": "update_task",
        "description": "Cập nhật một công việc đã có (đổi tên, hạn, mức ưu tiên, trạng thái, ví dụ đánh dấu hoàn thành). "
                       "Trường nào không đổi thì để null (với priority/status dùng 'none').",
        "strict": True,
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["task_id", "title", "description", "due_at", "priority", "status"],
            "properties": {
                "task_id": {"type": "integer"},
                "title": _nullable("string"),
                "description": _nullable("string"),
                "due_at": _nullable("string", description=_DT_DESC),
                "priority": _PRIORITY,
                "status": _STATUS,
            },
        },
    },
    {
        "name": "delete_task",
        "description": "Yêu cầu xoá một công việc. Hệ thống sẽ hiện nút để người dùng xác nhận, việc chưa bị xoá ngay.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["task_id"],
            "properties": {"task_id": {"type": "integer"}},
        },
    },
    {
        "name": "set_reminder",
        "description": "Đặt nhắc nhở vào một thời điểm, có thể gắn với một công việc.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["remind_at", "message", "task_id"],
            "properties": {
                "remind_at": {"type": "string", "description": _DT_DESC},
                "message": {"type": "string", "description": "Nội dung nhắc nhở."},
                "task_id": _nullable("integer", description="Id công việc liên quan, hoặc null."),
            },
        },
    },
    {
        "name": "check_emails",
        "description": "Đọc hộp thư Gmail của người dùng: liệt kê email chưa đọc trong 3 ngày gần đây theo nhóm "
                       "(cần trả lời, đọc sau, thông báo, quảng cáo) và tóm tắt các email quan trọng. "
                       "Dùng khi người dùng hỏi về email, thư, hộp thư.",
        "strict": True,
        "input_schema": {"type": "object", "additionalProperties": False, "required": [], "properties": {}},
    },
    {
        "name": "get_statistics",
        "description": "Lấy thống kê tiến độ: số việc theo trạng thái, quá hạn, đến hạn hôm nay/tuần này, tỉ lệ hoàn thành.",
        "strict": True,
        "input_schema": {"type": "object", "additionalProperties": False, "required": [], "properties": {}},
    },
]


def task_to_dict(t: Task) -> dict:
    return {
        "id": t.id,
        "title": t.title,
        "description": t.description,
        "due_at": to_local_str(t.due_at),
        "priority": t.priority.value,
        "status": t.status.value,
    }


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)  # không có tz -> as_utc coi là giờ Việt Nam


class ToolError(Exception):
    pass


class ToolExecutor:
    def __init__(self, db: Session, user: User):
        self.db = db
        self.user = user
        self.actions: list[dict] = []          # nhật ký hành động trong lượt này
        self.pending: list[dict] = []          # hành động chờ xác nhận

    def run(self, name: str, args: dict) -> str:
        args = {k: (None if v == "none" and k in ("priority", "status") else v) for k, v in args.items()}
        handler = getattr(self, f"_t_{name}", None)
        if handler is None:
            raise ToolError(f"Công cụ không tồn tại: {name}")
        result = handler(**args)
        return json.dumps(result, ensure_ascii=False)

    def _own(self, task_id: int) -> Task:
        task = ts.get_task(self.db, self.user, task_id)
        if task is None:
            raise ToolError(f"Không tìm thấy công việc id={task_id}. Hãy dùng list_tasks để tìm đúng id.")
        return task

    def _t_create_task(self, title, description=None, due_at=None, priority=None):
        task = ts.create_task(self.db, self.user, title=title, description=description, due_at=_dt(due_at),
                              priority=Priority(priority or "medium"))
        data = task_to_dict(task)
        self.actions.append({"type": "create_task", "task": data})
        cal = gc.calendar_state(self.db, self.user.id, task_id=task.id) if task.due_at else None
        return {"ok": True, "task": data, "calendar": cal}

    def _t_list_tasks(self, status=None, priority=None, due_from=None, due_to=None, search=None, overdue=False):
        tasks = ts.list_tasks(self.db, self.user, status=status, priority=priority, due_from=_dt(due_from),
                              due_to=_dt(due_to), search=search, overdue=overdue, limit=50)
        data = [task_to_dict(t) for t in tasks]
        self.actions.append({"type": "list_tasks", "count": len(data),
                             "filters": {k: v for k, v in dict(status=status, priority=priority, due_from=due_from,
                                         due_to=due_to, search=search, overdue=overdue).items() if v}})
        return {"count": len(data), "tasks": data}

    def _t_update_task(self, task_id, title=None, description=None, due_at=None, priority=None, status=None):
        task = self._own(task_id)
        fields = {k: v for k, v in dict(title=title, description=description, priority=priority,
                                        status=status).items() if v is not None}
        if due_at is not None:
            fields["due_at"] = _dt(due_at)
        if not fields:
            raise ToolError("Không có trường nào để cập nhật.")
        ts.update_task(self.db, task, **fields)
        data = task_to_dict(task)
        self.actions.append({"type": "update_task", "task": data, "changed": sorted(fields)})
        cal = gc.calendar_state(self.db, self.user.id, task_id=task.id) if task.due_at else None
        return {"ok": True, "task": data, "calendar": cal}

    def _t_delete_task(self, task_id):
        task = self._own(task_id)
        pa = PendingAction(user_id=self.user.id, kind="delete_task", payload={"task_id": task.id},
                           summary=f"Xoá công việc \"{task.title}\"")
        self.db.add(pa)
        self.db.commit()
        item = {"id": pa.id, "kind": pa.kind, "summary": pa.summary}
        self.pending.append(item)
        self.actions.append({"type": "delete_task_requested", "task": task_to_dict(task)})
        return {"ok": True, "requires_confirmation": True,
                "note": "Đã gửi yêu cầu xác nhận xoá tới người dùng. Công việc CHƯA bị xoá."}

    def _t_set_reminder(self, remind_at, message, task_id=None):
        if task_id is not None:
            self._own(task_id)
        r = ts.create_reminder(self.db, self.user, message=message, remind_at=_dt(remind_at), task_id=task_id)
        data = {"id": r.id, "message": r.message, "remind_at": to_local_str(r.remind_at), "task_id": task_id}
        self.actions.append({"type": "set_reminder", "reminder": data})
        cal = gc.calendar_state(self.db, self.user.id, reminder_id=r.id) if task_id is None else None
        return {"ok": True, "reminder": data, "calendar": cal}

    def _t_check_emails(self):
        try:
            items = gmail.enrich(self.db, self.user.id, gmail.list_inbox(self.db, self.user.id))
        except gc.GoogleError as e:
            raise ToolError(str(e))
        counts = {gmail.LABELS[k]: sum(i["category"] == k for i in items) for k in gmail.LABELS}
        important = [{"subject": i["subject"], "from": i["from"], "category": gmail.LABELS[i["category"]],
                      "summary": i["summary"] or i["snippet"]} for i in items if i["important"]]
        self.actions.append({"type": "check_emails", "count": len(items), "important": len(important)})
        return {"total_unread": len(items), "counts": counts, "important": important[:8]}

    def _t_get_statistics(self):
        s = ts.stats(self.db, self.user)
        self.actions.append({"type": "get_statistics"})
        return s
