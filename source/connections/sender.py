import time
from collections import deque
from source.connections.bot_factory import bot
from source.app_logging import logger

class RateLimiter:
    def __init__(self, max_calls, period):
        self.max_calls = max_calls
        self.period = period
        self.calls = deque()

    def wait(self):
        now = time.time()
        while self.calls and self.calls[0] <= now - self.period:
            self.calls.popleft()
        if len(self.calls) >= self.max_calls:
            sleep_time = self.period - (now - self.calls[0])
            if sleep_time > 0:
                logger.warn(f"Отправка сообщений приостановлена на {sleep_time}")
                time.sleep(sleep_time)
        self.calls.append(time.time())

message_rate_limiter = RateLimiter(max_calls=20, period=60.0)

def send_message_limited(*args, **kwargs):
    message_rate_limiter.wait()
    return bot.send_message(*args, **kwargs)
