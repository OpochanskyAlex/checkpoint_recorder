FROM python:3.13-slim

WORKDIR /app

# Install dependencies first (layer cache)
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]" 2>/dev/null || true

# Copy source
COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .

# Install the package properly now that src/ exists
RUN pip install --no-cache-dir -e .

COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

CMD ["./entrypoint.sh"]
