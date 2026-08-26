# The playing server. Deliberately thin: no model weights, no LLM client, no
# ffmpeg. A scenario arrives pre-rendered in the bank and is played
# deterministically, so nothing here needs to generate anything.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY frontend/ frontend/
COPY station/ station/
COPY config/ config/
COPY assets/portraits/ assets/portraits/

# The bank and session records are mounted, not baked in.
ENV OPSTATION_DATA_DIR=/data
VOLUME ["/data"]

EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c \
  "import urllib.request;urllib.request.urlopen('http://127.0.0.1:3000/healthz')"

CMD ["python", "-m", "uvicorn", "--app-dir", "backend", "opstation.app:app", \
     "--host", "0.0.0.0", "--port", "3000"]
