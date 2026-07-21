"""Synthetic app: pytest-backed, Dockerized, but not PostgreSQL-backed."""
def healthcheck():
    return {"status": "ok"}

