"""Filmmaker dashboard data pipeline (funds and events).

Separate from the Gmail assistant in `app/`: own Postgres database, own Docker Compose file,
run as one-shot commands (`python -m pipeline run`). See pipeline/README.md.
"""

__version__ = "0.1.0"
