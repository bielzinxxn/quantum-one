# syntax=docker/dockerfile:1.7
# Imagem única do backend: todos os workers, a API e o job de migração.
# Imagem base fixada por digest (rodar `make pin-images` para atualizar conscientemente).

ARG PYTHON_IMAGE=python:3.12.16-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b

FROM ${PYTHON_IMAGE} AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never PIP_NO_CACHE_DIR=1
WORKDIR /app
# CA extra OPCIONAL (só para quem compila atrás de proxy com inspeção TLS):
#   docker build --secret id=extra_ca,src=/caminho/ca.pem ...
# Sem o secret, o build usa as CAs públicas normais.
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -f /run/secrets/extra_ca ]; then export PIP_CERT=/run/secrets/extra_ca; fi; \
    pip install "uv==0.11.32"
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -f /run/secrets/extra_ca ]; then export SSL_CERT_FILE=/run/secrets/extra_ca; fi; \
    uv sync --frozen --no-dev --no-install-project
COPY backend/src ./src
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -f /run/secrets/extra_ca ]; then export SSL_CERT_FILE=/run/secrets/extra_ca; fi; \
    uv sync --frozen --no-dev --no-editable

FROM ${PYTHON_IMAGE} AS runtime
RUN groupadd --system --gid 10001 q1 \
 && useradd --system --uid 10001 --gid q1 --no-create-home --shell /usr/sbin/nologin q1
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY backend/alembic.ini ./alembic.ini
COPY backend/migrations ./migrations
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HEALTH_PORT=8080
USER q1:q1
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-m", "quantum_one.services.healthcheck", "/health/live"]
CMD ["python", "-m", "quantum_one.services.cli", "engine"]
