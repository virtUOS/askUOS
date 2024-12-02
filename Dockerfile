# Use the official Python image from Docker Hub
FROM python:3.11

# Set the working directory inside the container
WORKDIR /app

# Install dependencies
RUN apt-get update && apt-get install -y \
    sudo \
    wget \
    firefox-esr \
    gettext 

RUN pip install --upgrade pip
COPY ./requirements.txt .
RUN pip install -r requirements.txt



# Download Python source (Needed for internationalization) 
RUN wget https://www.python.org/ftp/python/3.11.0/Python-3.11.0.tgz \
    && tar xzf Python-3.11.0.tgz \
    && mv Python-3.11.0 /usr/local/src/ \
    && rm Python-3.11.0.tgz 

# Download and install geckodriver
RUN wget https://github.com/mozilla/geckodriver/releases/download/v0.34.0/geckodriver-v0.34.0-linux64.tar.gz && \
    tar -xvzf geckodriver-v0.34.0-linux64.tar.gz && \
    chmod +x geckodriver && \
    mv geckodriver /usr/local/bin/

# Clean up
RUN rm geckodriver-v0.34.0-linux64.tar.gz

# Copy the rest of the application code into the container
COPY . .

# Compile the .po file into a .mo file
#RUN ls -l /usr/local/src/Python-3.11.0/Tools/i18n/msgfmt.py
RUN chmod +x /usr/local/src/Python-3.11.0/Tools/i18n/msgfmt.py
RUN  /usr/local/src/Python-3.11.0/Tools/i18n/msgfmt.py /app/locale/de/LC_MESSAGES/base.po /app/locale/de/LC_MESSAGES/base

# Expose the port that Streamlit will run on
EXPOSE 8501

CMD ["sh", "-c", "cd db && python3 vector_store.py --create_db true && cd .. && streamlit run start.py"]
