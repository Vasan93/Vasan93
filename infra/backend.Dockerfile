FROM python:3.12-slim

# Stockfish provides engine ground truth. lc0 (for Maia sparring) is optional and
# installed separately -- see engines/README.md.
RUN apt-get update \
 && apt-get install -y --no-install-recommends stockfish build-essential \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend backend
COPY data data

ENV PYTHONPATH=/app/backend STOCKFISH_PATH=/usr/games/stockfish
WORKDIR /app/backend
EXPOSE 8000
CMD ["sh", "-c", "python -m app.bootstrap && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
