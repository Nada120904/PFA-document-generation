FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir --upgrade pip && \
    python -c "import tomllib, pathlib, subprocess; deps = tomllib.loads(pathlib.Path('/app/services/upload_service/pyproject.toml').read_text(encoding='utf-8'))['project']['dependencies']; subprocess.check_call(['pip', 'install', '--no-cache-dir', *deps])"

EXPOSE 8000

CMD ["uvicorn", "services.upload_service.app:app", "--host", "0.0.0.0", "--port", "8000"]
