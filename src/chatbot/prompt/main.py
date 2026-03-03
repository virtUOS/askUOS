from typing import Dict, List, Literal

from langchain_core.messages import SystemMessage

import src.chatbot.prompt.prompt_text as text

# from src.chatbot.agents.utils.agent_helpers import llm
from src.chatbot.agents.utils.agent_helpers import llm_gemini
from src.chatbot_log.chatbot_logger import logger
from src.config.core_config import settings


def translate_prompt(language: Literal["Deutsch", "English"]= "Deutsch") -> Dict[str, str]:
    """
    Translates the prompt text based on the configured language.

    Returns:
        A dictionary containing the translated prompt text.
    """

    #if settings.language == "Deutsch":
    if language == "Deutsch":
        prompt_text = text.prompt_text_deutsch
    #elif settings.language == "English":
    elif language == "English":
        prompt_text = text.prompt_text_english
    else:
        prompt_text = text.prompt_text_deutsch

        logger.warning(
            f'Language "{settings.language}" not supported. Defaulting to "Deutsch"'
        )
    return prompt_text


def get_system_prompt(
    user_input: str, current_date: str, language: Literal["Deutsch", "English"]= "Deutsch"
) -> List:
    """
    Generates a chat prompt template based on the provided prompt text.

    """

    prompt_text = translate_prompt(language)
    system_message_text = prompt_text["system_message"].format(
        current_date,
        user_input,
    )
    return [SystemMessage(content=system_message_text)]


def get_prompt_length() -> int:
    """
    Calculates the length of the prompt based on the provided text.

    Returns:
        int: The length of the prompt (in tokens).

    """

    prompt_text = translate_prompt()

    # formula to roughly compute the number of tokens: https://stackoverflow.com/questions/70060847/how-to-work-with-openai-maximum-context-length-is-2049-tokens

    num_prompt_tokens = llm_gemini().get_num_tokens(prompt_text["system_message"])

    return num_prompt_tokens
