# ask.UOS

*AI chatbot for applicants and students – get instant answers about studies, teaching, and campus life.*

[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://docker.com)
[![Python](https://img.shields.io/badge/Python-3.11-green.svg)](https://python.org)
[![LangChain](https://img.shields.io/badge/LangChain-orange.svg)](https://langchain.com)
[![Streamlit](https://img.shields.io/badge/Streamlit-red.svg)](https://streamlit.io)

## 📖 Documentation

**Documentation is available at: [docs/](./docs/)**

- **[Getting Started](./docs/getting-started.md)** - Quick setup and installation
- **[Architecture](./docs/architecture/overview.md)** - System design and components
- **[Configuration](./docs/configuration.md)** - Configuration options and setup
- **[Deployment](./docs/deployment/docker.md)** - Docker and production deployment

##  Quick Start

```bash
# 1. Clone and configure
git clone <your-repo-url>
cd askuos
cp config_example.yaml config.yaml
cp .env.dev-example .env.dev

# 2. Add your OpenAI API key to .env.dev
echo "OPENAI_API_KEY=your_api_key_here" >> .env.dev

# 3. Start the application
docker compose up -d

# 4. Access the chatbot
open http://localhost:8501
```

---

## Overview

ask.UOS is designed to provide an interactive interface for users to communicate with a chatbot and access up-to-date university information. It leverages the `LangChain` library for natural language processing and `Streamlit` for the web interface. The system supports both German and English, and can be easily extended to other languages.

ask.UOS can answer a wide range of general questions about university life in just a few moments, including inquiries about the application process, academic requirements, and various study programs. The chatbot enables users to receive quick support in a conversational manner, without having to wait for office hours or search for the right contact person—available 24/7. For university departments such as student advisory services, the chatbot also helps reduce the volume of support requests.

---

## Features

- Interactive chatbot interface for students and applicants
- Content summarization and document insights
- PDF reading and processing
- Web scraping and data extraction
- Multilingual support (German and English)
- Customizable prompts and responses
- Vector database (Milvus) for efficient unstructured data retrieval

---

## Setup

### Prerequisites

- [Docker](https://www.docker.com/) and [Docker Compose](https://docs.docker.com/compose/)
- (For development) See `requirements.txt`
- (For production) See `requirements.prod.txt`

---

### Development with Docker

1. **Clone the repository**  
   ```sh
   git clone <your-repo-url>
   cd <your-repo>
   ```

2. **Create and configure environment file**  
   ```sh
   cp .env.dev-example .env.dev
   # Edit .env.dev as needed
   ```

3. **Start the application**  
   ```sh
   docker compose up -d
   ```

4. **Access the chatbot**  
   Open [http://localhost:8501/](http://localhost:8501/) in your browser.

**Note:** If you run the application without Docker, you must set up a Milvus server manually.

---

### Production with Docker

1. **Create and configure environment file**  
   ```sh
   cp .env.prod-example .env.prod
   # Edit .env.prod as needed
   ```

2. **Set up Nginx configuration (optional, for reverse proxy)**  
   ```sh
   cp ./nginx/nginx.conf.example nginx.conf
   # Edit nginx.conf as needed
   ```

3. **Start the application in production mode**  
   ```sh
   docker compose -f docker-compose.prod.yml up -d
   ```

---

## Configuration

This application uses a configuration file (`config.yaml`) to manage its settings. The configuration is validated at startup using `Pydantic`, ensuring all required fields are present and correctly formatted.

- Modify the example file as needed for your environment.

  ```sh
   cp config_example.yamo config.yaml
   # Edit config.yaml as needed
   ```

---

## Milvus Vector DB

- A vector database (Milvus) is used for indexing and storage of unstructured data (e.g., pdf files).
- Milvus is automatically set up via Docker Compose and does not require manual installation.
- If you are already running a Milvus instance, you can connect ask.UOS with it. See `config_example.yaml`

---

## Translation Mechanism

ask.UOS supports both German and English, allowing users to switch languages seamlessly. The translation mechanism is implemented using Python’s `gettext` library.

### How It Works

1. **Translation Setup**
   - The system generates a `base.mo` file from `locale/de/LC_MESSAGES/base.po` (automatically during Docker build).
   - The project sets up German translation using `gettext.translation` and provides a function for dynamic text translation.

2. **Language Initialization**
   - Streamlit presents a radio button for language selection (default: German).
   - The selected language is stored in the session state and query parameters.

3. **Usage in Streamlit**
   - Throughout the app, the translation function is used to display text in the user’s chosen language.



---

## License

[MIT](LICENSE)


