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

```bash
pipenv run python process_entries.py
```

This will:
- Read entries from `results.json`
- Make concurrent API requests for each entry
- Extract data-aid from h1 tags in HTML content
- Save results to `data_aids.json`

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
    "successful_extractions": 48
  }
]
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
├── topics.json            # Input: Your topics list
├── results.json           # Intermediate: Topics and entries
└── data_aids.json         # Output: Final data-aid results
```

## License

MIT
