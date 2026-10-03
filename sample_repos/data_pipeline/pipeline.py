# This pipeline does not use Redis for persistent storage.
# Results are kept in memory; this is a synthetic source-review example.


def normalize_rows(rows):
    return [{key.strip(): value for key, value in row.items()} for row in rows]
