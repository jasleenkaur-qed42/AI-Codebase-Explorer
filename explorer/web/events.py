import asyncio
import json
import time
from collections import deque

MAX_HISTORY = 20


class EventBus:
    def __init__(self):
        self._subscribers: list[asyncio.Queue] = []
        self._history: deque = deque(maxlen=MAX_HISTORY)

    def publish(self, event: dict) -> dict:
        event = {**event, "timestamp": time.time()}
        self._history.append(event)
        for queue in self._subscribers:
            queue.put_nowait(event)
        return event

    def recent(self) -> list:
        return list(self._history)

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    async def stream(self, queue: asyncio.Queue):
        try:
            yield ": connected\n\n"
            for event in self.recent():
                yield f"data: {json.dumps(event)}\n\n"
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            self.unsubscribe(queue)
