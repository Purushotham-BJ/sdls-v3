FROM python:3.11-slim
WORKDIR /app
COPY backend/shared /app/shared
COPY backend/notification-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/notification-service /app
ENV PYTHONPATH=/app:/app/shared
CMD ["python", "app.py"]
