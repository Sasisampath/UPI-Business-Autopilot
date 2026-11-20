"""Time helpers. Timestamps are stored as naive UTC; business days are Asia/Kolkata."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

_frozen: datetime | None = None


def freeze(at: datetime | None) -> None:
    """Test hook: pin `now()` to a naive-UTC instant (None to unfreeze)."""
    global _frozen
    _frozen = at


def now() -> datetime:
    if _frozen is not None:
        return _frozen
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_ist(ts: datetime) -> datetime:
    return ts.replace(tzinfo=timezone.utc).astimezone(IST)


def today_ist() -> date:
    return to_ist(now()).date()


def ist_day_bounds(day: date) -> tuple[datetime, datetime]:
    """Naive-UTC [start, end) of an IST calendar day."""
    start = datetime.combine(day, time.min, tzinfo=IST).astimezone(timezone.utc).replace(tzinfo=None)
    return start, start + timedelta(days=1)


def ist_at(day: date, hour: int, minute: int = 0) -> datetime:
    """Naive-UTC instant for a wall-clock time on an IST day."""
    return datetime.combine(day, time(hour, minute), tzinfo=IST).astimezone(timezone.utc).replace(tzinfo=None)


def iso(ts: datetime | None) -> str | None:
    return None if ts is None else ts.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
