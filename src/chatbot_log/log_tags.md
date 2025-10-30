# Log Tags

- API: API called 
- AUTH: Authentication
- REDIS
- LANGGRAPH
- USERQUERY
- BOTANSWER
- FEEDBACK
- CRAWL
- SEARCH: e.g., Programmable search engine related logs
- LMM-OPERATION
- FILEIO: File input/output operations
- SECURITY: Security-related events
- METRICS: Performance or usage metrics
- TASK: Background tasks or jobs
- CONFIG: Configuration changes
- SYSTEM: System-level events
- CACHE: Caching operations
- VECTOR DB
- RAGFlow
- EMBEDDING
- NOT-ANSWERED e.g., A recursion error occurs because the content needed to answer the question was not found. 
- STREAMLIT


## Example Usage
```python
logger.info("[API] Received GET request for /users")
logger.error("[DB] Database connection failed")
logger.debug("[AUTH] Token validation started")
```


