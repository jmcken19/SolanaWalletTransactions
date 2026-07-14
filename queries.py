import psycopg2.extras


def _cursor(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def summary_by_type(conn) -> None:
    with _cursor(conn) as cur:
        cur.execute("""
            SELECT
                type                                        AS "Type",
                COUNT(*)                                    AS "Transactions",
                ROUND(SUM(fee) / 1000000000.0, 6)          AS "Fees (SOL)"
            FROM transactions
            WHERE type IN ('TRANSFER', 'SWAP')
            GROUP BY type
            ORDER BY "Transactions" DESC
        """)
        rows = cur.fetchall()
    pretty_table(rows, title="Activity Breakdown")


def recent_transactions(conn, n: int = 10) -> None:
    with _cursor(conn) as cur:
        cur.execute("""
            SELECT
                SUBSTRING(signature, 1, 8) || '...'             AS "ID",
                TO_CHAR(TO_TIMESTAMP(block_time), 'Mon DD HH24:MI') AS "Date",
                type                                             AS "Type",
                COALESCE(token_in,  '-')                         AS "Received",
                COALESCE(ROUND(amount_in::numeric,  4)::text, '-') AS "Amt In",
                COALESCE(token_out, '-')                         AS "Sent",
                COALESCE(ROUND(amount_out::numeric, 4)::text, '-') AS "Amt Out"
            FROM transactions
            WHERE (token_in  IS NOT NULL AND token_in  <> '')
               OR (token_out IS NOT NULL AND token_out <> '')
            ORDER BY block_time DESC
            LIMIT %s
        """, (n,))
        rows = cur.fetchall()
    pretty_table(rows, title="Recent Transactions")


def remaining_transactions(conn) -> None:
    with _cursor(conn) as cur:
        cur.execute("""
            SELECT
                SUBSTRING(signature, 1, 8) || '...'             AS "ID",
                TO_CHAR(TO_TIMESTAMP(block_time), 'Mon DD HH24:MI') AS "Date",
                type                                             AS "Type",
                COALESCE(token_in,  '-')                         AS "Received",
                COALESCE(ROUND(amount_in::numeric,  4)::text, '-') AS "Amt In",
                COALESCE(token_out, '-')                         AS "Sent",
                COALESCE(ROUND(amount_out::numeric, 4)::text, '-') AS "Amt Out"
            FROM transactions
            WHERE (token_in  IS NOT NULL AND token_in  <> '')
               OR (token_out IS NOT NULL AND token_out <> '')
            ORDER BY block_time DESC
            LIMIT 490 OFFSET 10
        """)
        rows = cur.fetchall()
    pretty_table(rows, title="")


def failed_transactions(conn) -> None:
    with _cursor(conn) as cur:
        cur.execute("""
            SELECT
                SUBSTRING(signature, 1, 8) || '...' AS "ID",
                TO_CHAR(TO_TIMESTAMP(block_time), 'Mon DD HH24:MI') AS "Date",
                description                          AS "Description"
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
        max(len(headers[i]), max(len(str(row[headers[i]] or '')) for row in rows))
        for i in range(len(headers))
    ]

    if title:
        print(f"\n{title}")
    print("  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    print("  ".join("-" * w for w in widths))

    for row in rows:
        print("  ".join(str(row[h] or '-').ljust(widths[i]) for i, h in enumerate(headers)))
