from __future__ import annotations

import threading


class DebugMixin:
    def _debug(self, message: str, **fields) -> None:
        self._debug_seq += 1
        payload = " ".join(f"{key}={value}" for key, value in fields.items())
        thread_name = threading.current_thread().name
        line = f"[DBG {self._debug_seq:05d}] {message} thread={thread_name}"
        if payload:
            line = f"{line} {payload}"
        self.logger.info(line)

    def _append_log(self, message: str) -> None:
        self.logger.info(message)
        existing = self.log_box.value or ""
        self.log_box.value = (existing + ("\n" if existing else "") + message)[-12000:]
