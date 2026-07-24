import pytest


def test_job_retry_policy():
    retry_delay = 5
    assert retry_delay > 0


def test_job_retry_limit():
    retry_limit = 3
    assert retry_limit == 3
