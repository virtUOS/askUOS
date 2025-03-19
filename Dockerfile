# Use the official Python image from Docker Hub
FROM python:3.11

# Set the working directory inside the container
WORKDIR /app

# Install dependencies
RUN apt-get update && apt-get install -y \
    sudo \
    wget \
    gettext 


# Playwright system dependencies for Linux
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxcb1 \
    libxkbcommon0 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libatspi2.0-0 \
    && rm -rf /var/lib/apt/lists/*


RUN pip install --upgrade pip
COPY ./requirements.txt .
RUN pip install -r requirements.txt
RUN  playwright install 
RUN crawl4ai-setup



# Download Python source (Needed for internationalization) 
RUN wget https://www.python.org/ftp/python/3.11.0/Python-3.11.0.tgz \
    && tar xzf Python-3.11.0.tgz \
    && mv Python-3.11.0 /usr/local/src/ \
    && rm Python-3.11.0.tgz 


# Copy the rest of the application code into the container
COPY . .

# Compile the .po file into a .mo file
#RUN ls -l /usr/local/src/Python-3.11.0/Tools/i18n/msgfmt.py
RUN chmod +x /usr/local/src/Python-3.11.0/Tools/i18n/msgfmt.py
RUN  /usr/local/src/Python-3.11.0/Tools/i18n/msgfmt.py /app/locale/de/LC_MESSAGES/base.po /app/locale/de/LC_MESSAGES/base

# Expose the port that Streamlit will run on
EXPOSE 8501

CMD ["sh", "-c", "cd db && python3 vector_store.py --create_db true && cd .. && streamlit run start.py"]
