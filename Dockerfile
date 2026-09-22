# ==============================================================================
# Dockerfile - Plataforma Analítica Financeira Ledger Horizon
# Debian 12 / Python 3.12 Lean Container
# ==============================================================================

FROM python:3.12-slim-bookworm

# Evitar escrita de arquivos .pyc e garantir stdout não bufferizado
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar dependências de sistema mínimas para compilação caso necessário
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements primeiro para aproveitar cache de camadas
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar o restante da aplicação
COPY . .

# Criar usuário sem privilégios de root para segurança
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
