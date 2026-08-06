FROM python:3.11-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

RUN apt-get update && apt-get install -y libmupdf-dev libssl-dev libffi-dev build-essential && rm -rf /var/lib/apt/lists/*
RUN python -m venv .venv
COPY requirements.txt ./
RUN .venv/bin/pip install -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y libmupdf libssl3 && rm -rf /var/lib/apt/lists/*
COPY --from=builder /app/.venv .venv/
COPY . .

# Add venv to PATH so gunicorn can be found
ENV PATH="/app/.venv/bin:$PATH"

CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:app"]
