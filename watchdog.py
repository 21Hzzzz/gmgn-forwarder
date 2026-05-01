import time


class Watchdog:
    def __init__(self, timeout: int) -> None:
        self.timeout = timeout
        self.last_msg_time = time.time()

    def feed(self) -> None:
        self.last_msg_time = time.time()

    def is_timed_out(self) -> bool:
        return self.time_since_last_msg() > self.timeout

    def time_since_last_msg(self) -> float:
        return time.time() - self.last_msg_time
