import pytest

from worker import next_job


@pytest.mark.parametrize("queue, expected", [([], None), (["task"], "task")])
def test_next_job(queue, expected):
    assert next_job(queue) == expected
