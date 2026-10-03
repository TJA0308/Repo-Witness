def next_job(queue):
    return queue.pop(0) if queue else None
