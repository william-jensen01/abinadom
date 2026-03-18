# Topic & Entry Data Processor

A multi-threaded Python application to process topics and extract data from API endpoints.

## Overview

This project consists of two scripts:
1. **process_topics.py** - Fetches topic data and extracts entries
2. **process_entries.py** - Multi-threaded processing of entries to extract data-aid values

## Setup

### Prerequisites
- Python 3.7+
- pipenv

### Installation

1. Install pipenv if you haven't already:
```bash
pip install pipenv
```

2. Navigate to the project directory and install dependencies:
```bash
pipenv install
```

3. Activate the virtual environment:
```bash
pipenv shell
```

## Configuration

### Step 1: Configure process_topics.py

Edit `process_topics.py` and update:
- `BASE_URL`: Your API base URL for topics
- `TOPICS_FILE`: Path to your topics.json file (default: "topics.json")
- `OUTPUT_FILE`: Output filename (default: "results.json")

### Step 2: Configure process_entries.py

Edit `process_entries.py` and update:
- `BASE_URL`: Your API base URL for entries
- `INPUT_FILE`: Input from first script (default: "results.json")
- `OUTPUT_FILE`: Output filename (default: "data_aids.json")
- `MAX_WORKERS`: Number of concurrent threads (default: 15, adjust based on API limits)

## Usage

### Step 1: Process Topics

```bash
pipenv run python process_topics.py
```

This will:
- Read topics from `topics.json`
- Fetch data for each topic
- Extract entries from collection sections
- Save results to `results.json`

### Step 2: Process Entries

**Process all topics:**
```bash
pipenv run python process_entries.py
```

**Process a specific topic:**
```bash
pipenv run python process_entries.py --topic "Priesthood"
```

**Process with custom settings:**
```bash
pipenv run python process_entries.py --topic "Priesthood" --workers 20 --output priesthood_results.json
```

**Available options:**
- `--topic, -t`: Specific topic name to process (case-insensitive)
- `--input, -i`: Input file path (default: results.json)
- `--output, -o`: Output file path (default: data_aids.json)
- `--errors, -e`: Error log file path (default: errors.json)
- `--workers, -w`: Number of concurrent threads (default: 15)
- `--base-url, -u`: API base URL

This will:
- Read entries from `results.json` (or specified input file)
- Search for the specified topic if provided
- Make concurrent API requests for each entry
- Extract data-aid from h1 tags in HTML content
- Save results to `data_aids.json` (or specified output file)
- Save detailed error information to `errors.json`

### Step 3: Build SQLite Database

**Build database from all results:**
```bash
pipenv run python build_database.py
```

**Build with custom files:**
```bash
pipenv run python build_database.py --input data_aids.json --output content.db
```

**Recreate database (drop existing tables):**
```bash
pipenv run python build_database.py --recreate
```

**Available options:**
- `--input, -i`: Input JSON file (default: data_aids.json)
- `--output, -o`: Output database file (default: content.db)
- `--recreate`: Drop and recreate tables (default: update existing)

This will:
- Create SQLite database with two tables: `topics` and `content_references`
- Populate topics with metadata (total entries, success counts)
- Store all content identifiers (data-aids) with topic relationships
- Create indexes for efficient queries
- Display statistics about the database

## Input Format

### topics.json
```json
[
  {
    "title": "Topic Name",
    "uri": "/path/to/topic"
  }
]
```

## Output Format

### results.json (from process_topics.py)
```json
[
  {
    "topic": "Topic Name",
    "entries": [
      {
        "uri": "/path/to/entry",
        ...other entry fields
      }
    ]
  }
]
```

### data_aids.json (from process_entries.py)
```json
[
  {
    "topic": "Topic Name",
    "data_aids": ["aid1", "aid2", "aid3"],
    "total_entries": 50,
    "successful_extractions": 48,
    "failed_extractions": 2,
    "all_results": [
      {
        "index": 0,
        "uri": "/path/to/entry",
        "title": "Entry Title",
        "data_aid": "aid1",
        "success": true,
        "error": null
      }
    ],
    "errors": [
      {
        "topic": "Topic Name",
        "index": 5,
        "uri": "/path/to/failed/entry",
        "title": "Failed Entry",
        "error": "Error message"
      }
    ]
  }
]
```

