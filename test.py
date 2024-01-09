from langchain_community.chat_models import ChatOllama
from langchain.schema import HumanMessage
from langchain.prompts.chat import ChatPromptTemplate
from langchain.output_parsers import CommaSeparatedListOutputParser

chat_model = ChatOllama()

# text = "how can I apply to a german university?"
# messages = [HumanMessage(content=text)]
#
#
#
# print(chat_model.invoke(messages))



output_parser = CommaSeparatedListOutputParser()



template = "You work for a german university as an advisor who supports prospect students with their application process. Answer the following query: {text}.\n\n{format_instructions}"

chat_prompt = ChatPromptTemplate.from_template(template)
chat_prompt = chat_prompt.partial(format_instructions=output_parser.get_format_instructions())
chain = chat_prompt | chat_model
result = chain.invoke({"text": "I am an international student and I want to apply to a german university. What do I need to do?"})
# >> ['red', 'blue', 'green', 'yellow', 'orange']

print(result)

# template = "You are a helpful assistant that works at a german univesity. You help students with their questions about the application process."
# human_template = "{text}"
#
# chat_prompt = ChatPromptTemplate.from_messages([
#     ("system", template),
#     ("human", human_template),
# ])
#
# chat_prompt.format_messages( text="I am an international student and I want to apply to a german university. What do I need to do?")
# chain = chat_prompt | chat_model
#
# chain.invoke()
print('Finished running code')