# LangChain Streamlit Chatbot 
(Under development)

This project is a chatbot application built using LangChain and Streamlit. The chatbot can interact with users, summarize content, and handle various tasks using different tools and APIs.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Setup](#setup)


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
   


#### Production

1. Create a `.env.prod` file from `env.prod-example` and modify it accordingly. 
   ```
   cp .env.prod-example .env.prod
   ```
2. Start the ChatBot application 
   ```
   docker compose -f docker-compose.prod.yml up




### Chroma DB

- Data: Place the documents to be processed and embedded here `src/data`




