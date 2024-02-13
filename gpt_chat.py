from langchain.chains import LLMChain, StuffDocumentsChain
from langchain_core.prompts import SystemMessagePromptTemplate
from vector_store import retriever
from langchain.prompts.prompt import PromptTemplate
from langchain.memory import ConversationBufferMemory
from typing import  Dict
from langchain.chains.base import Chain
from langchain.prompts.chat import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    MessagesPlaceholder,
)
import gradio as gr
import dotenv
dotenv.load_dotenv()

from langchain_openai import ChatOpenAI

print('package imported')


# todo tune the temperature so that the model is not too talkative
# model
# chat_model = ChatOllama(
#     model="llama2:13b-chat",
# )

chat_model = ChatOpenAI(
    model="gpt-3.5-turbo-1106",
)

# todo summarize the context, all the texts in the cotext are appended to the prompt. long prompts tak long time to process
"""
this is what the prompt looks like once rendered:

[ChatPromptValue(messages=[SystemMessage(content='You work for a german university as an advisor who supports prospect students with their application process.\n                           Provide answers in German if the student asks in German, and in English if the student asks in English.\n                             The AI is talkative and provides lots of specific details from its context.\n                          If the AI does not know the answer to a question, it truthfully says it does not know.\n                Answer any user questions based solely on the context below:\n\n<context>\nBitte lesen Sie alle folgenden Hinweise zum Bewerber-Login aufmerksam durch.\n2.3.1 E-Mail-Verifikation\n\nNach der erstmaligen Registrierung in unserem Portal bekommen Sie eine Registrierungsmail mit Ihrer Benutzungsrkennung und einem Freischaltcode bzw. Verifizierungslink. Bitte vergessen Sie nicht Ihre Registrierung zu verifizieren.\n2.3.2 Über welche Funktion melde ich mich an?\n\n1.1 Welche Browser werden derzeit unterstützt?\n\nWenn Sie das Bewerbungsportal mit dem Browser „Microsoft Edge“ benutzen, funktionieren einige Funktionen derzeit nicht. Bitte benutzen Sie einen anderen Browser, wie z.B. Mozilla Firefox, Internet Explorer oder Chrome.\nZurück nach oben\n2 Probleme bei der Registrierung / mit dem Login\n\n2.1 Bei der erstmaligen Registrierung, nach dem Klick auf „Registrieren“, komme ich nicht weiter. Die Seite wird ohne Fehler nochmal geladen. Wieso?\n</context>'), HumanMessage(content='Name three study programs at the University')])]

You are an AI assistant for the University of Osnabrueck Germany. You support prospect students with their application process. The University website is https://www.uni-osnabrueck.de/startseite.
You are given the following extracted parts of a long document and a question. Provide a conversational answer with a hyperlink to the documentation.
You should only use hyperlinks that are explicitly listed as a source in the context. Do NOT make up a hyperlink that is not listed.

If you don't know the answer, just say "Hmm, I'm not sure." Don't try to make up an answer.
If the question is not about LangChain, politely inform them that you are tuned to only answer questions about LangChain.
Question: {question}
=========
{context}
=========


"""

# \n\n<chat history>\n{chat_history}\n</chat history>

template_messages = [SystemMessagePromptTemplate(prompt=PromptTemplate(input_variables=['context', 'chat_history'],
                                                                       template="""You work for a german university as an advisor who 
                                                                       supports prospect students with their application process.
                           Provide answers in German if the student asks in German, and in English if the student asks in English.
                             Do not greet the user. Avoid using greetings. The AI is talkative and provides specific details from its context. 
                          If the AI does not know the answer to a question, it truthfully says it does not know. If the user asks question which are not about University studies in Germany, the AI will say it does not know.
                Answer any user questions based solely on the context and chat history provided below. If the context doesn't contain any relevant information to the question, don't make something up and just say "I don't know.
                \n\n<context>\n{context}\n</context> \n\n<chat history>\n{chat_history}\n</chat history> """)),
                     MessagesPlaceholder(variable_name='chat_history'),
                     HumanMessagePromptTemplate(prompt=PromptTemplate(input_variables=['question'], template='{question}'))]



prompt_template = ChatPromptTemplate.from_messages(template_messages)

# todo choose a memory that reduces the chat_history
memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

# prompt_template2 = hub.pull("langchain-ai/retrieval-qa-chat")

retriever = retriever


# stuff documents

document_prompt = PromptTemplate(
    input_variables=["page_content"],
    template="{page_content}" # refers to the input variable page_content
)

# The variable name in the llm_chain to put the documents in.
document_variable_name = "context"



llm_combine_chain = LLMChain(llm=chat_model, prompt=prompt_template)



def get_docs(question):
    """Get docs."""
    docs = retriever.get_relevant_documents(
        question
    )
    return docs





class ChainM(StuffDocumentsChain, Chain):
    def prep_outputs(
            self,
            inputs: Dict[str, str],
            outputs: Dict[str, str],
            return_only_outputs: bool = False,
    ) -> Dict[str, str]:
        """Validate and prepare chain outputs, and save info about this run to memory.

        Args:
            inputs: Dictionary of chain inputs, including any inputs added by chain
                memory.
            outputs: Dictionary of initial chain outputs.
            return_only_outputs: Whether to only return the chain outputs. If False,
                inputs are also added to the final outputs.

        Returns:
            A dict of the final chain outputs.
        """
        if len(inputs.keys()) != 1:
            key = 'question' if 'question' in inputs.keys() else 'input'
            inputs = {'question':inputs[key]}
        self._validate_outputs(outputs)
        if self.memory is not None:
            self.memory.save_context(inputs, outputs)
        if return_only_outputs:
            return outputs
        else:
            return {**inputs, **outputs}




chain = ChainM(
    memory=memory,
    verbose=False,
    llm_chain=llm_combine_chain,
    document_prompt=document_prompt,
    document_variable_name=document_variable_name)


print('Chain created')



class GetAnswer():
    first_interaction = True

    @staticmethod
    def predict(message: str, history: str = None):
        print(f"Retrieving documents for question: {message}")
        docs = get_docs(message)
        print(
            f"Retrieved {len(docs)} documents for question: {message}. -------------------{docs}"
        )
        response = chain.invoke({"input_documents": docs, "question": message})
        if GetAnswer.first_interaction == True:
            response[
                'output_text'] = "Hello, I am the University of Osnabrück chatbot. I can answer questions about studying at the University of Osnabrück.\n " + \
                                 response['output_text']
            # response = chain.invoke({"input": message})
            GetAnswer.first_interaction = False
        return response['output_text']


if __name__ == "__main__":



    interface = gr.ChatInterface(
        clear_btn=None,
        fn=GetAnswer.predict,
        retry_btn=None,
        undo_btn=None,
    )

    # Launch the user interface
    interface.launch(
        height=600,
        inline=True,
        share=True,
        width=800
    )
