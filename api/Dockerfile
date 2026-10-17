# Built from the REPO ROOT (fly.toml sets this up) so the image can include fixtures/ and simulator/.
FROM python:3.12-slim

WORKDIR /app
COPY api/requirements.txt api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt

COPY api/ api/
COPY simulator/ simulator/
COPY fixtures/ fixtures/

ENV PYTHONUNBUFFERED=1 FIXTURES_DIR=/app/fixtures
EXPOSE 8080
# The "app" process; the "worker" process (simulator) is defined in fly.toml.
CMD ["sh", "-c", "cd api && uvicorn app.main:app --host 0.0.0.0 --port 8080"]
