"""Loads user-editable prompt templates from an external directory.

A git-tracked `prompts_example/` ships the default wording, and an
installer copies it to `prompts/` (gitignored, override via the PROMPTS_DIR
env var) to customize wording for their own university without touching any
Python. Layout:

    prompts/
      en/
        system_message.md
        system_message_generate.md
        system_message_generate_application.md
        system_message_generate_teaching_degree.md
        rewrite_msg_human.md
        grading_llm.md
        strings.yaml       # short tool descriptions / one-line strings
      de/
        (same files)

Loaded once at import time (module-level cache) -- picking up an edit
requires restarting/rebuilding the app, same as backend_config.yaml today.
No hot-reload/file-watching, deliberately: this app runs multiple replicas,
and "restart to pick up a config change" is the existing, well-understood
pattern rather than a new one.

Every long-form template is validated at load time against an explicit
placeholder schema (_TEMPLATE_PLACEHOLDERS below): the file must contain
*exactly* the named {placeholders} the corresponding .format(...) call site
in graph_node_edges.py will supply -- no more, no fewer. This is what makes
hand-editing these files actually safe for a non-developer: the old scheme
used positional bare {} placeholders, where reordering a paragraph past one
silently swapped which value landed where (e.g. swapping the date and the
user's query) with no error at all. Named placeholders make each slot's
meaning visible directly in the text, and a deleted/mistyped one now fails
loudly at startup ("missing placeholder: user_query") instead of silently
misbehaving or surfacing confusingly mid-conversation.
"""

import os
import string
from pathlib import Path
from typing import Dict, Set

import yaml

from src.chatbot_log.chatbot_logger import logger

_PROMPTS_DIR = os.getenv("PROMPTS_DIR", "prompts")
_EXAMPLE_DIR = "prompts_example"

_LANGUAGE_FOLDERS = {"Deutsch": "de", "English": "en"}

# Long-form templates: one markdown file per key. See module docstring for
# why the placeholder set is enforced exactly (no more, no fewer).
_TEMPLATE_PLACEHOLDERS: Dict[str, Set[str]] = {
    "system_message": {"current_date", "user_query"},
    "system_message_generate": {"current_date", "user_query", "context"},
    "system_message_generate_application": {
        "current_date",
        "user_query",
        "context",
    },
    "system_message_generate_teaching_degree": {
        "current_date",
        "user_query",
        "context",
    },
    "rewrite_msg_human": {"user_query", "tool_history"},
    "grading_llm": {"context", "question"},
}

# Short strings living in strings.yaml -- no {placeholders} expected today.
# If you add one to a value below, add its name to a set here too, or
# validation will reject it as "unexpected".
#
# Deliberately NOT here:
# - response_output_description, response_sources_description,
#   grader_binary_score, use_tool_msg -- moved to internal_prompt_text.py.
#   These are internal control-flow strings (a structured-output field
#   description, an internal nudge message), not user-facing wording a
#   university admin should be customizing.
# - HISinOne_troubleshooting_questions -- moved to backend_config.yaml
#   (graph.troubleshooting.description), since it's the description for a
#   tool that only exists when graph.troubleshooting.activate is True. See
#   docs/PROMPT_CONFIGURATION.md for the full three-tier explanation.
# - examination_regulations -- dropped entirely; only ever referenced from
#   commented-out code (the old, pre-MCP examination regulations tool).
_STRING_KEYS: Dict[str, Set[str]] = {
    "description_university_web_search": set(),
}


def _extract_placeholders(text: str) -> Set[str]:
    """Return the set of str.format() placeholders in `text`, keyed by name.

    A bare positional `{}` (the old, unsafe style this migration replaced)
    parses to field_name == "" rather than a real name -- that's kept here
    (not filtered out) precisely so a leftover one still shows up as an
    "unexpected" placeholder during validation instead of being silently
    ignored. Only literal-text segments with no placeholder at all
    (field_name is None) are excluded.
    """
    return {
        field_name
        for _, field_name, _, _ in string.Formatter().parse(text)
        if field_name is not None
    }


