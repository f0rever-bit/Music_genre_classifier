# Stage 1: Build the React frontend
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package.json ./
RUN npm install

COPY frontend/ ./
RUN npm run build

# Stage 2: Backend & Production
FROM python:3.10-slim
WORKDIR /app

# Install system dependencies for audio processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy backend requirements
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ .

# Create required directories
RUN mkdir -p /app/uploads /app/models /app/static

# Copy frontend build output to backend static directory
COPY --from=frontend-builder /app/frontend/dist /app/static

# Run lint check (non-blocking)
RUN ruff check . --exit-zero

# Expose port (Cloud providers like Fly.io use 8080 by default, but we can override it)
EXPOSE 8000
EXPOSE 8080

# Run migrations and start server
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]
