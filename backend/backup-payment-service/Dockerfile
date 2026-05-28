FROM python:3.11-slim
WORKDIR /app
COPY backend/shared /app/shared
COPY backend/backup-payment-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/backup-payment-service /app
ENV PYTHONPATH=/app:/app/shared
CMD ["python", "app.py"]
