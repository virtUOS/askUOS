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


def get_milvus_client_retriever(collection_name: str) -> VectorStoreRetriever:

    vector_store = Milvus(
        embedding_function=embeddings,
        connection_args={
            "uri": URI,
        },
        collection_name=collection_name,
    )

    retriever = vector_store.as_retriever(search_type="mmr", search_kwargs={"k": 7})

    return retriever


# web_index_retriever = get_milvus_client_retriever("web_index")

# print()
# # Example usage:
# results = web_index_retriever.invoke(
#     "I finished my application but I did not receive a confirmation email"
# )
