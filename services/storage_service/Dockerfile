FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /service

COPY requirements.txt ./
COPY .env ./.env
COPY .env.example ./.env.example
COPY refresh_token.txt ./refresh_token.txt

RUN pip install --no-cache-dir --upgrade pip &&     pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
