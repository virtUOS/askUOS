from embedding import embeddings
from langchain.text_splitter import CharacterTextSplitter, RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma

EXTRACT_FROM_WEBSITE = True

# Load the document, split it into chunks, embed each chunk and load it into the vector store.
# todo create a funtion that iterates over all files in a directory and loads them into the vector store
# raw_documents = TextLoader('./data/application.txt').load()
# text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=0)
# # chunks returns a list of documents, where each element of the list is of type 'langchain_core.documents.base.Document'
# documents = text_splitter.split_documents(raw_documents)
# db = Chroma.from_documents(documents, embeddings)

# save db to disk
#db = Chroma.from_documents(documents, embeddings, persist_directory="./data/chroma_index")


# # load from disk
# db = Chroma(persist_directory="./data/chroma_index", embedding_function=embeddings)



# you can define a threshold for the similarity search


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


def split_embed_to_db():
    '''
    create a vector store from a text file or a website
    '''

    if EXTRACT_FROM_WEBSITE:
        from langchain_community.document_loaders import WebBaseLoader

        text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=0)
        loader = WebBaseLoader("https://www.virtuos.uni-osnabrueck.de/campus_management.html/")
        data = loader.load()


    else:
        from langchain_community.document_loaders import TextLoader

        text_splitter = CharacterTextSplitter(chunk_size=500, chunk_overlap=0)
        loader = TextLoader('./data/application.txt')
        data = loader.load()



    all_splits = text_splitter.split_documents(data)
    documents = text_splitter.split_documents(all_splits)
    db = Chroma.from_documents(documents, embeddings, persist_directory="./data/chroma_index")

    return db



try: # try to load the db from disk
    db = Chroma(persist_directory="./data/chroma_index", embedding_function=embeddings)
except:
    db = split_embed_to_db()

retriever = db.as_retriever(search_type='similarity', search_kwargs={'k': 2})