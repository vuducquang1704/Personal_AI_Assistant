from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ChatMessage, Conversation, PendingAction, User
from ..schemas import ChatIn, ChatMessageOut, ChatOut, ConversationOut
from ..security import get_current_user
from ..services import assistant
from ..services import task_service as ts

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _conv(db: Session, user: User, conv_id: int) -> Conversation:
    conv = db.get(Conversation, conv_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(404, "Không tìm thấy cuộc trò chuyện")
    return conv


@router.post("", response_model=ChatOut)
def send(body: ChatIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.conversation_id:
        conv = _conv(db, user, body.conversation_id)
    else:
        conv = Conversation(user_id=user.id)
        db.add(conv)
        db.commit()
    try:
        msg, pending = assistant.chat(db, user, conv, body.message.strip(), body.input_mode)
    except assistant.AssistantError as e:
        raise HTTPException(503, str(e))
    return ChatOut(conversation_id=conv.id, reply=ChatMessageOut.model_validate(msg), pending_actions=pending)


@router.get("/conversations", response_model=list[ConversationOut])
def conversations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return list(db.scalars(select(Conversation).where(Conversation.user_id == user.id)
                           .order_by(Conversation.id.desc()).limit(100)))


@router.get("/conversations/{conv_id}", response_model=list[ChatMessageOut])
def messages(conv_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _conv(db, user, conv_id).messages


@router.delete("/conversations/{conv_id}", status_code=204)
def delete_conversation(conv_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(_conv(db, user, conv_id))
    db.commit()


@router.post("/actions/{action_id}/{decision}")
def decide(action_id: int, decision: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Người dùng xác nhận hoặc huỷ hành động do AI đề xuất (ví dụ xoá công việc)."""
    if decision not in ("confirm", "cancel"):
        raise HTTPException(400, "decision phải là confirm hoặc cancel")
    pa = db.get(PendingAction, action_id)
    if not pa or pa.user_id != user.id:
        raise HTTPException(404, "Không tìm thấy yêu cầu")
    if pa.status != "pending":
        raise HTTPException(409, "Yêu cầu đã được xử lý")
    if decision == "cancel":
        pa.status = "cancelled"
        db.commit()
        return {"status": "cancelled", "message": "Đã huỷ."}
    if pa.kind == "delete_task":
        task = ts.get_task(db, user, pa.payload["task_id"])
        if task:
            ts.delete_task(db, task)
    pa.status = "confirmed"
    db.commit()
    return {"status": "confirmed", "message": f"Đã thực hiện: {pa.summary}."}
