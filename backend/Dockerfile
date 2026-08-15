# AgentDock backend — FastAPI on uvicorn.
FROM python:3.12-slim

WORKDIR /app

# Install deps first so the layer caches across code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Bind to all interfaces inside the container; the host/orchestrator maps the
# port. The app reads MONGO_URL, DB_NAME, CORS_ORIGINS, BSC_* and the 8004scan
# key from the environment — never baked into the image.
EXPOSE 8000
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
