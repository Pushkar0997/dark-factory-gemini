# Stage 3 — Run Specification

## Container Build

```bash
docker build -t stage-3 .
```

## Container Execution

```bash
docker run -p 8080:8080 -e PORT=8080 stage-3
```

## Health Check

```bash
curl -f http://localhost:8080/health
```

## Status & Provenance
- **Status**: Scaffolding / Placeholder (Pending Live Factory Execution)
- **Target Contract**: Complete Stage 3 solution (Stage 2 carried forward + Temporal state & historical records).
