import psycopg2.extras


def _cursor(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def summary_by_type(conn) -> None:
    with _cursor(conn) as cur:
        cur.execute("""
            SELECT type,
                   COUNT(*) AS count,
                   ROUND(SUM(fee) / 1000000000.0, 6) AS total_fees_sol
            FROM transactions
            GROUP BY type
            ORDER BY count DESC
        """)
        rows = cur.fetchall()
    pretty_table(rows, title="Transactions by type")


def recent_transactions(conn, n: int = 10) -> None:
    with _cursor(conn) as cur:
        cur.execute("""
            SELECT SUBSTRING(signature, 1, 8) || '...' AS signature,
                   TO_TIMESTAMP(block_time)::TEXT        AS time,
                   type, token_in, amount_in,
                   token_out, amount_out,
                   ROUND(fee / 1000000000.0, 6)         AS fee_sol
            FROM transactions
            ORDER BY block_time DESC
            LIMIT %s
        """, (n,))
        rows = cur.fetchall()
    pretty_table(rows, title="Recent Transactions")


def remaining_transactions(conn) -> None:
    with _cursor(conn) as cur:
        cur.execute("""
            SELECT SUBSTRING(signature, 1, 8) || '...' AS signature,
                   TO_TIMESTAMP(block_time)::TEXT        AS time,
                   type, token_in, amount_in,
                   token_out, amount_out,
                   ROUND(fee / 1000000000.0, 6)         AS fee_sol
            FROM transactions
            ORDER BY block_time DESC
            LIMIT 490 OFFSET 10
        """)
        rows = cur.fetchall()
    pretty_table(rows, title="")


def failed_transactions(conn) -> None:
    with _cursor(conn) as cur:
        cur.execute("""
            SELECT signature,
                   TO_TIMESTAMP(block_time)::TEXT AS time,
                   description
            FROM transactions
            WHERE status = 'failed'
        """)
        rows = cur.fetchall()
    pretty_table(rows, title="Failed Transactions")


def pretty_table(rows, title: str = "") -> None:
    if not rows:
        return

    headers = list(rows[0].keys())
    widths = [
        max(len(headers[i]), max(len(str(row[headers[i]])) for row in rows))
        for i in range(len(headers))
    ]

    print(f"\n{title}")
    print("  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    print("  ".join("-" * w for w in widths))

    def fmt(val):
        if val is None:
            return ""
        try:
            f = float(val)
            return str(int(f)) if f == int(f) else f"{f:.6f}"
        except (TypeError, ValueError):
            return str(val)

    for row in rows:
        print("  ".join(fmt(row[h]).ljust(widths[i]) for i, h in enumerate(headers)))
