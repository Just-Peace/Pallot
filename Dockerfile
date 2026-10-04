# Pallot in a container: see compose.yaml, the README ("Quick start", "Docker") and
# DEVELOPMENT.md ("Docker image").

# Build: Pallot and its locked dependencies (no dev tools) installed into /app/.venv.
FROM python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app
# the dependencies first, so a code change doesn't reinstall them
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project --no-editable
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable
# the commit, for the footer: the run stage has no .git. -P writes it into the installed
# package, not the copy of the source in /app.
RUN .venv/bin/python -P -m pallot.version /app

# Run: just the venv; everything Pallot writes goes to /data (a volume).
FROM python:3.13-slim
RUN useradd --create-home --uid 1000 pallot && mkdir /data && chown pallot:pallot /data
COPY --from=build /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH PALLOT_DATA_DIR=/data PYTHONUNBUFFERED=1
USER pallot
EXPOSE 8000
# 0.0.0.0 inside the container, or the published port can't reach it; which host
# interfaces it's published on is up to compose.yaml
CMD ["pallot", "--host", "0.0.0.0", "--port", "8000"]
