# Configuration

ask.UOS uses YAML files, environment variables, and runtime settings managed through Pydantic models.

## Configuration Files

- `config.yaml`: Main configuration for model, language, legal, application, embedding, database, and logging
- `.env`: Environment variables for API keys, endpoints, and security

## Configuration Models

- Model, application, and database settings are validated at startup
- Embedding configuration supports Ollama and Fastembed

## Loading and Updating

- Configuration is loaded from YAML and environment variables


## Environment-Specific Configurations

- Development, production, and testing configurations are supported

## Validation

- Language and embedding settings are validated
- API connections are checked at startup


---

**Next**: [Getting Started →](./getting-started.md)
