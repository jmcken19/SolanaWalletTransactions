import sys
from db      import get_connection, create_schema, insert_transactions
from helius  import fetch_transactions
from parser  import parse_transactions
import queries


def main(wallet: str) -> None:
    conn = get_connection()
    create_schema(conn)

    # Wipe previous wallet's data so stats only reflect the current wallet
    with conn.cursor() as cur:
        cur.execute("DELETE FROM transactions")
    conn.commit()

    print(f"Analyzing wallet {wallet[:8]}...")
    raw = fetch_transactions(wallet)
    print(f"  Fetched {len(raw)} transactions from chain")

    rows = parse_transactions(raw)
    print(f"  Processed {len(rows)} valid entries")

    inserted = insert_transactions(conn, rows)
    print(f"  Saved {inserted} new records\n")

    queries.summary_by_type(conn)
    queries.recent_transactions(conn)
    queries.failed_transactions(conn)

    conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print("Error: no wallet address provided")
        sys.exit(1)
    main(sys.argv[1].strip())
