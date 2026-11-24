## Commands

```bash
pipenv run python -m pytest                                        # all tests
pipenv run python -m pytest tests/test_build.py::TestName::test_x  # one test
SCI_TEST_DB_DIR=<main checkout>/db pipenv run python -m pytest     # in a git worktree (no db/*.db): read the real dbs from there
SCI_TEST_SKIP_REAL_DB=1 pipenv run python -m pytest                # skip the real-db tests on purpose (otherwise a missing db fails them)
pipenv run python server.py                                        # needs Weaviate + EMBEDDING_URL
```

## Rules

- Docker installs from `requirements.txt`; after dependency changes run `pipenv requirements > requirements.txt`.
- Open database files only through `scripts/db_schema_extractor.py` with specific arguments.
