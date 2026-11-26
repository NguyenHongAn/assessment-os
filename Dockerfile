FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY main.py ./

RUN useradd --create-home --shell /bin/sh appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app

USER appuser

ENTRYPOINT ["python", "main.py"]
