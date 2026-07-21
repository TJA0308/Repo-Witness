"""Synthetic app: pytest-backed and Dockerized."""

# This sample does not use PostgreSQL; health data exists only in memory.
def healthcheck():
    return {"status": "ok"}
