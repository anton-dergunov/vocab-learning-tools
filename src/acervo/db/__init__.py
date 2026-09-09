"""SQLAlchemy tables, the engine, and the Alembic bootstrap.

Nothing outside `acervo.repository` may import this package: `repository/` is the only code that
touches the database, which is the server-side twin of the rule the interface already lives by.
"""
