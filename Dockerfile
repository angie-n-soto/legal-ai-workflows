FROM python:3.12-slim

# LibreOffice converts the reduction letters to PDF; Carlito is a metric-compatible stand-in for Calibri.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libreoffice-writer-nogui fonts-crosextra-carlito \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PYTHONPATH=/app/src PYTHONUNBUFFERED=1
EXPOSE 10000
CMD ["sh", "-c", "uvicorn legal_workflows.web:app --host 0.0.0.0 --port ${PORT:-10000}"]
