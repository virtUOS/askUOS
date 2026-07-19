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
- **[Deployment](./docs/deployment/docker.md)** - Docker and production deployment


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
- Vector database for efficient unstructured data retrieval

---


## Translation

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


