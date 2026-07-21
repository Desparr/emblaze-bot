# =============================================================================
# Emblaze Slack Bot -- Dockerfile
# Built to the Emtech app-author contract (Emtech-LLC/starthere).
#   - Base image from public.ecr.aws/* (never Docker Hub -- avoids the CI
#     builder's anonymous pull-rate 429).
#   - Binds 0.0.0.0:${PORT}, PORT=8080.
#   - Health at /healthz and /health, open + data-free, no auth.
#   - All config/secrets read from environment variables (see .env.example).
# Local Docker is for testing only -- the real image is built on Linux CI once
# Russell has wired the repo. See starthere/building/containerizing.md.
# =============================================================================

FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app

# Dependencies first for layer caching -- editing source won't reinstall pip.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application source.
COPY app.py ./
COPY slack_bot/ slack_bot/

ENV PORT=8080
EXPOSE 8080

# gunicorn, not Flask's dev server. app:app matches app.py's module-level `app`.
CMD ["sh", "-c", "exec gunicorn -b 0.0.0.0:${PORT} --workers 2 --threads 4 --timeout 60 app:app"]
