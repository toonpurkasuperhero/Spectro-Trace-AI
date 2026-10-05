FROM python:3.11-slim

# Install system dependencies for audio decoding, image processing, and exiftool
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    libimage-exiftool-perl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install (supports both root context and api subfolder context)
COPY requirements.txt* api/requirements.txt* ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app:/app/api

CMD ["sh", "-c", "if [ -f main.py ]; then uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}; else uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}; fi"]
