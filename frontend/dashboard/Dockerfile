FROM python:3.11-slim
WORKDIR /app
COPY backend/shared /app/shared
COPY frontend/dashboard/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY frontend/dashboard /app
ENV PYTHONPATH=/app:/app/shared
CMD ["python", "app.py"]
