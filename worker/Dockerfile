FROM python:3.11-slim
WORKDIR /app
# Install system dependencies for NLTK
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Download NLTK data
RUN python -c "import nltk; nltk.download('vader_lexicon', quiet=True); nltk.download('punkt', quiet=True)"
COPY . .
CMD ["python", "worker.py"]
