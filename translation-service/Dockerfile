FROM python:3.11-slim

WORKDIR /app

COPY translation-service/requirements.txt /app/translation-service/requirements.txt
RUN pip install --no-cache-dir -r /app/translation-service/requirements.txt

COPY backend/app/translation_engine /app/backend/app/translation_engine
COPY translation-service/translation_service /app/translation-service/translation_service

ENV PYTHONPATH=/app/translation-service:/app/backend/app
EXPOSE 8001

CMD ["uvicorn", "translation_service.main:app", "--host", "0.0.0.0", "--port", "8001"]
