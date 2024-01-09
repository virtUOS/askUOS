from langchain_community.document_loaders import TextLoader
from embedding import embeddings
from langchain.text_splitter import CharacterTextSplitter
from langchain_community.vectorstores import Chroma

# Load the document, split it into chunks, embed each chunk and load it into the vector store.
raw_documents = TextLoader('./data/application.txt').load()
text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=0)
documents = text_splitter.split_documents(raw_documents)
db = Chroma.from_documents(documents, embeddings)

# you can define a threshold for the similarity search
retriever = db.as_retriever(search_type='similarity', search_kwargs={'k': 2})

# Input—> string query; output—> list of documents
#retriever.get_relevant_documents(" Wo finde ich die Informationen zum Studienangebot")

