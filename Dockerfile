# syntax=docker/dockerfile:1
FROM python:3.14.10-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.11.3 /uv /usr/local/bin/uv
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"
WORKDIR /srv
COPY pyproject.toml uv.lock ./

FROM base AS runtime
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app
COPY db ./db
RUN useradd --system --uid 10001 appuser
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

FROM base AS test
RUN uv sync --frozen --no-install-project
COPY app ./app
COPY db ./db
COPY tests ./tests
RUN mkdir -p docs
COPY --chmod=644 docs/Firm_Payments_Test_Scenarios.md ./docs/Firm_Payments_Test_Scenarios.md
RUN useradd --system --uid 10001 runner && mkdir -p /srv/results && chown runner /srv/results
USER runner
CMD ["pytest", "tests", "-p", "no:cacheprovider"]
