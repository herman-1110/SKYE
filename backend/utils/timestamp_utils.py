from datetime import datetime, timezone


def utcnow_iso() -> str:
    """Return current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def parse_iso(ts: str) -> datetime:
    """Parse an ISO 8601 string to a timezone-aware datetime."""
    return datetime.fromisoformat(ts)


def seconds_between(earlier: str, later: str) -> float:
    """Return elapsed seconds between two ISO 8601 timestamps."""
    return (parse_iso(later) - parse_iso(earlier)).total_seconds()
