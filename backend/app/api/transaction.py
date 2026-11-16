"""Explicit commit for the endpoints that promise persistence (TD-039, DD-15).

`get_db` commits once more after the handler returns, which in this stack happens after the success
response was sent: a commit that PostgreSQL refuses there would follow a 2xx. A handler that stores
something therefore calls `commit_or_rollback` before it builds the response; when the database
refuses, the session is rolled back and the error propagates to the standard 500 body.
"""

from sqlalchemy.orm import Session


def commit_or_rollback(db: Session) -> None:
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
