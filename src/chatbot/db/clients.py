import os

import dotenv

dotenv.load_dotenv()

import logging
import os
from typing import List, Optional

from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from langchain_core.vectorstores import VectorStoreRetriever
from langchain_milvus import Milvus

# Configurations
EMBEDDING_MODEL = "intfloat/multilingual-e5-large"


# Initialize embeddings
embeddings = FastEmbedEmbeddings(model_name=EMBEDDING_MODEL)

URI = os.getenv("MILVUS_URL")
MILVUS_USER = os.getenv("MILVUS_USER")
MILVUS_PASSWORD = os.getenv("MILVUS_PASSWORD")


def get_milvus_client(collection_name: str) -> Milvus:

    vector_store = Milvus(
        embedding_function=embeddings,
        connection_args={"uri": URI, "token": f"{MILVUS_USER}:{MILVUS_PASSWORD}"},
        collection_name=collection_name,
    )

    return vector_store


def get_retriever(collection_name: str) -> VectorStoreRetriever:

    vector_store = get_milvus_client(collection_name)
    retriever = vector_store.as_retriever(
        search_type="similarity", search_kwargs={"k": 5}
    )

    return retriever


print()

# web_index_retriever = get_milvus_client_retriever("web_index")

# print()
# # Example usage:
# results = retriever.invoke(
#     "I finished my application but I did not receive a confirmation email"
# )


# vector_store = Milvus(
#     embedding_function=embeddings,
#     connection_args={"uri": URI, "token": f"{MILVUS_USER}:{MILVUS_PASSWORD}"},
#     collection_name="examination_regulations",
# )


# for doc in results:
#     print(f"* {doc.page_content} [{doc.metadata}]")

# # LIKE --> infix match
# vector_store.similarity_search_with_score(
#     "master arbeit", k=1, expr='source LIKE "%Biologie%"'
# )
