FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Mirror alternativo oficial de Debian (evita caída del nodo Fastly 151.101.230.132 de deb.debian.org en Perú)
RUN sed -i 's|deb.debian.org|mirrors.ocf.berkeley.edu|g' /etc/apt/sources.list.d/debian.sources \
    && echo 'Acquire::Retries "5";' > /etc/apt/apt.conf.d/80-retries

# Tesseract OCR con idiomas español e inglés (usado por Smart Triage)
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Aplica las migraciones pendientes y levanta la API (Render inyecta PORT; en local se usa 8000)
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
