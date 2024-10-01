# LangChain Streamlit Chatbot 
(Under development)

This project is a chatbot application built using LangChain and Streamlit. The chatbot can interact with users, summarize content, and handle various tasks using different tools and APIs.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Setup](#setup)
- [Translation Mechanism](#translation_mechanism)


## Overview

The LangChain Streamlit Chatbot is designed to provide an interactive interface for users to communicate with a chatbot and thus access to updated information (In this case about a University). It leverages the LangChain library for natural language processing and Streamlit for the web interface.

## Features

- Interactive chatbot interface
- Content summarization
- PDF reading and processing
- Web scraping and data extraction
- Customizable prompts and responses

## Setup

### Prerequisites

- See `requirements.txt`
- Docker ( for containerization)


### Application Configuration
This application uses a configuration file (`config.yaml`) to manage its settings. The settings are structured in a way that allows for easy customization without modifying the source code. The configuration is validated at startup using Pydantic, ensuring that all required fields are present and correctly formatted.

#### Congiguration File `config.yaml`

The `config.yaml` file should be placed in the root directory of the application. Modify the existing file accordingly (If necessary). 


### Installation

You can develop or deploy this application using Docker.

#### Development


1. Create a `.env.dev` file from `env.dev-example` and modify it accordingly. 
   ```
   cp .env.dev-example .env.dev
   ```
2. Start the ChatBot application 
   ```
   docker compose up -d
   ```
3. To access the ChatBot visit ` http://localhost:8501/`
   
**Note:** If you run the application without Docker; you need to set up a chromadb server manually. 

#### Production

1. Create a `.env.prod` file from `env.prod-example` and modify it accordingly. 
   ```
   cp .env.prod-example .env.prod
   ```
2. Create a `nginx.conf` file from `nginx.conf-example` and modify it accordingly
```
cp ./nginx/nginx.conf.example nginx.conf
```

3. Start the ChatBot application 
   ```
   docker compose -f docker-compose.prod.yml up




### Chroma DB

- Data: Place the documents to be processed and embedded here `src/data`


## Translation Mechanism


This project supports both German and English languages, allowing users to switch between them seamlessly. The translation mechanism is implemented using the `gettext` library: a standard for internationalization and localization in Python.

### How It Works

1. Translation Setup:
   - The system generates a  `base.mo`file from `locale/de/LC_MESSAGES/base.po` (This file is autmatically generated when the software is installed using `Docker`)
   - The project sets up the translation for German using `gettext.translation`. It installs the German translation and provides a function to translate text.

2. Language Initialization:

   - The project, using `Streamlit`, sets up a radio button for language selection. It defaults to German if no language is chosen.
   - When the user selects a language, the application updates the session state and configuration based on the selected language.
   - The selected language is stored in the session state and query parameters.


3. Usage in Streamlit:

   - Throughout the Streamlit application, the translation function from the session state is used to translate text dynamically based on the selected language.

By following this approach, the project ensures that all user-facing text can be easily translated and displayed in the user's preferred language.
