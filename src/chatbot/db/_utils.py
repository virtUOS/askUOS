from pymilvus import DataType, MilvusClient, utility

client = MilvusClient(uri="http://standalone:19530", token="root:Milvus")

res = client.list_collections()

print(res)


from pymilvus import MilvusClient

client = MilvusClient(uri="http://localhost:19530", token="root:Milvus")

client.drop_collection(collection_name="customized_setup_2")
