# Tablekeeper stage 1

```sh
docker build -t tablekeeper-s1 . && docker run --rm -e PORT=8080 -p 8080:8080 tablekeeper-s1
```

The service listens on `0.0.0.0:$PORT` (default 8080). No other setup is needed; state is in memory.

Black-box tests (against a running container):

```sh
BASE=http://localhost:8080 python3 tests/test_api.py
```
