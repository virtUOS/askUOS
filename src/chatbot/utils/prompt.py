from typing import Optional, Union
from langchain_core.prompts import SystemMessagePromptTemplate
from langchain.prompts.prompt import PromptTemplate
from langchain.prompts.chat import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    MessagesPlaceholder,
)


def get_prompt(prompt_text: dict[str, str]) -> ChatPromptTemplate:
    """
    Generates a chat prompt template based on the provided prompt text.

    Args:
        prompt_text (Dict[str, str]): A dictionary containing the prompt text.

    Returns:
        ChatPromptTemplate: The generated chat prompt template.
    """

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
