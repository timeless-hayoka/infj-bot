FROM python:3.12-slim

WORKDIR /app

# System deps: build tools for native packages + audio libs for voice
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev libssl-dev \
    libsndfile1 portaudio19-dev \
    sqlite3 curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (layer cache — only rebuilds on requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy project code
COPY . .

# Data directory — override with INFJ_DATA_DIR env var to use PortableSSD
RUN mkdir -p /app/chroma_db /app/data

# Default port for web UI (Hugging Face Spaces routes here)
EXPOSE 7860

# Default: run web interface
CMD ["python", "interfaces/web_app.py"]
