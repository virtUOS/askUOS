FROM python:3.11.0

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    wget \
    gnupg \
    git \
    cmake \
    vim \
    pkg-config \
    python3-dev \
    libjpeg-dev \
    libpng-dev \
    && rm -rf /var/lib/apt/lists/*

COPY . .

# Download and install uv
ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh
# Ensure the installed binary is on the `PATH`
ENV PATH="/root/.local/bin:$PATH"

# Create venv and install deps
RUN uv sync --frozen

ENV PATH="/app/.venv/bin:$PATH"

RUN echo $PATH
RUN echo $(which python)
RUN echo $(which streamlit)

#######----- the locale files are compiled locally, they are mounted/baked into the image-----#####

# Download Python source for i18n
# RUN wget https://www.python.org/ftp/python/3.11.0/Python-3.11.0.tgz \
#     && tar xzf Python-3.11.0.tgz \
#     && mv Python-3.11.0 /usr/local/src/ \
#     && rm Python-3.11.0.tgz

# RUN /usr/local/src/Python-3.11.0/Tools/i18n/msgfmt.py \
#     && /usr/local/src/Python-3.11.0/Tools/i18n/msgfmt.py \
#        /app/locale/de/LC_MESSAGES/base.po \
#        /app/locale/de/LC_MESSAGES/base


# Dev-in-container git config
RUN git config --global --add safe.directory /app

# Expose the port that Streamlit will run on
EXPOSE 8501