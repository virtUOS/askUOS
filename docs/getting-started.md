## askUOS Installation Guide

This guide explains how to deploy the askUOS chatbot using Docker Compose. Caddy is provided as a suggested reverse proxy, but you can use any reverse proxy of your choice (e.g., Nginx).

## Prerequisites

- Docker and Docker Compose installed on the server
- A domain name pointing to the server (e.g., `chat.your-university.de`)
- SSL/TLS certificate (Caddy auto-provides via Let's Encrypt; configure separately for other proxies)
- Access to required API keys (see Environment Variables section)
- A [RAGFlow](https://github.com/infiniflow/ragflow) instance

## Directory Structure

Create the installation directory:

```bash
sudo mkdir -p /opt/chatbot
cd /opt/chatbot
```

The following files and directories should be placed in `/opt/chatbot/`:

```
/opt/chatbot/
├── .env.prod                    # Environment variables (see below)
├── backend_config.yaml          # Backend configuration
├── ui_config.yml                # UI configuration  
├── config.toml                  # Streamlit configuration
├── Caddyfile                    # Caddy reverse proxy config (optional)
├── datenschutz.html             # Privacy policy page
├── impressum.html               # Imprint/legal notice page
├── promtail-config.yml          # Log collection config (optional)
├── config_loki.yml              # Loki log storage config (optional)

```

---

## Environment Variables (`.env.prod`)

Create the `.env.prod` file with the following variables:

```bash
#============#
# OpenAI     #
#============#
# IF using OpenAI
OPENAI_API_KEY=""

#============#
# Self-hosted#
# LLMs       #
#============#
# If models are hosted locally
API_KEY_SELF_HOSTED_MAIN=""
API_KEY_SELF_HOSTED_HELPER=""

#============#
# RAGFlow    #
#============#

RAGFLOW_API_KEY=""

#============#
# Google API #
#============#

# Required for Gemini models
GEMINI_API_KEY=""

# Google Search URL (REQUIRED)
# Replace YOUR-KEY and YOUR-CX with actual values from Google Cloud Console
# https://developers.google.com/custom-search/v1/using_rest
SEARCH_URL = "https://www.googleapis.com/customsearch/v1?key=YOUR-KEY&cx=YOUR-CX&q="

#============#
# askUOS     #
#============#

# Generate secure random strings
# The STREAMLIT_API_KEY must match one of the keys in API_KEYS
API_KEYS = "<generate-secure-random-string>"
STREAMLIT_API_KEY = "<generate-secure-random-string>"
```

### Required Google API Permissions

The Google API key must have access to:
- Custom Search API
    - You need to configure a Programmable Search Engine and index the sites you want to search (e.g., the Website of your University). The engine endpoint should be configured in the `.env.prod` file as `SEARCH_URL`.
- Generative Language API (If using Google as LLM provider)
- Vertex AI API (If using Google as LLM provider)

### ⚠️ Security Warnings

- The `STREAMLIT_API_KEY` must match one of the keys listed in `API_KEYS`.
- Generate secure random strings for all API keys. 

---

## Backend Configuration (`backend_config.yaml`)

This file, `backend_config.yaml`, configures the models and other backend settings. See the example: [`backend_config_example.yaml`](backend_config_example.yaml).

To use the example configuration:

```bash
cp docs/backend_config_example.yaml ./backend_config.yaml
# Edit backend_config.yaml with your specific settings
```

---

## UI Configuration (`ui_config.yml`)

This file, `ui_config.yml`, configures the user interface settings. Follow this example: [`ui_example_config.yml`](ui_example_config.yml).

To use the example configuration:

```bash
cp docs/ui_example_config.yml ./ui_config.yml
# Edit ui_config.yml with your specific settings
```

**Note:** For the icons, mount (to the container) your own custom icons to the `/app/ui/static/icons/` directory with the same filenames: `Icon-User.svg`, `Icon-chatbot.svg`, `Icon-chatbot.png`.

---

## Streamlit Configuration (`config.toml`)

```toml
[server]
enableStaticServing = true

[theme]
primaryColor = "#ad1034"

[client]
showErrorDetails = "none"
toolbarMode = "minimal"
showSidebarNavigation = false

[browser]
gatherUsageStats = false
```

---

## Prompts Configuration (`prompt_text.py`)

The prompt configuration file ([`src/chatbot/prompt/prompt_text.py`](../src/chatbot/prompt/prompt_text.py)) contains pyhton dictionaries (`prompt_text_english` and `prompt_text_deutsch`) that specifiy the system messages and instructions that define the chatbot's behavior, personality, and knowledge scope. **This file must be mounted to the container (`container_name: ask_uos`) during installation** at the path `/app/src/chatbot/prompt/prompt_text.py`.

### Adapting Prompts for Your University

When deploying askUOS at a different university, you must customize the prompts to reflect your institution's specific information. Copy and modify this file: [`src/chatbot/prompt/prompt_text.py`](../src/chatbot/prompt/prompt_text.py).

Here are the key areas to modify:

#### 1. University Name and Identity
- **What to change**: Replace "Osnabrück University" with your university's name
- **Example**: `# AI Assistant of [Your University Name]`

#### 2. Tool Descriptions and Names
- **Location**: Lines (around) 12-14, 193-212 (English), 366-368, 551-574 (German)
- **What to change**:
  - Update tool names to match your university's systems (e.g., replace "HISinOne" with your application portal name)
  - Update tool descriptions to reflect your university's software and processes
  - Modify the `custom_university_web_search` description to point to your university's website

#### 3. University-Specific Processes
- **Location**: Lines 77-186 (application process), 272-352 (teaching degrees)
- **What to change**:
  - Update admission requirements and procedures
  - Modify degree program structures (Bachelor/Master types)
  - Adjust application deadlines and processes
  - Update examination regulations references

#### 4. University-Specific Terminology
- **Location**: Throughout the file
- **What to change**:
  - Replace German-specific terms (e.g., "Zulassungsbeschränkungen", "NC-Fächer") with your local terminology
  - Update program names and combinations
  - Modify any culturally-specific references

#### 5. Links and Resources
- **Location**: Line (around) 174 (FAQ link)
- **What to change**: Replace with your university's FAQ page and other relevant resources

#### 6. Supported Languages
- **What to change**: Update language settings based on your university's primary languages

### Mounting the Prompts File

Before mounting the file to the container make sure that the python script is correct, e.g, pay close attention to the script syntax: this file should contain valid python dictionaries.

Add the following volume mount to your `docker-compose.yml`:

```yaml
volumes:
  - ./prompt_text.py:/app/src/chatbot/prompt/prompt_text.py
```

This ensures your customized prompts are used instead of the default ones.

### Best Practices for Customization

1. **Keep the structure**: Maintain the overall structure and format of the prompts
2. **Preserve tool usage instructions**: The chatbot relies on tools for accurate information
3. **Update both languages**: Ensure both English and German sections are updated
4. **Test thoroughly**: After customization, test the chatbot with common queries

---

## Docker Compose Configuration

Create `docker-compose.yml`:

The easiest way to install askUOS is using Docker Compose. Follow this example: [`docker-compose.prod.example.yml`](docker-compose.prod.example.yml).

To use the example configuration:

```bash
cp docs/docker-compose.prod.example.yml ./docker-compose.yml
# Edit docker-compose.yml with your specific settings (e.g., image tag)
```

---

## Caddy Configuration (`Caddyfile`) - Optional

If using Caddy as your reverse proxy, follow this example: [`Caddy.example`](Caddy.example).

To use the example configuration:

```bash
cp docs/Caddy.example ./Caddyfile
# Edit Caddyfile with your domain name
```

### Using a Different Reverse Proxy

If you prefer Nginx, Traefik, or another reverse proxy, configure it to:

1. Forward `/v1/*` and `/health` to `localhost:8000` (FastAPI backend)
2. Forward all other requests to `localhost:8501` (Streamlit UI)
3. Handle SSL termination
4. Serve static files (`datenschutz.html`, `impressum.html`)

---

## Deployment Steps

1. **Clone or copy all configuration files** to `/opt/chatbot/`

2. **Update environment variables** in `.env.prod` with your actual API keys

3. **Generate secure authentication keys**: Set `API_KEYS` and `STREAMLIT_API_KEY` in `.env.prod`.

4. **Customize prompts for your university** (see [Prompts Configuration](#prompts-configuration-prompt_textpy)):
   - Edit `prompt_text.py` with your university's name and processes
   - Mount the file in `docker-compose.yml` as shown in the Prompts section

5. **Configure your reverse proxy**:
   - If using Caddy, update the `Caddyfile` with your domain name
   - If using another proxy, configure it according to the routing rules above

5. **Start the services**:
   ```bash
   cd /opt/chatbot
   docker compose up -d
   ```

6. **Check service status**:
   ```bash
   docker compose ps
   ```

7. **View logs**:
   ```bash
   docker compose logs -f app
   ```

---

## Access Points

| Service | URL |
|---------|-----|
| Chatbot UI | `https://your-domain.de` |
| API | `https://your-domain.de/v1/*` |
| Health Check | `https://your-domain.de/health` |

---


## Troubleshooting

| Issue | Solution |
|-------|----------|
| Container won't start | Check `.env.prod` for missing or invalid API keys |
| SSL certificate issues | Ensure port 80 and 443 are open for Let's Encrypt (Caddy) |
| Slow responses | Check `recursion_limit` and consider reducing it |

---

## Updating

To update to a new version:

```bash
cd /opt/chatbot
docker compose pull
docker compose up -d
```

To rollback, specify a previous image tag in the docker-compose.yml file:

```yaml
image: ghcr.io/virtuos/askuos:previous-version


## Next Steps

- Explore architecture in [Architecture Overview](architecture/overview.md)

