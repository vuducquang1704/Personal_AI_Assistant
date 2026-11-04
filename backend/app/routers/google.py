from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import User
from ..security import get_current_user
from ..services import google_calendar as gc

COOKIE = "google_oauth_nonce"
router = APIRouter(prefix="/api/google", tags=["google"])


class GoogleStatus(BaseModel):
    configured: bool  # máy chủ đã khai báo GOOGLE_CLIENT_ID/SECRET chưa
    connected: bool
    email: str | None = None
    sync_enabled: bool = False
    reminder_minutes: int = 30
    last_error: str | None = None


class GoogleSettingsIn(BaseModel):
    sync_enabled: bool | None = None
    reminder_minutes: int | None = Field(default=None, ge=0, le=1440)


def _status(db: Session, user: User) -> GoogleStatus:
    acc = gc.get_account(db, user.id)
    if not acc:
        return GoogleStatus(configured=gc.enabled(), connected=False)
    return GoogleStatus(configured=gc.enabled(), connected=True, email=acc.email, sync_enabled=acc.sync_enabled,
                        reminder_minutes=acc.reminder_minutes, last_error=acc.last_error)


def _require_enabled():
    if not gc.enabled():
        raise HTTPException(400, "Máy chủ chưa cấu hình GOOGLE_CLIENT_ID và GOOGLE_CLIENT_SECRET")


@router.get("/status", response_model=GoogleStatus)
def status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _status(db, user)


@router.get("/auth-url")
def get_auth_url(response: Response, user: User = Depends(get_current_user)):
    _require_enabled()
    nonce = gc.new_nonce()
    # Cookie gắn state với trình duyệt đã bấm "Kết nối"; Lax vẫn được gửi khi Google chuyển hướng về
    response.set_cookie(COOKIE, nonce, max_age=600, httponly=True, samesite="lax",
                        secure=get_settings().frontend_url.startswith("https://"), path="/api/google")
    return {"url": gc.auth_url(user, nonce)}


@router.get("/callback", include_in_schema=False)
def callback(code: str | None = None, state: str | None = None, error: str | None = None,
             google_oauth_nonce: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    """Google chuyển hướng trình duyệt về đây sau khi người dùng đồng ý."""
    front = get_settings().frontend_url.rstrip("/")
    if error or not code or not state:
        return RedirectResponse(f"{front}/settings?google=denied")
    try:
        user_id = gc.read_state(state, google_oauth_nonce)
        if not db.get(User, user_id):
            raise gc.GoogleError("Người dùng không tồn tại")
        gc.connect(db, user_id, code)
        gc.sync_all(db, db.get(User, user_id))
    except gc.GoogleError:
        return RedirectResponse(f"{front}/settings?google=error")
    resp = RedirectResponse(f"{front}/settings?google=connected")
    resp.delete_cookie(COOKIE, path="/api/google")
    return resp


@router.patch("", response_model=GoogleStatus)
def update(body: GoogleSettingsIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    acc = gc.get_account(db, user.id)
    if not acc:
        raise HTTPException(404, "Chưa kết nối Google")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        if v is not None:
            setattr(acc, k, v)
    db.commit()
    if data.get("sync_enabled") or "reminder_minutes" in data:
        gc.sync_all(db, user)
    return _status(db, user)


@router.post("/sync")
def sync(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_enabled()
    if not gc.get_account(db, user.id):
        raise HTTPException(404, "Chưa kết nối Google")
    return {"synced": gc.sync_all(db, user), **_status(db, user).model_dump()}


@router.delete("", status_code=204)
def disconnect(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    gc.disconnect(db, user.id)


# ---------------------------------------------------------------- Email

def _emails(db: Session, user: User) -> list[dict]:
    from ..services import gmail
    _require_enabled()
    try:
        return gmail.list_inbox(db, user.id)
    except gc.GoogleError as e:
        raise HTTPException(400, str(e))
    except Exception:
        raise HTTPException(502, "Không kết nối được tới Gmail, bạn thử lại sau")


@router.get("/emails")
def emails(summarize: bool = False, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Email chưa đọc 3 ngày gần đây, đã phân loại; summarize=true thì AI tóm tắt các email quan trọng."""
    from ..services import gmail
    items = _emails(db, user)
    if summarize:
        gmail.enrich(db, user.id, items)
    counts = {k: sum(i["category"] == k for i in items) for k in gmail.LABELS}
    return {"items": items, "counts": counts, "labels": gmail.LABELS,
            "important": sum(i["important"] for i in items)}


@router.post("/emails/tasks")
def email_tasks(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Tạo việc 'Trả lời ...' (hạn 17:00 hôm nay) cho các email cần trả lời chưa có việc."""
    from ..services import gmail
    created = gmail.make_tasks(db, user, _emails(db, user))
    return {"created": len(created), "titles": [t.title for t in created]}
