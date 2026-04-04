FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Fixed container-internal paths (D-06, D-07) — NOT operator-facing
ENV CHROMADB_PATH=/data/chromadb
ENV AUTH_DB_PATH=/data/auth.db

# Default host/port — overridable via .env / env_file in compose
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8000

EXPOSE 8000

CMD ["python", "server.py"]