### errors.json (detailed error log)
```json
[
  {
    "topic": "Topic Name",
    "index": 5,
    "uri": "/path/to/entry",
    "title": "Entry Title",
    "error": "Detailed error message"
  }
]
```

## Database Schema

### content.db (SQLite Database)

**topics table:**
- `topic_id` (INTEGER PRIMARY KEY): Unique identifier for topic
- `topic_name` (TEXT UNIQUE): Name of the topic
- `total_entries` (INTEGER): Total number of entries for this topic
- `successful_extractions` (INTEGER): Number of successful extractions
- `created_at` (TIMESTAMP): When the topic was first added
- `updated_at` (TIMESTAMP): When the topic was last updated

**content_references table:**
- `reference_id` (INTEGER PRIMARY KEY): Unique identifier for content reference
- `topic_id` (INTEGER FOREIGN KEY): References topics table
- `content_identifier` (TEXT): The extracted data-aid value
- `entry_uri` (TEXT): URI of the source entry
- `entry_title` (TEXT): Title of the source entry
- `entry_index` (INTEGER): Original index in the entries list
- `extracted_at` (TIMESTAMP): When the reference was extracted

**Indexes:**
- Index on `content_references.topic_id` for fast topic queries
- Index on `content_references.content_identifier` for fast identifier lookups

## Database Querying

### Using SQLite CLI

```bash
sqlite3 content.db
```

**Example queries:**

```sql
-- View all topics
SELECT * FROM topics;

-- Get all content identifiers for a topic
SELECT content_identifier, entry_title 
FROM content_references cr
JOIN topics t ON cr.topic_id = t.topic_id
WHERE t.topic_name = 'Priesthood';

-- Find topics containing a specific identifier
SELECT t.topic_name
FROM topics t
JOIN content_references cr ON t.topic_id = cr.topic_id
WHERE cr.content_identifier = 'your-id-here';

-- Count references per topic
SELECT t.topic_name, COUNT(cr.reference_id) as count
FROM topics t
LEFT JOIN content_references cr ON t.topic_id = cr.topic_id
GROUP BY t.topic_id
ORDER BY count DESC;
```

See `queries.sql` for more example queries.

### Using Python

```python
import sqlite3

conn = sqlite3.connect('content.db')
cursor = conn.cursor()

# Get all content for a topic
cursor.execute('''
    SELECT content_identifier, entry_title
    FROM content_references cr
    JOIN topics t ON cr.topic_id = t.topic_id
    WHERE t.topic_name = ?
''', ('Priesthood',))

for content_id, title in cursor.fetchall():
    print(f"{content_id}: {title}")

conn.close()
```

## Performance Tuning

### Adjusting Concurrency

The `MAX_WORKERS` parameter in `process_entries.py` controls how many concurrent API requests are made:

- **Lower values (5-10)**: More conservative, better for rate-limited APIs
- **Higher values (15-20)**: Faster processing, ensure your API can handle it
- **Very high values (20+)**: Only if your API has no rate limits

### Rate Limiting Considerations

If you encounter rate limiting:
1. Reduce `MAX_WORKERS` value
2. Add delays between requests (can be implemented in the script)
3. Check your API's rate limit documentation

## Troubleshooting

### Common Issues

**Import errors**: Make sure you're in the pipenv shell
```bash
pipenv shell
```

**API errors**: Verify your BASE_URL is correct and API is accessible

**Timeout errors**: Increase timeout in `fetch_entry_data()` method or reduce `MAX_WORKERS`

**Memory issues with large datasets**: Process topics in batches

## Project Structure

```
.
├── Pipfile                 # Pipenv dependencies
├── Pipfile.lock           # Locked dependencies (generated)
├── process_topics.py      # Step 1: Process topics
├── process_entries.py     # Step 2: Process entries (multi-threaded)
├── build_database.py      # Step 3: Build SQLite database
├── queries.sql            # Example SQL queries
├── topics.json            # Input: Your topics list
├── results.json           # Intermediate: Topics and entries
├── data_aids.json         # Intermediate: Final data-aid results
├── errors.json            # Output: Detailed error log
└── content.db             # Output: SQLite database
```

## License

MIT
