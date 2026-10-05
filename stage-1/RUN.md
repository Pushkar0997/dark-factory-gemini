# Tablekeeper stage 1

```sh
docker build -t tablekeeper-s1 . && docker run --rm -e PORT=8080 -p 8080:8080 tablekeeper-s1
```
