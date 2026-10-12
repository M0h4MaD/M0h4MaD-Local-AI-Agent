from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

@dataclass
class Message:
    channel: str
    sender: str
    text: str | None = None
    audio: Path | None = None

class Transport(ABC):
    @abstractmethod
    async def start(self): ...
    @abstractmethod
    async def stop(self): ...
    @abstractmethod
    async def receive(self) -> Message: ...
    @abstractmethod
    async def send(self, to: str, text: str): ...