FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default host/port — overridable via .env / env_file in compose
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=7363

EXPOSE 7363

CMD ["python", "server.py"]
