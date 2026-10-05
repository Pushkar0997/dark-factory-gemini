# Tablekeeper stage 4

```sh
docker build -t tablekeeper-s4 . && docker run --rm -e PORT=8080 -p 8080:8080 tablekeeper-s4
```

The service listens on `0.0.0.0:$PORT` (default 8080). No other setup is needed; state is in memory.

Black-box tests (against a running container):

```sh
BASE=http://localhost:8080 python3 tests/test_api.py
```

Browser UI: open http://localhost:8080/ (screens `/`, `/signup`, `/login`, `/lookup`). All assets are served from the container.
Stage-3 tests: `BASE=http://localhost:8080 python3 tests/test_stage3.py` (browser tests: `tests/test_ui.py`, needs Playwright).
