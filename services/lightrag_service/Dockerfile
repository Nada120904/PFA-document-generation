FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY . /app
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/services/lightrag_service/requirements.txt

EXPOSE 8000
CMD ["uvicorn", "services.lightrag_service.app:app", "--host", "0.0.0.0", "--port", "8000"]
