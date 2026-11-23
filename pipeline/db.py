"""Database connection helper (reads DATABASE_URL or standard PG* variables)."""
import os

import psycopg


def dsn() -> str:
    if url := os.getenv("DATABASE_URL"):
        return url
    return (
        f"host={os.getenv('PGHOST', 'localhost')} "
        f"port={os.getenv('PGPORT', '5432')} "
        f"dbname={os.getenv('PGDATABASE', 'hr_migration')} "
        f"user={os.getenv('PGUSER', 'postgres')} "
        f"password={os.getenv('PGPASSWORD', 'postgres')}"
    )


def connect() -> psycopg.Connection:
    return psycopg.connect(dsn(), autocommit=True)
