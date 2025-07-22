# Architecture Overview

ask.UOS uses a multi-layered architecture with modular components, asynchronous processing, and multiple storage layers.

## High-Level Architecture

```mermaid
graph TB
    User[User] --> Frontend[Streamlit Frontend]
    Frontend --> Backend[Application Backend]
    Backend --> AI[AI Agent]
    Backend --> Cache[Redis Cache]
    Backend --> VectorDB[Milvus Vector DB]
    AI --> Tools[Tools Layer]
    Tools --> WebSearch[Web Search]
    Tools --> DocRetrieval[Document Retrieval]
    DocRetrieval --> VectorDB
    WebSearch --> Crawler[crawl4ai]
    WebSearch --> SQLite[SQLite]
    Backend --> Logs[Logging System]
```

## System Layers

- Presentation: Streamlit web application
- Application: Business logic and orchestration
- AI Agent: Decision engine
- Data: Redis, Milvus, SQLite
- Infrastructure: Docker Compose

## Service Architecture

- Web: Frontend application
- Redis: Caching and sessions
- Milvus: Vector database
- etcd: Metadata storage
- MinIO: Object storage

## Data Flow

- Session data: Redis
- Vector data: Milvus
- Cache data: Redis
- Logs: Files



---

**Next**: [Software Architecture →](bot.md)
