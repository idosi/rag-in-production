"""Daily dollar limit: a circuit breaker for money.

The rate limiter (security.py) caps requests per minute, not dollars. A leaked key or a
loop bug could still burn the budget at a "legal" pace. Once today's spend reaches
`daily_budget`, guarded.py refuses new (uncached) questions until midnight UTC.
Per process: with N containers the real daily cap is N times this number.

Written by Ido as exercise 3c-1. Moved here with one change: a threading.Lock.
"""

import threading
import time
from collections.abc import Callable


class SpendTracker:
    def __init__(self, daily_budget: float, clock: Callable[[], float] = time.time):
        self.daily_budget = daily_budget
        self.clock = clock
        self.current_spend = 0.0
        self.current_day = int(self.clock() // 86400)  # 86400 = seconds in a day
        self._lock = threading.Lock()  # FastAPI runs /ask in several threads

    def _roll(self) -> None:
        """Check if the day changed, and reset current_spend if so."""
        now_day = int(self.clock() // 86400)
        if now_day != self.current_day:
            self.current_day = now_day
            self.current_spend = 0.0

    def record(self, cost: float) -> None:
        if cost < 0:
            raise ValueError("cost must be non-negative")
        with self._lock:
            self._roll()
            self.current_spend += cost

    def spent_today(self) -> float:
        with self._lock:
            self._roll()
            return self.current_spend

    def allow(self) -> bool:
        return self.spent_today() < self.daily_budget
