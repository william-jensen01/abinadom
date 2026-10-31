## Commands

```bash
pipenv run python -m pytest                                        # all tests
pipenv run python -m pytest tests/test_build.py::TestName::test_x  # one test
pipenv run python server.py                                        # needs Weaviate + EMBEDDING_URL
```

## Rules

- Docker installs from `requirements.txt`; after dependency changes run `pipenv requirements > requirements.txt`.
- Open database files only through `scripts/db_schema_extractor.py` with specific arguments.
