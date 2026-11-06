# Daily YouTube Digest

## Running tests

Run the test suite from the project root (the directory containing `pyproject.toml`):

```shell
uv run python -m unittest discover -s tests -v
```

To run only the YouTube RSS tests:

```shell
uv run python -m unittest discover -s tests -p test_youtube.py -v
```

If your terminal is currently in the `tests` directory, return to the project root first:

```shell
cd ..
uv run python -m unittest discover -s tests -v
```

Running unittest discovery from the project root also ensures the application package can be imported by the tests.