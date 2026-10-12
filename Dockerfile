FROM ghcr.io/astral-sh/uv:0.11.28 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 POC_DATA_DIR=/data
COPY pyproject.toml uv.lock ./
COPY src ./src
COPY config ./config
RUN uv sync --locked --no-dev --no-editable --python /usr/local/bin/python \
    && groupadd --gid 1000 poc \
    && useradd --uid 1000 --gid poc --create-home poc \
    && mkdir -p /data \
    && chown -R poc:poc /data
ENV PATH="/app/.venv/bin:$PATH"
USER poc
ENTRYPOINT ["python", "-m", "poc"]
CMD ["--help"]
