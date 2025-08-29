FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
  && apt-get install -y --no-install-recommends build-essential gcc ca-certificates \
  && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash bot \
  && mkdir -p /app \
  && chown bot:bot /app

WORKDIR /app

COPY source/requirements.txt /app/source/requirements.txt

RUN python -m pip install --upgrade pip \
  && pip install --no-cache-dir -r /app/source/requirements.txt

COPY source /app/source
COPY setup.py /app/setup.py
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

USER bot
WORKDIR /app/source

ENTRYPOINT ["/app/entrypoint.sh"]
