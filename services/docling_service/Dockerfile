FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HF_HOME=/opt/huggingface
ENV HF_HUB_CACHE=/opt/huggingface/hub
ENV EASYOCR_MODEL_STORAGE_DIRECTORY=/opt/easyocr
ENV HF_HUB_DISABLE_SSL_VERIFICATION=1
ENV PYTHONHTTPSVERIFY=0

WORKDIR /app

COPY . /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libglib2.0-0 \
    libgl1 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libxcb1 \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /opt/huggingface/hub /opt/easyocr

RUN pip install --no-cache-dir --upgrade pip && \
    python -c "import tomllib, pathlib, subprocess; deps = tomllib.loads(pathlib.Path('/app/services/docling_service/pyproject.toml').read_text(encoding='utf-8'))['project']['dependencies']; subprocess.check_call(['pip', 'install', '--no-cache-dir', *deps])"

RUN python - <<'PY'
from pathlib import Path
import site

sitecustomize = Path(site.getsitepackages()[0]) / "sitecustomize.py"
sitecustomize.write_text(
    """
import ssl

ssl._create_default_https_context = ssl._create_unverified_context

try:
    import requests.sessions
    _orig_request = requests.sessions.Session.request
    def _request(self, method, url, **kwargs):
        kwargs.setdefault("verify", False)
        return _orig_request(self, method, url, **kwargs)
    requests.sessions.Session.request = _request
except Exception:
    pass

try:
    import httpx
    _orig_client_init = httpx.Client.__init__
    def _client_init(self, *args, **kwargs):
        kwargs.setdefault("verify", False)
        return _orig_client_init(self, *args, **kwargs)
    httpx.Client.__init__ = _client_init

    _orig_async_client_init = httpx.AsyncClient.__init__
    def _async_client_init(self, *args, **kwargs):
        kwargs.setdefault("verify", False)
        return _orig_async_client_init(self, *args, **kwargs)
    httpx.AsyncClient.__init__ = _async_client_init
except Exception:
    pass
""".strip()
)
PY

RUN if [ -d /app/services/docling_service/assets/huggingface ]; then \
      cp -r /app/services/docling_service/assets/huggingface/. /opt/huggingface/; \
    fi

RUN python - <<'PY'
from services.docling_service.ingestion.docx.extractor import _get_docx_converter

# Warm up the cached DOCX converter so later runtime does not pay that setup cost again.
_get_docx_converter()
PY

RUN python - <<'PY'
import easyocr

# Pre-download EasyOCR model files during image build so the first real OCR request
# does not spend time fetching them at runtime.
for languages in (["fr", "en"], ["ar", "en"]):
    easyocr.Reader(
        lang_list=languages,
        gpu=False,
        download_enabled=True,
        model_storage_directory="/opt/easyocr",
    )
PY

EXPOSE 8000

CMD ["uvicorn", "services.docling_service.app:app", "--host", "0.0.0.0", "--port", "8000"]
