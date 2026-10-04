# Stage 1 — Run Specification

## Container Build

```bash
docker build -t stage-1 .
```

## Container Execution

```bash
docker run -p 8080:8080 -e PORT=8080 stage-1
```

## Health Check

```bash
curl -f http://localhost:8080/health
```

## Status & Provenance
- **Status**: Scaffolding / Placeholder (Pending Live Factory Execution)
- **Target Contract**: Complete Stage 1 API conforming to chosen competition specification.
- **Rule Compliance**: Code must be generated exclusively through Band room collaboration between `@Planner`, `@Builder`, and `@Reviewer`.
