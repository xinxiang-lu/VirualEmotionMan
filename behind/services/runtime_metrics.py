from __future__ import annotations

from collections import deque
from datetime import datetime


class RuntimeMetrics:
    def __init__(self) -> None:
        self.request_count = 0
        self.error_count = 0
        self.total_duration_ms = 0.0
        self.logs: deque[dict] = deque(maxlen=50)

    def record_request(self, path: str, method: str, status_code: int, duration_ms: float) -> None:
        self.request_count += 1
        self.total_duration_ms += duration_ms
        if status_code >= 400:
            self.error_count += 1

        if status_code >= 500:
            level = "异常"
            message = f"{method} {path} 返回 {status_code}，需要排查错误栈。"
        elif status_code >= 400:
            level = "警告"
            message = f"{method} {path} 返回 {status_code}，请求被拒绝或参数异常。"
        else:
            level = "正常"
            message = f"{method} {path} 正常完成，耗时 {duration_ms:.0f}ms。"

        self.logs.appendleft(
            {
                "id": f"log-{self.request_count}",
                "level": level,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "message": message,
            }
        )

    @property
    def average_response_time_ms(self) -> int:
        if self.request_count == 0:
            return 0
        return round(self.total_duration_ms / self.request_count)

    def latest_logs(self, limit: int = 8) -> list[dict]:
        return list(self.logs)[:limit]
