# ==============================================================================
# STAGE-1 PLACEHOLDER DOCKERFILE
# ==============================================================================
# This stage directory is prepared for autonomous generation by the Dark Factory.
# The Builder agent will replace this with the real service container definition
# during the live Band room execution.
#
# Runtime Contract:
# - Listens on 0.0.0.0:$PORT (default 8080)
# - Responds to GET /health with 200 OK within 60s
# - Operates with 0 outbound network access at runtime
# ==============================================================================
FROM alpine:3.20
RUN echo "Stage 1 pending factory execution" > /status.txt
EXPOSE 8080
CMD ["sh", "-c", "echo 'Stage 1 pending factory implementation'; sleep 1; exit 1"]
