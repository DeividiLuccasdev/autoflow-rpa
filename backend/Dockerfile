# Imagem de produção: somente dependências de execução, sem testes nem ferramentas de desenvolvimento.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install "pip>=26.2,<27" && pip install -r requirements.txt

RUN useradd --create-home --uid 10001 autoflow
COPY --chown=autoflow:autoflow . .
USER autoflow

EXPOSE 8000

# Sem curl na imagem slim: o próprio Python consulta o endpoint de liveness.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
