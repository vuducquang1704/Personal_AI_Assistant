from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .config import get_settings


def local_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime | None) -> datetime | None:
    """Chuẩn hoá datetime về UTC có timezone. Datetime không có tz được coi là giờ địa phương."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=local_tz())
    return dt.astimezone(timezone.utc)


def from_db(dt: datetime | None) -> datetime | None:
    """SQLite trả về datetime naive (UTC); PostgreSQL trả về aware."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def to_local_str(dt: datetime | None) -> str | None:
    dt = from_db(dt)
    return dt.astimezone(local_tz()).strftime("%Y-%m-%d %H:%M") if dt else None
