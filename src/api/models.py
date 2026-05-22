import uuid
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from src.config.core_config import settings
from src.config.models import Languages


class ChatRequest(BaseModel):
    message: str
    thread_id: str
    language: Literal["Deutsch", "English"] = "Deutsch"


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "askUOS-agent"
    messages: List[Message]
    stream: bool = False
    thread_id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()))
    language: Literal[Languages.GERMAN, Languages.ENGLISH] = Languages.GERMAN
    keep_user_message_history: bool = (
        False  # wather to keep the list of messages shown to the user (sent to the client)
    )
    # Optional OpenAI-compatible fields (ignored but accepted)
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
