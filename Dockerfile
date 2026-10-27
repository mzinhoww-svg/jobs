# syntax=docker/dockerfile:1
FROM python:3.12.14-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN --mount=type=secret,id=system_ca,required=true \
    apt-get -o Acquire::https::CaInfo=/run/secrets/system_ca update \
    && apt-get -o Acquire::https::CaInfo=/run/secrets/system_ca install -y --no-install-recommends chromium fonts-dejavu-core ca-certificates poppler-utils \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.lock ./
RUN --mount=type=secret,id=system_ca,required=true \
    PIP_CERT=/run/secrets/system_ca pip install --no-cache-dir --require-hashes -r requirements.lock
RUN groupadd -g 10001 jobs && useradd --uid 10001 --gid 10001 --no-create-home jobs \
    && mkdir -p /var/lib/jobs && chown jobs:jobs /var/lib/jobs
COPY --chown=10001:10001 jobs_service ./jobs_service
COPY --chown=10001:10001 tests ./tests
USER 10001:10001
ENV JOBS_DATA_DIR=/var/lib/jobs JOBS_CHROMIUM=/usr/bin/chromium HOME=/tmp XDG_CONFIG_HOME=/tmp/.config XDG_CACHE_HOME=/tmp/.cache
EXPOSE 8787
CMD ["python","-m","uvicorn","jobs_service.api:factory","--factory","--host","0.0.0.0","--port","8787","--no-access-log"]
