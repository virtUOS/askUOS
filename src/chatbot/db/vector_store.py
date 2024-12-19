import argparse
import os
import logging
from typing import List, Optional

import chromadb
from langchain_core.vectorstores import VectorStore
from chromadb.config import Settings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from langchain_community.embeddings.sentence_transformer import (
    SentenceTransformerEmbeddings,
)
from langchain_community.vectorstores import Chroma
from langchain_core.documents.base import Document
from pydantic import FilePath, DirectoryPath, validate_call

# Configurations
EMBEDDING_MODEL = "intfloat/multilingual-e5-large"
DEFAULT_DATA_DIR = "./src/data/documents/"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 0

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize embeddings
embeddings = FastEmbedEmbeddings(model_name=EMBEDDING_MODEL)


@validate_call
def split_embed_to_db(path_doc: FilePath) -> Optional[List[Document]]:
    """
    Splits the given document into smaller chunks and returns a list of documents.

    Args:
        path_doc (FilePath): The path to the document to be split.

    Returns:
        Optional[List[Document]]: A list of documents if the splitting is successful, otherwise None.
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    )
    documents = None

    try:
        if path_doc.suffix.lower() == ".pdf":
            loader = PyPDFLoader(path_doc)
            documents = loader.load_and_split()
        else:
            loader = TextLoader(path_doc)
            data = loader.load()
            documents = text_splitter.split_documents(data)
        logger.info(f"Documents created for {path_doc}")
    except Exception as e:
        logger.error(f"Error while processing {path_doc}: {e}")

    return documents


# Function to create or load the database client
def get_chroma_client() -> chromadb.HttpClient:
    """
    Get a client for connecting to the chromadb service.

    Returns:
        chromadb.HttpClient: A client for interacting with the chromadb service.
    """
    try:
        # chromadb refers to the name of the container running the chromadb service (see docker-compose.yml)
        client = chromadb.HttpClient(
            host="chromadb", settings=Settings(allow_reset=True)
        )
        logger.debug("Connected to chromadb service")
    except Exception as e:
        logger.warning(
            f"Failed to connect to chromadb service: {e}. Using default settings."
        )
        client = chromadb.HttpClient(settings=Settings(allow_reset=True))

    return client


@validate_call
def create_db_from_documents(db, data_dir: DirectoryPath) -> None:
    """
    Creates a database from a directory of documents.

    Args:
        db (Chroma): The database object to store the documents.
        data_dir (str): The directory path containing the documents.

    Returns:
        None
    """
    for filename in os.listdir(data_dir):
        file_path = os.path.join(data_dir, filename)

        documents = split_embed_to_db(path_doc=FilePath(file_path))
        if documents:
            db.add_documents(documents)

    logger.info("DB creation completed")


client = get_chroma_client()
db = Chroma(client=client, embedding_function=embeddings)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--create_db",
        type=str,
        default="true",
        help="Flag to create the database",
    )

    parser.add_argument(
        "--custom_data_dir",
        type=str,
        default=DEFAULT_DATA_DIR,
        help="Directory containing documents",
    )
    args = parser.parse_args()

    if args.create_db.lower() == "true":
        create_db_from_documents(db, args.custom_data_dir)
    else:
        logger.debug("DB loaded from disk")


# TODO: set the threshold for the similarity search. Too many unrelated documents are returned
retriever = db.as_retriever(search_type="similarity", search_kwargs={"k": 7})
logger.debug("Retriever created/loaded")

# Example: usage of the retriever
# results = retriever.invoke("I finished my application but I did not receive a confirmation email")
# logger.info(f"Retrieved documents: {results}")
