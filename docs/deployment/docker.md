# Docker Setup

ask.UOS uses Docker Compose for orchestrating services in development and production.

## Container Architecture

```mermaid
graph TB
    subgraph "Docker Compose"
        Web[web: Streamlit App]
        Redis[redis: Cache & Sessions]
        Milvus[standalone: Vector Database]
        Etcd[etcd: Metadata Store]
        Minio[minio: Object Storage]
    end
    Web --> Redis
    Web --> Milvus
    Milvus --> Etcd
    Milvus --> Minio
```

## Service Definitions

- Web: Streamlit application
- Redis: Caching and sessions
- Milvus: Vector database
- etcd: Metadata storage
- MinIO: Object storage

## Setup Steps

- Build and start services with Docker Compose
- Configure environment variables for API keys and endpoints


---

**Next**: [Configuration →](/docs/configuration.md)
