from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_serializer

from .models import Priority, TaskStatus
from .timeutil import from_db


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Auth ----------
class RegisterIn(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=6, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class VoiceSettings(BaseModel):
    voice: str | None = None
    rate: float = Field(1.0, ge=0.5, le=2.0)
    pitch: float = Field(1.0, ge=0.0, le=2.0)
    auto_speak: bool = True


class UserOut(_Out):
    id: int
    email: str
    full_name: str
    voice_settings: dict
    created_at: datetime


class UserUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=255)
    voice_settings: VoiceSettings | None = None


class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=128)


# ---------- Tasks ----------
class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    due_at: datetime | None = None
    priority: Priority = Priority.medium
    status: TaskStatus = TaskStatus.todo


class TaskUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    due_at: datetime | None = None
    priority: Priority | None = None
    status: TaskStatus | None = None


class TaskOut(_Out):
    id: int
    title: str
    description: str | None
    due_at: datetime | None
    priority: Priority
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

    @field_serializer("due_at", "created_at", "updated_at", "completed_at")
    def _ser_dt(self, v: datetime | None):
        v = from_db(v)
        return v.isoformat() if v else None


# ---------- Reminders ----------
class ReminderIn(BaseModel):
    task_id: int | None = None
    message: str = Field(min_length=1, max_length=500)
    remind_at: datetime


class ReminderOut(_Out):
    id: int
    task_id: int | None
    message: str
    remind_at: datetime
    fired_at: datetime | None
    seen: bool

    @field_serializer("remind_at", "fired_at")
    def _ser_dt(self, v: datetime | None):
        v = from_db(v)
        return v.isoformat() if v else None


# ---------- Chat ----------
class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: int | None = None
    input_mode: str = Field("text", pattern="^(text|voice)$")


class ChatMessageOut(_Out):
    id: int
    role: str
    text: str
    input_mode: str
    actions: list
    created_at: datetime

    @field_serializer("created_at")
    def _ser_dt(self, v: datetime):
        return from_db(v).isoformat()


class ChatOut(BaseModel):
    conversation_id: int
    reply: ChatMessageOut
    pending_actions: list[dict] = []


class ConversationOut(_Out):
    id: int
    title: str
    created_at: datetime


class StatsOut(BaseModel):
    total: int
    todo: int
    in_progress: int
    done: int
    overdue: int
    due_today: int
    due_this_week: int
    by_priority: dict[str, int]
    completion_rate: float
    completed_last_7_days: list[dict]
