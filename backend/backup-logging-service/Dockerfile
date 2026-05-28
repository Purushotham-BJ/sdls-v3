FROM python:3.11-slim
WORKDIR /app
COPY backend/shared /app/shared
COPY backend/backup-logging-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/backup-logging-service /app
ENV PYTHONPATH=/app:/app/shared
CMD ["python", "app.py"]
