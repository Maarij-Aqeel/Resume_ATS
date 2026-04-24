FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System dependencies:
#  - libreoffice: .doc -> .docx conversion
#  - tesseract-ocr: OCR fallback
#  - poppler-utils: pdfplumber/PyMuPDF helpers
#  - libgl1 / libglib2.0-0: Pillow + opencv-style deps for sentence-transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice \
        tesseract-ocr \
        poppler-utils \
        libgl1 \
        libglib2.0-0 \
        curl \
        ca-certificates \
        gcc \
        libc6-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

RUN useradd --create-home --shell /bin/bash ats \
    && mkdir -p /app/uploads \
    && chown -R ats:ats /app
USER ats

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
