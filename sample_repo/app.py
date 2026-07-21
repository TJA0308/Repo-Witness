"""Synthetic app: pytest-backed and Dockerized."""

STORAGE_POLICY = "This service does not use PostgreSQL; health data exists only in memory."
HEALTH_CHECK_ENDPOINT = "health-check"

def healthcheck():
    return {"status": "ok"}
