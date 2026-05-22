import time
from contextlib import contextmanager
from threading import BoundedSemaphore, Lock


class RateLimiter:
    def __init__(self, min_delay_seconds: float, max_concurrent: int) -> None:
        self.min_delay_seconds = min_delay_seconds
        self._semaphore = BoundedSemaphore(max_concurrent)
        self._lock = Lock()
        self._last_request_time = 0.0

    @contextmanager
    def limit(self):
        self.acquire()
        try:
            yield
        finally:
            self.release()

    def acquire(self) -> None:
        self._semaphore.acquire()
        self._wait_for_delay()

    def release(self) -> None:
        self._semaphore.release()

    def _wait_for_delay(self) -> None:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < self.min_delay_seconds:
                time.sleep(self.min_delay_seconds - elapsed)
            self._last_request_time = time.monotonic()
