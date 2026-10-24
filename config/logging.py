"""Định dạng log JSON để Alloy/Loki dễ dàng truy vấn.

Chỉ các trường an toàn trong whitelist mới được đưa vào log. Không ghi
mật khẩu, token, session, query string hoặc dữ liệu cá nhân nhạy cảm.
"""
import json
import logging
from datetime import datetime, timezone

SAFE_EXTRA_FIELDS = (
    "event_id",
    "registration_id",
    "ticket_id",
    "actor_id",
    "quantity",
    "status_code",
    "method",
    "path",
    "duration_ms",
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in SAFE_EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # ensure_ascii=True giữ log JSON an toàn trên mọi console (kể cả Windows
        # dùng cp1252). Loki vẫn parse và hiển thị đúng tiếng Việt sau khi decode.
        return json.dumps(payload, ensure_ascii=True, default=str)
