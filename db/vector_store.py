from langchain.text_splitter import  RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.embeddings.sentence_transformer import (
    SentenceTransformerEmbeddings,
)
from langchain_community.embeddings import OllamaEmbeddings
import pickle
from langchain_community.vectorstores import Chroma
import os
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
import chromadb
from chromadb.config import Settings
import argparse

EXTRACT_FROM_WEBSITE = False

'''
"T-Systems-onsite/cross-en-de-roberta-sentence-transformer" --> parameters: 278043648
'''

# todo try out this embedding model embaas/sentence-transformers-e5-large-v2 --> https://huggingface.co/embaas/sentence-transformers-e5-large-v2
# create the open-source embedding function
# Number of parameters: 335141888 for embaas/sentence-transformers-e5-large-v2
# embeddings = SentenceTransformerEmbeddings(model_name='T-Systems-onsite/cross-en-de-roberta-sentence-transformer')
# embeddings = SentenceTransformerEmbeddings(model_name='embaas/sentence-transformers-e5-large-v2')

# embeddings = SentenceTransformerEmbeddings(model_name="all-MiniLM-L6-v2")

# Embedding using allama model

# embeddings = OllamaEmbeddings(model="llama2:13b", show_progress=True)
#https://python.langchain.com/docs/integrations/text_embedding/fastembed
# embeddings = FastEmbedEmbeddings(
#     model_name='intfloat/multilingual-e5-large'
# )


# load or create db
# db = Chroma(persist_directory="./chromadb/chroma_index", embedding_function=embeddings)

try:
    client = chromadb.HttpClient(host='chromadb',settings=Settings(allow_reset=True))
except:
    client = chromadb.HttpClient(settings=Settings(allow_reset=True))

db = Chroma(client=client)
# db = Chroma(client=client, embedding_function=embeddings)

def get_links_from_pickle (path_to_pickle):
    with open(path_to_pickle, 'rb') as f:
        links = pickle.load(f)
    return set(links)


def split_embed_to_db(links=None, path_doc=None):
    '''
    create a vector store from a text file or a website
    '''
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=0)
    if EXTRACT_FROM_WEBSITE:
        from langchain_community.document_loaders import AsyncChromiumLoader
        from langchain_community.document_transformers import BeautifulSoupTransformer

        try:
            with open('data/transformed_data.pickle', 'rb') as f:
                documents = pickle.load(f)
        except FileNotFoundError:
            # Load
            print('Loading html content from website')
            try:
                with open('data/html.pickle', 'rb') as f:
                    html = pickle.load(f)
            except FileNotFoundError:

                loader = AsyncChromiumLoader(links)
                html = loader.load()
                # save html to pickle file`
                with open('data/html.pickle', 'wb') as f:
                    pickle.dump(html, f, protocol=pickle.HIGHEST_PROTOCOL)

                print('html content extracted and saved to pickle file')

            # Transform
            bs_transformer = BeautifulSoupTransformer()
            documents = bs_transformer.transform_documents(
                html, tags_to_extract=["p", "li", "div", "a"]
            )
            # save transformed files to pickle file
            with open('data/transformed_data.pickle', 'wb') as f:
                pickle.dump(documents, f, protocol=pickle.HIGHEST_PROTOCOL)

            print('html content transformed and saved to pickle file')

    else:
        from langchain_community.document_loaders import TextLoader


        if path_doc.lower().endswith('.pdf'):
            loader = PyPDFLoader(path_doc)
            documents = loader.load_and_split()
        else:
            try:
                loader = TextLoader(path_doc)
                data = loader.load()
                documents = text_splitter.split_documents(data)
            except Exception as e:
                print(f'----------Error-----------------: {e}')
                documents = None



    # all_splits = text_splitter.split_documents(data)

    print('Documents created')


    return documents




if __name__ == "__main__":
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--create_db', type=str, default='false', help='Flag to create the database')
    args = parser.parse_args()
    
    if args.create_db.lower() == 'true':
    
        if EXTRACT_FROM_WEBSITE:
                links = get_links_from_pickle('data/links.pickle')
                documents = split_embed_to_db(links=list(links))
                print(f'embedding model: {embeddings}')
                if documents:
                    db.add_documents(documents)
        else:
                for filename in os.listdir('data/documents/'):
                    print(f'embedding model: {embeddings}')
                    file_path = os.path.join('data/documents/', filename)
                    if os.path.isfile(file_path):
                        print(f'embedding: {filename}')
                        documents = split_embed_to_db(path_doc=file_path)
                        if documents:
                            db.add_documents(documents)

        print('DB created')
    else:
        print('DB loaded from disk')





# todo set the threshold for the similarity search. Too many unrelated documents are returned
retriever = db.as_retriever(search_type='similarity', search_kwargs={'k': 7})
print('Retriever created/loaded')

# langchain_chroma._collection.count()