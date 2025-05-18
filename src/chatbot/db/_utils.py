from pymilvus import DataType, MilvusClient, utility

client = MilvusClient(uri="http://standalone:19530", token="root:Milvus")

res = client.list_collections()

print(res)


from pymilvus import MilvusClient

client = MilvusClient(uri="http://localhost:19530", token="root:Milvus")

client.drop_collection(collection_name="customized_setup_2")


import redis

r = redis.StrictRedis(host="redis", port=6379, decode_responses=True)
print(r.keys("*"))

r.flushdb()


# Add/set a key
r.set("mykey", "hello world")

# Add/set a key with expiration (TTL in seconds)
r.setex("mykey", 60, "hello world")

# Delete a key
r.delete("mykey")

# List all keys
keys = r.keys("*")
print(keys)
