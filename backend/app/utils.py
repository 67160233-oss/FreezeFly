from datetime import datetime, timezone


def utcnow() -> datetime:
    """เวลา UTC แบบ naive (ไม่มี tzinfo) ให้เข้ากับข้อมูลเดิมใน SQLite
    ใช้แทน datetime.utcnow() ที่ถูก deprecate ใน Python 3.12"""
    return datetime.now(timezone.utc).replace(tzinfo=None)