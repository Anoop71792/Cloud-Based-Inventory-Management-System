FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WEB_CONCURRENCY=2

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Amazon RDS CA bundle (public certificates, not a secret). Used by the app to
# verify the RDS server certificate and hostname.
ARG RDS_CA_BUNDLE_URL=https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem
RUN mkdir -p /app/certs \
 && python -c "import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], '/app/certs/rds-global-bundle.pem')" "$RDS_CA_BUNDLE_URL" \
 && python -c "import sys; sys.exit(0 if open('/app/certs/rds-global-bundle.pem').read().count('BEGIN CERTIFICATE') > 0 else 1)"

COPY . .

# Run as an unprivileged user. No database files or volumes: all data lives in RDS MySQL.
RUN useradd --system --no-create-home --shell /usr/sbin/nologin appuser \
 && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/healthz', timeout=4)" || exit 1

# entrypoint.py validates configuration, waits for MySQL, creates the tables,
# and then execs the command below. Database settings come from environment
# variables at runtime (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, SECRET_KEY).
ENTRYPOINT ["python", "entrypoint.py"]
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--access-logfile", "-", "app:app"]
