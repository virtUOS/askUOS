import argparse
import os
import pickle

import chromadb
from chromadb.config import Settings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from langchain_community.embeddings.sentence_transformer import (
    SentenceTransformerEmbeddings,
)
from langchain_community.vectorstores import Chroma
from langchain_core.documents.base import Document
from pydantic import FilePath, validate_call

# https://python.langchain.com/docs/integrations/text_embedding/fastembed
embeddings = FastEmbedEmbeddings(model_name="intfloat/multilingual-e5-large")


@validate_call
def split_embed_to_db(path_doc: FilePath) -> list[Document]:
    """
    create a vector store from documents
    """
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=0)
    from langchain_community.document_loaders import TextLoader

    if str(path_doc).lower().endswith(".pdf"):
        loader = PyPDFLoader(path_doc)
        documents = loader.load_and_split()
    else:
        try:
            loader = TextLoader(path_doc)
            data = loader.load()
            documents = text_splitter.split_documents(data)
        except Exception as e:
            print(f"----------Error-----------------: {e}")
            documents = None

    print("Documents created")

    return documents


try:
    # chromadb refers to the name of the container running the chromadb service (see docker-compose.yml)
    client = chromadb.HttpClient(host="chromadb", settings=Settings(allow_reset=True))
except:
    client = chromadb.HttpClient(settings=Settings(allow_reset=True))

db = Chroma(client=client, embedding_function=embeddings)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--create_db", type=str, default="true", help="Flag to create the database"
    )
    args = parser.parse_args()

    if args.create_db.lower() == "true":

        for filename in os.listdir("./src/data/documents/"):
            print(f"embedding model: {embeddings}")
            file_path = os.path.join("./src/data/documents/", filename)
            if os.path.isfile(file_path):
                print(f"embedding: {filename}")
                documents = split_embed_to_db(path_doc=file_path)
                if documents:
                    db.add_documents(documents)

        print("DB created")

    else:
        print("DB loaded from disk")


# TODO set the threshold for the similarity search. Too many unrelated documents are returned
retriever = db.as_retriever(search_type="similarity", search_kwargs={"k": 7})
print("Retriever created/loaded")

# langchain_chroma._collection.count()
