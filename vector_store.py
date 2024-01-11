from langchain_community.document_loaders import TextLoader
from embedding import embeddings
from langchain.text_splitter import CharacterTextSplitter
from langchain_community.vectorstores import Chroma

# Load the document, split it into chunks, embed each chunk and load it into the vector store.
# todo create a funtion that iterates over all files in a directory and loads them into the vector store
raw_documents = TextLoader('./data/application.txt').load()
text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=0)
# chunks returns a list of documents, where each element of the list is of type 'langchain_core.documents.base.Document'
documents = text_splitter.split_documents(raw_documents)
db = Chroma.from_documents(documents, embeddings)

# save db to disk
#db = Chroma.from_documents(documents, embeddings, persist_directory="./data/chroma_index")


# you can define a threshold for the similarity search
retriever = db.as_retriever(search_type='similarity', search_kwargs={'k': 2})

# Input—> string query; output—> list of documents
#retriever.get_relevant_documents(" Wo finde ich die Informationen zum Studienangebot")



# # save to disk
# db2 = Chroma.from_documents(docs, embedding_function, persist_directory="./chroma_db")
# docs = db2.similarity_search(query)
#
# # load from disk
# db3 = Chroma(persist_directory="./chroma_db", embedding_function=embedding_function)
# docs = db3.similarity_search(query)
# print(docs[0].page_content)