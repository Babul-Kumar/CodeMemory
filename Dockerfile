FROM python:3.10-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

FROM python:3.10-slim AS runner

WORKDIR /app

# Copy installed site-packages and entry points from builder
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy codebase
COPY codememory /app/codememory
COPY pyproject.toml README.md /app/

# Expose HTTP / SSE port
EXPOSE 8000

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Default repository to serve is /repo
VOLUME /repo

CMD ["codememory", "serve", "/repo", "--host", "0.0.0.0", "--port", "8000"]
