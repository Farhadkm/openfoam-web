FROM python:3.12-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services ./services
COPY shared ./shared
# Scalar /api-docs (explicit so image rebuilds when static changes)
COPY services/bff/static ./services/bff/static
RUN mkdir -p /app/credentials

ENV JOBS_ROOT=/jobs
ENV MONGODB_URI=mongodb://mongo:27017
ENV MONGODB_DB=forge_web
ENV SIMULATION_SERVICE_URL=http://simulation:8001
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

EXPOSE 8000 8001 8003 8080 8081 8082

# Default: BFF (browser API). Override CMD per service in Compose.
CMD ["uvicorn", "services.bff.app:app", "--host", "0.0.0.0", "--port", "8000"]
