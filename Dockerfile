FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ROTINA_PROXY=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn==23.0.0

COPY . .

# Usuário sem privilégios, dono só da pasta de dados (banco e log da IA)
RUN useradd --uid 1000 --no-create-home rotina \
    && mkdir -p dados && chown rotina:rotina dados
USER rotina

VOLUME ["/app/dados"]
EXPOSE 5001

HEALTHCHECK --interval=60s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5001/ajustes')"

# 1 processo: SQLite e o timer único não precisam de mais que isso
CMD ["gunicorn", "--workers", "1", "--threads", "4", "--bind", "0.0.0.0:5001", "app:app"]
