FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    libportaudio2 \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.11.0
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir cloud-sql-python-connector pg8000 sqlalchemy

COPY . .

# Install the drift package in editable mode
RUN pip install -e .

EXPOSE 8000
ENV PORT=8000

CMD ["python", "-m", "drift.interfaces.api"]
