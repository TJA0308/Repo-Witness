import unittest

from worker import next_job


class QueueTests(unittest.TestCase):
    def test_next_job(self):
        self.assertIsNone(next_job([]))
        self.assertEqual(next_job(["task"]), "task")
