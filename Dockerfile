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
COPY db/one-off-migration/*.py db/one-off-migration/*.sql db/one-off-migration/talk_corrections.json ./db/one-off-migration/

# scripts/fetch.py rewrites these in place and runs as whatever uid compose passes, so they are writable by any uid.
# It also keeps its HTTP cache (http_cache.sqlite and its journal) in /app, which needs room to create them.
COPY --chmod=0666 topics.json ./
COPY --chmod=0666 db/one-off-migration/talk_metadata.json db/one-off-migration/talk_previews.json db/one-off-migration/conference_topics.json ./db/one-off-migration/
RUN chmod 1777 /app

CMD ["python", "scripts/build.py", "--help"]
