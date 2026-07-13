import sys
from db      import get_connection, create_schema, insert_transactions
from helius  import fetch_transactions
from parser  import parse_transactions
import queries


def main(wallet: str) -> None:
    conn = get_connection()
    create_schema(conn)

    print(f"Fetching transactions for {wallet[:8]}...")
    raw = fetch_transactions(wallet)
    print(f"  Got {len(raw)} raw records")

    rows = parse_transactions(raw)
    print(f"  Parsed {len(rows)} valid rows")

    for row in rows:
        row['wallet'] = wallet

    inserted = insert_transactions(conn, rows)
    print(f"  Inserted {inserted} new rows into DB\n")

    queries.summary_by_type(conn)
    queries.recent_transactions(conn)
    queries.failed_transactions(conn)

    conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print("Error: no wallet address provided")
        sys.exit(1)
    main(sys.argv[1].strip())
