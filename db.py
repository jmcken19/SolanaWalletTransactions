import psycopg2
import psycopg2.extras
from config import DATABASE_URL


def get_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn


def create_schema(conn) -> None:
    sql = """
        CREATE TABLE IF NOT EXISTS transactions (
            signature   TEXT PRIMARY KEY,
            block_time  INTEGER,
            slot        INTEGER,
            fee         INTEGER,
            status      TEXT,
            source      TEXT,
            type        TEXT,
            description TEXT,
            token_in    TEXT,
            token_out   TEXT,
            amount_out  REAL,
            amount_in   REAL,
            wallet      TEXT
        )
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        # Add wallet column if upgrading an existing table
        cur.execute("""
            ALTER TABLE transactions ADD COLUMN IF NOT EXISTS wallet TEXT
        """)
    conn.commit()


def insert_transactions(conn, rows: list[dict]) -> int:
    if not rows:
        return 0

    sql = """
        INSERT INTO transactions
            (signature, block_time, slot, fee, status, source, type,
             description, token_in, token_out, amount_out, amount_in, wallet)
        VALUES
            (%(signature)s, %(block_time)s, %(slot)s, %(fee)s, %(status)s,
             %(source)s, %(type)s, %(description)s, %(token_in)s,
             %(token_out)s, %(amount_out)s, %(amount_in)s, %(wallet)s)
        ON CONFLICT (signature) DO NOTHING
    """
    with conn.cursor() as cur:
        psycopg2.extras.execute_batch(cur, sql, rows)
        inserted = cur.rowcount
    conn.commit()
    return inserted
