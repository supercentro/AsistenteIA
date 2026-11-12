"""Database administration commands (change `database-least-privilege`, group 4).

`bootstrap` creates the roles and closes access, `adopt` re-owns an existing database,
`grants` renders the privilege matrix as SQL, `migrate` runs Alembic then the grants and `verify`
compares the live catalog with the matrix. Nothing here runs at import time or at API startup.
"""
