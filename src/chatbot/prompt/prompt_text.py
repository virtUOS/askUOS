"""Prompt content used to live here directly as two large hardcoded Python
dicts (~15 keys each, some 100+ lines of raw triple-quoted text). That made
even a small wording tweak require editing Python source and rebuilding the
Docker image, and several prompts used positional `{}` placeholders where
reordering a paragraph could silently swap which value landed where.

The actual content now lives in external, user-editable files (see
`prompt_loader.py` and the `prompts/` / `prompts_example/` directories).
This module just exposes the loaded result under the same two names as
before, so `prompt/main.py` (the only importer) needs no changes.
"""

from src.chatbot.prompt.prompt_loader import PROMPTS_BY_LANGUAGE

prompt_text_english = PROMPTS_BY_LANGUAGE["English"]
prompt_text_deutsch = PROMPTS_BY_LANGUAGE["Deutsch"]
