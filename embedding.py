# text emebedding should run  asynchronusly. The mdoel is needed at all times to embed the user input/query.
# see https://python.langchain.com/docs/integrations/text_embedding/ollama
# to download the model using ollama run-->  ollama run llama2:13b

from langchain_community.embeddings import OllamaEmbeddings

embeddings = OllamaEmbeddings(model="llama2:13b", show_progress=True)


if __name__ == "__main__":

    # embed query
    query_result = embeddings.embed_query("I am a student")

    # embed text
    doc_result = embeddings.embed_documents(["I am a student"])

    print()



