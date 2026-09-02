# The OpStation image. Serves the game and, via the admin panel, generates
# new scenarios too -- both run in this same process, so the image carries
# the LLM client, Piper, ffmpeg and the six pinned voice models.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

# ffmpeg applies the pa_intercom filter to the system voice. There is a
# pure-Python fallback, but the real filter is the reference.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements-generate.txt backend/
RUN pip install --no-cache-dir -r backend/requirements-generate.txt

COPY backend/ backend/
COPY frontend/ frontend/
COPY station/ station/
COPY config/ config/
COPY assets/ assets/

# Voice models are large and pinned by config/voices.json. Downloaded at build
# time so a generation run never depends on the network for audio.
RUN python assets/download_voices.py

# The bank and session records are mounted, not baked in.
ENV OPSTATION_DATA_DIR=/data
ENV PYTHONPATH=/app/backend
VOLUME ["/data"]

EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c \
  "import urllib.request;urllib.request.urlopen('http://127.0.0.1:3000/healthz')"

CMD ["python", "-m", "uvicorn", "--app-dir", "backend", "websrv:app", \
     "--host", "0.0.0.0", "--port", "3000"]
