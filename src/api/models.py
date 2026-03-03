from pydantic import BaseModel
from typing import Literal
from src.config.core_config import settings

class ChatRequest(BaseModel):
    message: str
    thread_id: str
    language: Literal["Deutsch", "English"] = "Deutsch"