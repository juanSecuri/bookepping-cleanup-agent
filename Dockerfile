# LedgerAI — Docker image with Tesseract OCR (Render Starter + persistent disk)
FROM python:3.11-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-spa \
    ffmpeg \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Node for frontend build
FROM base AS frontend-build
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Vite embeds these at build time (set on Render service env).
ARG VITE_SUPABASE_URL=
ARG VITE_SUPABASE_ANON_KEY=
ARG VITE_API_URL=
ENV VITE_SUPABASE_URL=$VITE_SUPABASE_URL \
    VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY \
    VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM base AS app
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY apps ./apps
COPY migrations ./migrations
COPY run.py ./
RUN pip install --upgrade pip && pip install -e .

COPY --from=frontend-build /app/frontend/dist ./frontend/dist

EXPOSE 8000
CMD ["python", "run.py"]
