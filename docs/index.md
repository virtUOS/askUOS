# ask.UOS Documentation

Documentation for ask.UOS, an AI chatbot for university-related queries.

## Quick Start

- [Getting Started](getting-started.md)
- [Configuration](configuration.md)
- [Architecture Overview](architecture/overview.md)

## Sections

- [Architecture](architecture/overview.md)
- [Components](components/chat-interface.md)
- [Deployment](deployment/docker.md)
- [Prompt Configuration](PROMPT_CONFIGURATION.md) — for system admins customizing bot wording
- [Installation Guide](INSTALLATION_GUIDE.md) — full production setup walkthrough

## Features

- State-based AI agent (LangGraph)
- Multi-source information retrieval (vector DB, web search, MCP subagents)
- Pluggable, per-university integrations via MCP subagents — no code changes needed
- Multilingual support
- Containerized architecture
- Real-time chat interface
- Caching for performance

## Technology Stack

- LangChain + LangGraph
- FastAPI + Streamlit
- RAGFlow/Infinity (current) or Milvus (also supported)
- Redis
- OpenAI / Google / self-hosted LLMs
- Docker

---


