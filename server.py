from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import urllib.request
import subprocess
import sys
import io
import os
import json


class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path in ("/", "/index.html"):
            self._serve_file("index.html", "text/html; charset=utf-8")
        elif parsed.path == "/run":
            params = parse_qs(parsed.query)
            wallet = params.get("wallet", [""])[0].strip()
            self._stream_run(wallet)
        elif parsed.path == "/tokens":
            self._get_tokens()
        elif parsed.path == "/more_transactions":
            self._get_more_transactions()
        elif parsed.path == "/token_detail":
            params = parse_qs(parsed.query)
            token = params.get("token", [""])[0].strip()
            self._get_token_detail(token)
        elif parsed.path == "/prices":
            self._get_prices()
        elif parsed.path == "/summary":
            self._get_summary()
        elif parsed.path == "/trend":
            self._get_trend()
        else:
            self.send_error(404)

    def _serve_file(self, filename, content_type):
        base = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base, filename)
        try:
            with open(path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self.send_error(404)

    def _stream_run(self, wallet):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        if not wallet:
            self._send_event("Error: no wallet address provided")
            self._send_event("[DONE]")
            return

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        base = os.path.dirname(os.path.abspath(__file__))
        proc = subprocess.Popen(
            [sys.executable, "-u", os.path.join(base, "runner.py"), wallet],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            cwd=base,
        )

        try:
            for line in proc.stdout:
                self._send_event(line.rstrip())
            proc.wait()
        except (BrokenPipeError, OSError):
            proc.terminate()
        finally:
            self._send_event("[DONE]")

    def _get_tokens(self):
        try:
            from db import get_connection
            import psycopg2.extras

            conn = get_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT token, COUNT(*) AS count, SUM(amount) AS total_amount
                    FROM (
                        SELECT token_in  AS token, amount_in  AS amount
                        FROM transactions
                        WHERE type = 'SWAP' AND token_in  IS NOT NULL AND token_in  <> ''
                        UNION ALL
                        SELECT token_out AS token, amount_out AS amount
                        FROM transactions
                        WHERE type = 'SWAP' AND token_out IS NOT NULL AND token_out <> ''
                    ) t
                    GROUP BY token
                    ORDER BY count DESC
                    LIMIT 20
                """)
                rows = [
                    {
                        "token":        r["token"],
                        "count":        int(r["count"]),
                        "total_amount": float(r["total_amount"] or 0),
                    }
                    for r in cur.fetchall()
                ]
            conn.close()

            data = json.dumps(rows).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        except Exception as e:
            err = json.dumps({"error": str(e)}).encode()
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err)))
            self.end_headers()
            self.wfile.write(err)

    def _get_token_detail(self, token):
        try:
            from db import get_connection
            import psycopg2.extras

            conn = get_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        SUM(CASE WHEN direction = 'in'  THEN 1 ELSE 0 END)      AS count_in,
                        SUM(CASE WHEN direction = 'out' THEN 1 ELSE 0 END)      AS count_out,
                        SUM(CASE WHEN direction = 'in'  THEN amount ELSE 0 END) AS total_in,
                        SUM(CASE WHEN direction = 'out' THEN amount ELSE 0 END) AS total_out,
                        TO_TIMESTAMP(MIN(block_time))::TEXT                     AS first_seen,
                        TO_TIMESTAMP(MAX(block_time))::TEXT                     AS last_seen
                    FROM (
                        SELECT token_in  AS token, amount_in  AS amount, 'in'  AS direction, block_time
                        FROM transactions WHERE token_in  = %s
                        UNION ALL
                        SELECT token_out AS token, amount_out AS amount, 'out' AS direction, block_time
                        FROM transactions WHERE token_out = %s
                    ) t
                """, (token, token))
                stats = dict(cur.fetchone())

                cur.execute("""
                    SELECT type, COUNT(*) AS count
                    FROM transactions
                    WHERE token_in = %s OR token_out = %s
                    GROUP BY type ORDER BY count DESC
                """, (token, token))
                types = [{"type": r["type"], "count": int(r["count"])} for r in cur.fetchall()]

            conn.close()

            result = {
                "token":      token,
                "count_in":   int(stats["count_in"]   or 0),
                "count_out":  int(stats["count_out"]  or 0),
                "total_in":   float(stats["total_in"]  or 0),
                "total_out":  float(stats["total_out"] or 0),
                "first_seen": str(stats["first_seen"]  or ""),
                "last_seen":  str(stats["last_seen"]   or ""),
                "types":      types,
            }

            data = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        except Exception as e:
            err = json.dumps({"error": str(e)}).encode()
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err)))
            self.end_headers()
            self.wfile.write(err)

    def _get_more_transactions(self):
        try:
            from db import get_connection
            import queries

            conn = get_connection()
            old_stdout = sys.stdout
            sys.stdout = buf = io.StringIO()
            queries.remaining_transactions(conn)
            sys.stdout = old_stdout
            conn.close()

            text = buf.getvalue().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(text)))
            self.end_headers()
            self.wfile.write(text)

        except Exception as e:
            sys.stdout = old_stdout if 'old_stdout' in dir() else sys.stdout
            err = str(e).encode()
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(err)))
            self.end_headers()
            self.wfile.write(err)

    def _get_summary(self):
        try:
            from db import get_connection
            import psycopg2.extras

            conn = get_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        COUNT(*)                                                      AS total_txns,
                        TO_TIMESTAMP(MIN(block_time))::TEXT                           AS first_txn,
                        TO_TIMESTAMP(MAX(block_time))::TEXT                           AS last_txn,
                        COALESCE(SUM(CASE WHEN token_in  IN ('USDC','USDT','USDH')
                                         THEN amount_in  ELSE 0 END), 0)              AS usd_in,
                        COALESCE(SUM(CASE WHEN token_out IN ('USDC','USDT','USDH')
                                         THEN amount_out ELSE 0 END), 0)              AS usd_out
                    FROM transactions
                """)
                row = dict(cur.fetchone())

                cur.execute("""
                    SELECT COUNT(DISTINCT token) AS unique_tokens
                    FROM (
                        SELECT token_in  AS token FROM transactions
                        WHERE token_in  IS NOT NULL AND token_in  <> ''
                        UNION
                        SELECT token_out AS token FROM transactions
                        WHERE token_out IS NOT NULL AND token_out <> ''
                    ) t
                """)
                row["unique_tokens"] = cur.fetchone()["unique_tokens"]
            conn.close()

            result = {
                "total_txns":    int(row["total_txns"]),
                "first_txn":     str(row["first_txn"] or ""),
                "last_txn":      str(row["last_txn"]  or ""),
                "usd_in":        float(row["usd_in"]),
                "usd_out":       float(row["usd_out"]),
                "unique_tokens": int(row["unique_tokens"]),
            }
            data = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            err = json.dumps({"error": str(e)}).encode()
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err)))
            self.end_headers()
            self.wfile.write(err)

    def _get_trend(self):
        try:
            from db import get_connection
            import psycopg2.extras

            conn = get_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        TO_CHAR(TO_TIMESTAMP(block_time), 'YYYY-MM') AS month,
                        COUNT(*)                                       AS txn_count,
                        COALESCE(SUM(CASE WHEN token_in  IN ('USDC','USDT','USDH')
                                         THEN amount_in  ELSE 0 END), 0) AS usd_in,
                        COALESCE(SUM(CASE WHEN token_out IN ('USDC','USDT','USDH')
                                         THEN amount_out ELSE 0 END), 0) AS usd_out
                    FROM transactions
                    GROUP BY month
                    ORDER BY month
                """)
                rows = [
                    {
                        "month":     r["month"],
                        "txn_count": int(r["txn_count"]),
                        "usd_in":    float(r["usd_in"]),
                        "usd_out":   float(r["usd_out"]),
                    }
                    for r in cur.fetchall()
                ]
            conn.close()

            data = json.dumps(rows).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            err = json.dumps({"error": str(e)}).encode()
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err)))
            self.end_headers()
            self.wfile.write(err)

    def _get_prices(self):
        # Mint addresses for tokens we recognise, keyed by symbol stored in DB
        MINT_TO_SYMBOL = {
            "So11111111111111111111111111111111111111112": "wSOL",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
            "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": "USDT",
            "USDH1Hdt8P7qTQKDSpeZDnDRKqTucBM5ciqMP2kYtAf": "USDH",
            "DezXAZ8z7PnrnRJjz3Fh4Cz9WcbQTUk2e37hTd5C59w": "BONK",
            "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN": "JUP",
            "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn": "JitoSOL",
            "mSoLzYCxNqgBJwTfMxKWR7fmDjnZ7HepfsSwnYwbsR": "mSOL",
            "bSo13r4TkiE4G6HUPZepS9z6E6T8Jq3EqW3eJ5W2RCP": "bSOL",
            "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R": "RAY",
            "orcaEKTdK7LKz57vaAYfXqXbUQmNEw4RkY7qR9VYkq":  "ORCA",
            "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm": "WIF",
            "HhJpBhZc3L4QxrzBFW91tYYQJgWPs2F7GQZpkz7g5Xtg": "MYRO",
            "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgTL": "SAMO",
        }
        try:
            mints = ",".join(MINT_TO_SYMBOL.keys())
            url = f"https://api.jup.ag/price/v2?ids={mints}"
            req = urllib.request.Request(url, headers={"User-Agent": "SolanaTracker/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                raw = json.loads(resp.read())

            prices = {}
            for mint, info in raw.get("data", {}).items():
                symbol = MINT_TO_SYMBOL.get(mint)
                if symbol and info and info.get("price"):
                    prices[symbol] = float(info["price"])

            data = json.dumps(prices).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            # Return empty object on failure — frontend handles gracefully
            empty = json.dumps({}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(empty)))
            self.end_headers()
            self.wfile.write(empty)

    def _send_event(self, text):
        try:
            self.wfile.write(f"data: {text}\n\n".encode())
            self.wfile.flush()
        except (BrokenPipeError, OSError):
            pass

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"Listening on port {port}")
    server.serve_forever()
