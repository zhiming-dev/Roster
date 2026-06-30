# Roster runtime container image.
#
# IMPORTANT: the Docker build context is the REPOSITORY ROOT (see
# docker-compose.yml -> build.context: ..). Each agent's config references
# markdown files that live OUTSIDE runtime/ (e.g. ../planner-agent/planner.agent.md),
# so the whole repo tree must be available inside the image.

# ---- Stage 1: build the React dashboard SPA (spec 002) ----------------------------
# Vite emits to ../runtime/static/app (frontend/vite.config.ts) = /runtime/static/app in
# this stage; the runtime stage copies it in. Building here keeps the image self-contained
# with no committed build artifacts and no legacy HTML fallback.
FROM node:20-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* /frontend/
RUN npm install
COPY frontend/ /frontend/
RUN npm run build

# ---- Stage 2: the Python runtime --------------------------------------------------
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # SQLite DB + run artifacts live under /data, which is a mounted volume so
    # conversation history survives container restarts.
    ROSTER_DB_PATH=/data/roster.db \
    ROSTER_RUNS_DIR=/data/runs

WORKDIR /app

# Install dependencies first for better layer caching.
COPY runtime/requirements.txt /app/runtime/requirements.txt
RUN pip install -r /app/runtime/requirements.txt

# Copy the agent/skill markdown tree + runtime source.
COPY . /app

# Bring in the dashboard built in the frontend stage (provides it when the build context
# has none, and overrides any stale local build copied from the context).
COPY --from=frontend /runtime/static/app /app/runtime/static/app

# The runtime resolves relative paths (../<role>-agent/...) from runtime/.
WORKDIR /app/runtime

EXPOSE 8765
VOLUME ["/data"]

# Bind 0.0.0.0 so the published port is reachable from the host.
CMD ["python", "-m", "roster", "--host", "0.0.0.0", "--port", "8765"]
