from langchain.chains import LLMChain, StuffDocumentsChain
from db.vector_store import retriever
from langchain.memory import ConversationBufferMemory
from langchain.prompts.prompt import PromptTemplate
from typing import  Dict
from langchain.chains.base import Chain
from utils.prompt import prompt_template
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
    # first_interaction = True

    @staticmethod
    def predict(message: str, history: str = None):
        print(f"Retrieving documents for question: {message}")
        docs = get_docs(message)
        print(
            f"Retrieved {len(docs)} documents for question: {message}. -------------------{docs}"
        )
        response = chain.invoke({"input_documents": docs, "question": message})
        # if GetAnswer.first_interaction == True:
        #     response[
        #         'output_text'] = "Hello, I am the University of Osnabrück chatbot. I can answer questions about studying at the University of Osnabrück.\n " + \
        #                          response['output_text']
        #     # response = chain.invoke({"input": message})
        #     GetAnswer.first_interaction = False
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
