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


print()

# web_index_retriever = get_milvus_client_retriever("web_index")

# print()
# # Example usage:
# results = web_index_retriever.invoke(
#     "I finished my application but I did not receive a confirmation email"
# )

# Example
# results[0]
# Document(metadata={'pk': '6977ea0d-f95c-45c2-b6a8-854386a59084',
#                    'source': 'data/troubleshooting/application.txt'},
#          page_content='1 Technische Voraussetzungen\n1.1 Welche Browser werden derzeit unterstützt?\n\nWenn Sie das Bewerbungsportal mit dem Browser „Microsoft Edge“ benutzen, funktionieren einige Funktionen derzeit nicht. Bitte benutzen Sie einen anderen Browser, wie z.B. Mozilla Firefox, Internet Explorer oder Chrome.\n\nZurück nach oben\n\n2 Probleme bei der Registrierung / mit dem Login\n2.1 Bei der erstmaligen Registrierung, nach dem Klick auf „Registrieren“, komme ich nicht weiter. Die Seite wird ohne Fehler nochmal geladen. Wieso?\n\nWenn Sie das Bewerbungsportal mit dem Browser „Microsoft Edge“ benutzen, funktioniert die Registrierung derzeit nicht. Bitte benutzen Sie für unser Portal einen anderen Browser, wie z.B. Mozilla Firefox, Internet Explorer oder Chrome.\n\nZurück nach oben\n\n2.2 Warum bekomme ich nach der Registrierung keine Bestätigungsmail?')
