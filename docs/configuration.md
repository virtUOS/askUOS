# Configuration

ask.UOS uses YAML files, environment variables, and runtime settings managed through Pydantic models.

## Configuration Files

- `src/backend_config.yaml` (copy from `src/backend_config_example.yaml`): model, language, legal, application, embedding, database, MCP agents (`mcp_agents`), and logging settings
- `prompts/` (copy from `prompts_example/`): system prompts and tool wording, plain text — not part of `backend_config.yaml`.
- `.env`: Environment variables for API keys, endpoints, and security

## Configuration Models

- Model, application, and database settings are validated at startup
- MCP agents (`mcp_agents`) support per-agent recursion limit, timeout, enabled flag, and an optional startup connectivity check (`fail_on_mcp_unreachable`)
- Embedding configuration uses a self-hosted, OpenAI-compatible endpoint (e.g. BGE-M3 served behind LiteLLM), the same pattern as the self-hosted chat models

## Loading and Updating

- Configuration is loaded from YAML and environment variables


## Environment-Specific Configurations

- Development, production, and testing configurations are supported

## Validation

- Language and embedding settings are validated
- API connections are checked at startup


---

**Next**: [Getting Started →](./getting-started.md)
