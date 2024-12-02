from typing import Optional, Union, Dict
from langchain_core.prompts import SystemMessagePromptTemplate
from langchain.prompts.prompt import PromptTemplate
from langchain.prompts.chat import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    MessagesPlaceholder,
)
from src.chatbot_log.chatbot_logger import logger
import src.chatbot.utils.prompt_text as text
from src.config.core_config import settings
from src.chatbot.utils.agent_helpers import llm


def translate_prompt() -> Dict[str, str]:
    """
    Translates the prompt text based on the configured language.

    Returns:
        A dictionary containing the translated prompt text.
    """

    if settings.language == "Deutsch":
        prompt_text = text.prompt_text_deutsch
    elif settings.language == "English":
        prompt_text = text.prompt_text_english
    else:
        prompt_text = text.prompt_text_deutsch

        logger.warning(
            f'Language "{settings.language}" not supported. Defaulting to "Deutsch"'
        )
    return prompt_text


def get_prompt() -> ChatPromptTemplate:
    """
    Generates a chat prompt template based on the provided prompt text.

    Returns:
        ChatPromptTemplate: The generated chat prompt template.
    """

    prompt_text = translate_prompt()

    template_messages = [
        SystemMessagePromptTemplate(
            prompt=PromptTemplate(
                input_variables=["input", "chat_history", "agent_scratchpad"],
                template=prompt_text["system_message"],
            )
        ),
        MessagesPlaceholder(variable_name="chat_history", optional=True),
        HumanMessagePromptTemplate(
            prompt=PromptTemplate(input_variables=["input"], template="{input}")
        ),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ]

    return ChatPromptTemplate.from_messages(template_messages)


def get_prompt_length() -> int:
    """
    Calculates the length of the prompt based on the provided text.

    Returns:
        int: The length of the prompt (in tokens).

    """

    prompt_text = translate_prompt()

    # formula to roughly compute the number of tokens: https://stackoverflow.com/questions/70060847/how-to-work-with-openai-maximum-context-length-is-2049-tokens

    num_prompt_tokens = llm().get_num_tokens(prompt_text["system_message"])

    return num_prompt_tokens
