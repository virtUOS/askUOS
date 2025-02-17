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
# results = web_index_retriever.invoke(
#     "I finished my application but I did not receive a confirmation email"
# )

# Example
# results[0]
# [Document(metadata={
#     'page': 21,
#     'pk': '40a0a328-5ba7-415b-bef9-893d996cb160',
#     'source'...o \nRequirements for participation  None'), Document(metadata={'page': 6, 'pk': '0e976935-15bc-46bc-af3a-83995732107f', 'source':...onsideration in the selection procedure.'), Document(metadata={'page': 128, 'pk': 'bf96418c-0e82-4d66-8964-592bc7d4b0cb', 'source...y requirements for participation  \nnone'), Document(metadata={'page': 20, 'pk': 'bb4e3774-591f-48ad-86be-70275a893a5e', 'source'...ion to a problem was judged incorrect or"), Document(metadata={'page': 4, 'pk': 'd9f25985-debf-4432-bf2c-f1fd728e5a72', 'source':...sten berufsqualifizierenden Abschlüssen,'), Document(metadata={'page': 14, 'pk': '2fea2926-558d-4275-b3b5-e6e6d32c03dc', 'source'...nce  (mandatory  module  / Pflichtmodul)'), Document(metadata={'page': 7, 'pk': 'bdf13523-8b68-4bfb-9f89-e62f505f91e2', 'source':...The provision in accordance with Section')]

# print(results[0])
# page_content='22
# Does the examination grade
# count towards the final grade?  No
# Requirements for participation  None' metadata={'page': 21, 'pk': '40a0a328-5ba7-415b-bef9-893d996cb160', 'source': 'data/documents/Modulbeschreibungen_ConflictStudiesPeacebuilding_EN_2021-03.pdf'}
