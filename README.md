# Chatbot
### (Under development)
This is a Chatbot built using LangChain and Streamlit. Its architecture is based on the RAG methodology. 

## Docker

You can develop or deploy this application using Docker.

### Development


1. Create a `.env.dev` file from `env.dev-example` and modify it accordingly. 
   ```
   cp .env.dev-example .env.dev
   ```
2. Start the ChatBot application 
   ```
   docker compose up -d
   ```
3. To access the ChatBot visit ` http://localhost:8502/`
   


### Production

1. Create a `.env.prod` file from `env.prod-example` and modify it accordingly. 
   ```
   cp .env.prod-example .env.prod
   ```
2. Start the ChatBot application 
   ```
   docker compose -f docker-compose.prod.yml up
