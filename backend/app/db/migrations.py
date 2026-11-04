"""Versioned SQL migration runner with SHA-256 checksums and PostgreSQL advisory lock."""

from __future__ import annotations

import hashlib
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

MIGRATION_ADVISORY_LOCK_KEY = 88022026
DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def _compute_checksum(sql_text: str) -> str:
    # Normalize CRLF -> LF so checksums match identically across Windows and Linux containers
    normalized = sql_text.replace("\r\n", "\n").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def run_migrations(database_url: str, migrations_dir: Path | None = None) -> list[str]:
    """Apply pending SQL migrations in deterministic order.

    Returns the list of newly applied migration filenames.
    Safe to invoke concurrently across processes thanks to `pg_advisory_lock`.
    """
    target_dir = migrations_dir or DEFAULT_MIGRATIONS_DIR
    if not target_dir.exists():
        raise FileNotFoundError(f"Không tìm thấy thư mục migrations: {target_dir}")

    sql_files = sorted(target_dir.glob("*.sql"), key=lambda p: p.name)
    applied_now: list[str] = []

    with psycopg.connect(database_url, row_factory=dict_row, autocommit=False) as conn:
        # Acquire session-level advisory lock across concurrent migration runners
        with conn.transaction():
            conn.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_ADVISORY_LOCK_KEY,))
        try:
            with conn.transaction():
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version VARCHAR(64) PRIMARY KEY,
                        filename VARCHAR(255) NOT NULL,
                        checksum CHAR(64) NOT NULL,
                        applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                rows = conn.execute(
                    "SELECT version, filename, checksum FROM schema_migrations ORDER BY version"
                ).fetchall()
                existing = {str(r["version"]): (str(r["filename"]), str(r["checksum"])) for r in rows}

            for sql_file in sql_files:
                version = sql_file.stem.split("_", 1)[0]
                sql_text = sql_file.read_text(encoding="utf-8")
                checksum = _compute_checksum(sql_text)

                if version in existing:
                    prev_filename, prev_checksum = existing[version]
                    if prev_checksum != checksum:
                        raise RuntimeError(
                            f"Checksum migration '{sql_file.name}' không khớp bản đã áp dụng "
                            f"('{prev_filename}'): expected {prev_checksum}, got {checksum}."
                        )
                    continue

                with conn.transaction():
                    conn.execute("SET LOCAL timezone = 'GMT'")
                    conn.execute(sql_text)
                    conn.execute(
                        """
                        INSERT INTO schema_migrations (version, filename, checksum)
                        VALUES (%s, %s, %s)
                        """,
                        (version, sql_file.name, checksum),
                    )
                applied_now.append(sql_file.name)
        finally:
            try:
                with conn.transaction():
                    conn.execute("SELECT pg_advisory_unlock(%s)", (MIGRATION_ADVISORY_LOCK_KEY,))
            except psycopg.Error:
                pass

    return applied_now