def _resolve_lang_dir(folder_name: str) -> Path:
    """Prefer PROMPTS_DIR; fall back to the checked-in prompts_example/ if
    an installer hasn't copied it over yet, so a fresh checkout still starts
    with sensible defaults instead of crashing on missing files."""
    primary = Path(_PROMPTS_DIR) / folder_name
    if primary.is_dir():
        return primary

    fallback = Path(_EXAMPLE_DIR) / folder_name
    if fallback.is_dir():
        logger.warning(
            f"[PROMPTS] {primary} not found; falling back to {fallback}. "
            f"Copy {_EXAMPLE_DIR}/ to {_PROMPTS_DIR}/ to customize prompts "
            f"without touching the shipped defaults.",
            extra={"tag": "PROMPTS_FALLBACK_TO_EXAMPLE", "folder": folder_name},
        )
        return fallback

    raise FileNotFoundError(
        f"[PROMPTS] No prompts directory found at {primary} or {fallback}. "
        f"Copy {_EXAMPLE_DIR}/ to {_PROMPTS_DIR}/ (or set the PROMPTS_DIR "
        f"env var) before starting the app."
    )


def _load_language(folder_name: str) -> Dict[str, str]:
    lang_dir = _resolve_lang_dir(folder_name)
    prompts: Dict[str, str] = {}

    for key, expected in _TEMPLATE_PLACEHOLDERS.items():
        path = lang_dir / f"{key}.md"
        if not path.is_file():
            raise FileNotFoundError(f"[PROMPTS] Missing required prompt file: {path}")

        text = path.read_text(encoding="utf-8").rstrip("\n")
        found = _extract_placeholders(text)
        if found != expected:
            missing = sorted(expected - found)
            unexpected = sorted(found - expected)
            raise ValueError(
                f"[PROMPTS] {path} does not have the expected placeholders. "
                f"Missing: {missing or 'none'}. Unexpected: {unexpected or 'none'}. "
                f"Expected exactly: {sorted(expected)}. Fix the file (or the "
                f"schema in prompt_loader.py if this key's placeholders were "
                f"deliberately changed, alongside its .format(...) call site "
                f"in graph_node_edges.py)."
            )
        prompts[key] = text

    strings_path = lang_dir / "strings.yaml"
    if not strings_path.is_file():
        raise FileNotFoundError(
            f"[PROMPTS] Missing required prompt file: {strings_path}"
        )

    with open(strings_path, encoding="utf-8") as f:
        strings = yaml.safe_load(f) or {}

    missing_keys = [k for k in _STRING_KEYS if k not in strings]
    if missing_keys:
        raise ValueError(
            f"[PROMPTS] {strings_path} is missing required keys: {missing_keys}"
        )

    for key, expected in _STRING_KEYS.items():
        value = strings[key]
        if not isinstance(value, str):
            raise ValueError(
                f"[PROMPTS] {strings_path}: '{key}' must be a string, got "
                f"{type(value).__name__}"
            )
        found = _extract_placeholders(value)
        if found != expected:
            raise ValueError(
                f"[PROMPTS] {strings_path}: '{key}' has unexpected "
                f"placeholders {sorted(found - expected)}; this key isn't "
                f"expected to have any today."
            )
        prompts[key] = value.rstrip("\n")

    return prompts


def load_prompts() -> Dict[str, Dict[str, str]]:
    """Load and validate every configured language's prompts. Raises loudly
    (FileNotFoundError/ValueError) on any missing file or placeholder
    mismatch. Called once at import time so a bad prompt edit fails
    application startup instead of surfacing later, mid-conversation.
    """
    loaded: Dict[str, Dict[str, str]] = {}
    for language, folder_name in _LANGUAGE_FOLDERS.items():
        loaded[language] = _load_language(folder_name)
        logger.debug(
            f"[PROMPTS] Loaded {len(loaded[language])} prompts for "
            f"'{language}' from {folder_name}/",
            extra={"tag": "PROMPTS_LOADED", "language": language},
        )
    return loaded


# Loaded once at import time -- see module docstring re: restart-to-reload.
PROMPTS_BY_LANGUAGE: Dict[str, Dict[str, str]] = load_prompts()
