FROM python:3.12-slim AS server

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Only what server.py imports. The db package ships without its schema files and one-off-migration modules.
COPY server.py ./
COPY config/*.py ./config/
COPY tools/*.py ./tools/
COPY db/__init__.py db/scripture.py ./db/

EXPOSE 7363

CMD ["python", "server.py"]


# Build and load tools: run as `docker compose run --rm tools scripts/<script>.py ...`.
FROM server AS tools

COPY scripts/ ./scripts/
COPY api/ ./api/
COPY process_topic_talks/ ./process_topic_talks/
COPY extractors/ ./extractors/
COPY loaders/ ./loaders/
COPY models/ ./models/
COPY utils/ ./utils/
COPY db/scripture_schema.sql ./db/
COPY db/one-off-migration/ ./db/one-off-migration/

CMD ["python", "scripts/build.py", "--help"]
