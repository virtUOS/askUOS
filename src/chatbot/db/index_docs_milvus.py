# from pymilvus import MilvusClient
import os
from uuid import uuid4

import dotenv

dotenv.load_dotenv()


import argparse
import logging
import os
from typing import List, Optional

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from langchain_core.documents.base import Document
from langchain_core.vectorstores import VectorStore
from langchain_milvus import Milvus
from pydantic import DirectoryPath, FilePath, validate_call
from tqdm import tqdm

# Configurations
EMBEDDING_MODEL = "intfloat/multilingual-e5-large"
DEFAULT_DATA_DIR = "./data/documents/"
DEFAULT_COLLECTION_NAME = "examination_regulations"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 0

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize embeddings
embeddings = FastEmbedEmbeddings(model_name=EMBEDDING_MODEL)


URI = os.getenv("MILVUS_URL")


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
def get_milvus_client(collection_name: str):

    vector_store = Milvus(
        embedding_function=embeddings,
        connection_args={"uri": URI},
        collection_name=collection_name,  # TODO make this configurable
    )

    return vector_store


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
    # TODO: Needs to be done asynchronously
    files = os.listdir(data_dir)
    for filename in tqdm(
        files,
        desc="Processing files: Embedding, Indexing and Storing...",
        total=len(files),
    ):
        try:

            file_path = os.path.join(data_dir, filename)

            documents = split_embed_to_db(path_doc=FilePath(file_path))
            if documents:
                uuids = [str(uuid4()) for _ in range(len(documents))]
                db.add_documents(documents, ids=uuids)
        except Exception as e:
            logger.error(f"An error ocurrued while processing this file: {file_path}")

    logger.info("DB creation completed")


# retriever = db.as_retriever(search_type="mmr", search_kwargs={"k": 7})
# logger.debug("Retriever created/loaded")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--create_db",
        type=str,
        default="true",
        help="Flag to create the database",
    )

    parser.add_argument(
        "--collection_name",
        type=str,
        default=DEFAULT_COLLECTION_NAME,
        help="Database collection name",
    )

    parser.add_argument(
        "--custom_data_dir",
        type=str,
        default=DEFAULT_DATA_DIR,
        help="Directory containing documents",
    )
    args = parser.parse_args()

    collection_name = args.collection_name
    db = get_milvus_client(collection_name)
    if args.create_db.lower() == "true":
        create_db_from_documents(db, args.custom_data_dir)
    else:
        logger.debug("DB loaded from disk")


# TODO: set the threshold for the similarity search. Too many unrelated documents are returned
# retriever = db.as_retriever(search_type="mmr", search_kwargs={"k": 7})
# logger.debug("Retriever created/loaded")

# Example: usage of the retriever
# results = retriever.invoke("I finished my application but I did not receive a confirmation email")
# logger.info(f"Retrieved documents: {results}")
