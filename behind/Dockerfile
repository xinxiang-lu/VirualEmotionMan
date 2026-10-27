FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY behind/requirements.txt /tmp/requirements.txt

RUN python -m pip install --upgrade pip \
    && pip install -r /tmp/requirements.txt

COPY . /app

RUN mkdir -p /app/behind/data /app/behind/static/audio

EXPOSE 5000

CMD ["python", "-m", "flask", "--app", "behind.wsgi:app", "run", "--host", "0.0.0.0", "--port", "5000", "--no-reload"]
