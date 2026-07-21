import pytest
from app import healthcheck
def test_healthcheck():
    assert healthcheck()["status"] == "ok"

