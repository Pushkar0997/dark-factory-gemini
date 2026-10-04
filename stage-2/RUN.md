# Stage 2 — Run Specification

## Container Build

```bash
docker build -t stage-2 .
```

## Container Execution

```bash
docker run -p 8080:8080 -e PORT=8080 stage-2
```

## Health Check

```bash
curl -f http://localhost:8080/health
```

## Status & Provenance
- **Status**: Scaffolding / Placeholder (Pending Live Factory Execution)
- **Target Contract**: Complete Stage 2 solution (Stage 1 carried forward + Browser UI & extended resources).
