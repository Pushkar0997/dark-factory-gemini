# Stage 4 — Run Specification

## Container Build

```bash
docker build -t stage-4 .
```

## Container Execution

```bash
docker run -p 8080:8080 -e PORT=8080 stage-4
```

## Health Check

```bash
curl -f http://localhost:8080/health
```

## Status & Provenance
- **Status**: Scaffolding / Placeholder (Pending Live Factory Execution)
- **Target Contract**: Complete Stage 4 solution (Stage 3 carried forward + Batch/replanning atomic multi-record operations).
