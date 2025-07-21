FROM python:3.11 as builder

# Set the working directory inside the container
WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    sudo \
    wget \
    gettext \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python packages
RUN pip install --upgrade pip
COPY ./requirements.txt .
RUN pip install -r requirements.txt

# Download Python source for internationalization
RUN wget https://www.python.org/ftp/python/3.11.0/Python-3.11.0.tgz \
    && tar xzf Python-3.11.0.tgz \
    && mv Python-3.11.0 /usr/local/src/ \
    && rm Python-3.11.0.tgz

# Copy application code and compile messages
COPY . .
RUN chmod +x /usr/local/src/Python-3.11.0/Tools/i18n/msgfmt.py
RUN /usr/local/src/Python-3.11.0/Tools/i18n/msgfmt.py /app/locale/de/LC_MESSAGES/base.po /app/locale/de/LC_MESSAGES/base

# Final stage
FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# Install runtime dependencies
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

# Copy only necessary files from builder

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY --from=builder /app/locale /app/locale
COPY --from=builder /app /app


RUN echo $PATH
RUN echo $(which python)


# Install Playwright browsers
RUN playwright install
RUN crawl4ai-setup

# Needed for dev in container
RUN apt-get install git -y
RUN git config --global --add safe.directory /app
# Expose the port that Streamlit will run on
EXPOSE 8501

