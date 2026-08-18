## askUOS Installation Guide

This guide explains how to deploy the askUOS chatbot using Docker Compose. Caddy is provided as a suggested reverse proxy, but you can use any reverse proxy of your choice (e.g., Nginx).

## Table of Contents

- [Prerequisites](#prerequisites)
- [Directory Structure](#directory-structure)
- [Environment Variables (`.env.prod`)](#environment-variables-envprod)
  - [Required Google API Permissions](#required-google-api-permissions)
- [Backend Configuration (`backend_config.yaml`)](#backend-configuration-backend_configyaml)
- [UI Configuration (`ui_config.yml`)](#ui-configuration-ui_configyml)
- [Streamlit Configuration (`config.toml`)](#streamlit-configuration-configtoml)
- [Prompts Configuration (`prompt_text.py`)](#prompts-configuration)
- [Caddy Configuration (`Caddyfile`) - Optional](#caddy-configuration-caddyfile---optional)
  - [Using a Different Reverse Proxy](#using-a-different-reverse-proxy)
- [Deployment Steps](#deployment-steps)
- [Access Points](#access-points)
- [Troubleshooting](#troubleshooting)
- [Updating](#updating)

---

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

Create `.env.prod`. Take a look at [`docs/env.prod.example`](docs/env.prod.example)


### Required Google API Permissions

The Google API key must have access to:
- Custom Search API
    - You need to configure a Programmable Search Engine and index the sites you want to search (e.g., the Website of your University). The engine endpoint should be configured in the `.env.prod` file as `SEARCH_URL`.
- Generative Language API (If using Google as LLM provider)
- Vertex AI API (If using Google as LLM provider)

### ⚠️ Security Warnings

- The `STREAMLIT_API_KEY` must match one of the keys listed in `API_KEYS` (Follow same procedure to set up the `HISTORY_API_KEYS`).
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

## Prompts Configuration 

askUOS's wording — what the bot says, what it's allowed to answer, how tools are described to it — comes from three different places, each with a different audience. This guide explains which is which, so you edit the right one.

### 1. Internal prompts — not for you to configure

**Where:** `src/chatbot/prompt/internal_prompt_text.py`

These are implementation details of the graph's own control flow: a description field consumed only by an internal grading step's structured output, and a short internal message inserted when the graph corrects the agent's own decision. None of this text is ever shown to end users, and none of it defines the bot's behavior, tone, or scope — it only makes sense in the context of the exact Python code that reads it. That's why it's kept in Python source rather than a config file: there's nothing here a university admin needs, or should want, to customize. Changing it requires a code change and redeploy, same as any other application logic.

### 2. General application prompts — configure these for every installation

**Where:** `prompts_example/` (copy to `prompts/` to activate your changes)

This is the bot's actual personality and guardrails: the system prompts that define what it is, what it's allowed to talk about, how it should ask clarifying questions, and how it should use retrieved context — plus a couple of short, always-active tool descriptions. These apply to every installation regardless of which optional tools or MCP integrations are turned on, so **every institution adopting askUOS should review and adjust these**, not just leave the shipped University of Osnabrück wording in place.

Layout: one `.md` file per long prompt, per language (`prompts/en/system_message.md`, `prompts/de/system_message.md`, etc.), plus a short `strings.yaml` per language for the couple of always-on tool descriptions.

Rules when editing:
- Each file may contain `{placeholder}` markers (e.g. `{current_date}`, `{user_query}`, `{context}`). These are filled in automatically at runtime — keep them, spelled exactly as they are, but feel free to move them to a different part of the text.
- Deleting a placeholder or introducing a typo in its name makes the application **fail to start**, with an error naming the exact file and the missing/wrong placeholder. This is intentional: a wording mistake gets caught immediately, not discovered later as a broken or nonsensical answer.
- Changes require restarting (rebuilding) the app to take effect — there's no live reload.

### 3. Tool / MCP / agent-specific prompts — only needed if that feature is on

**Where:** `backend_config.yaml`

Some prompts belong to one specific optional feature — a standalone tool or an MCP-connected subagent — and are meaningless outside that feature's own configuration block. These live next to the feature they describe in `backend_config.yaml`, not in `prompts/`, and you only need to fill them in if you actually enable that feature:

- **Standalone tools**, e.g. the troubleshooting tool:
  ```yaml
  graph:
    troubleshooting:
      activate: True   # only if True is a description required
      description: |
        What this tool is for and when the agent should use it.
  ```
- **MCP subagents**, one block per agent under `mcp_agents:`:
  ```yaml
  mcp_agents:
    - agent_name: "some_agent"
      enabled: True
      description: |     # tells the main agent when to route a task to this subagent
        ...
      prompt: |           # the system prompt for the subagent itself
        ...
  ```

If a tool/agent is disabled (`activate: False` / `enabled: False`), its prompt fields are ignored and don't need to be provided at all.


### Best Practices for Customization

1. **Keep the structure**: Maintain the overall structure and format of the prompts
2. **Preserve tool usage instructions**: The chatbot relies on tools for accurate information
3. **Update both languages**: Ensure both English and German sections are updated
4. **Test thoroughly**: After customization, test the chatbot with common queries

### Quick reference

| Type | Location | Who edits it | When needed |
|---|---|---|---|
| Internal | `src/chatbot/prompt/internal_prompt_text.py` | Developers only | Never (not user-facing) |
| General application | `prompts/` (from `prompts_example/`) | Every installer | Always |
| Tool/MCP-specific | `backend_config.yaml` | Every installer, per feature | Only if that tool/agent is activated |


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

4. **Customize prompts for your university** (see [Prompts Configuration](#Prompts Configuration)):
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
   docker compose logs -f app_name
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

```

## Next Steps

- Explore architecture in [Architecture Overview](architecture/overview.md)
