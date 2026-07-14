from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import urllib.request
import subprocess
import sys
import io
import os
import json

MINT_TO_SYMBOL = {
    "So11111111111111111111111111111111111111112":  "wSOL",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": "USDT",
    "USDH1Hdt8P7qTQKDSpeZDnDRKqTucBM5ciqMP2kYtAf":  "USDH",
    "DezXAZ8z7PnrnRJjz3Fh4Cz9WcbQTUk2e37hTd5C59w": "BONK",
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN":  "JUP",
    "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn": "JitoSOL",
    "mSoLzYCxNqgBJwTfMxKWR7fmDjnZ7HepfsSwnYwbsR":   "mSOL",
    "bSo13r4TkiE4G6HUPZepS9z6E6T8Jq3EqW3eJ5W2RCP":  "bSOL",
    "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R": "RAY",
    "orcaEKTdK7LKz57vaAYfXqXbUQmNEw4RkY7qR9VYkq":   "ORCA",
    "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm": "WIF",
    "HhJpBhZc3L4QxrzBFW91tYYQJgWPs2F7GQZpkz7g5Xtg": "MYRO",
    "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgTL":  "SAMO",
}


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
        elif parsed.path == "/holdings":
            params = parse_qs(parsed.query)
            wallet = params.get("wallet", [""])[0].strip()
            self._get_holdings(wallet)
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
        try:
            mints = ",".join(MINT_TO_SYMBOL.keys())
            url = f"https://lite-api.jup.ag/price/v3?ids={mints}"
            req = urllib.request.Request(url, headers={"User-Agent": "SolanaTracker/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                raw = json.loads(resp.read())

            prices = {}
            for mint, info in raw.items():
                symbol = MINT_TO_SYMBOL.get(mint)
                if symbol and info and info.get("usdPrice"):
                    prices[symbol] = float(info["usdPrice"])

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

    def _get_holdings(self, wallet_param=""):
        try:
            from config import API_KEY, WALLET as CONFIG_WALLET
            wallet = wallet_param or CONFIG_WALLET

            SOL_MINT = "So11111111111111111111111111111111111111112"
            RPC_URL  = f"https://mainnet.helius-rpc.com/?api-key={API_KEY}"

            def rpc(method, params):
                body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
                req  = urllib.request.Request(RPC_URL, data=body, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return json.loads(resp.read()).get("result", {})

            # 1. Native SOL balance
            sol_lamports = rpc("getBalance", [wallet]).get("value", 0)
            sol_amount   = float(sol_lamports) / 1e9

            # 2. SPL token accounts — both legacy Token program and Token-2022
            SPL_PROGRAM    = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
            TOKEN22_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"

            all_accounts = []
            for program_id in (SPL_PROGRAM, TOKEN22_PROGRAM):
                result = rpc("getTokenAccountsByOwner", [
                    wallet,
                    {"programId": program_id},
                    {"encoding": "jsonParsed"},
                ])
                all_accounts.extend(result.get("value") or [])

            entries = [{"mint": SOL_MINT, "symbol": "wSOL", "amount": sol_amount}]

            for acct in all_accounts:
                info   = acct["account"]["data"]["parsed"]["info"]
                mint   = info["mint"]
                ui_amt = float(info["tokenAmount"]["uiAmount"] or 0)
                symbol = MINT_TO_SYMBOL.get(mint) or (
                    mint[:6] + "\u2026" + mint[-4:] if len(mint) > 10 else mint
                )
                entries.append({"mint": mint, "symbol": symbol, "amount": ui_amt})

            # 3. Filter: must hold more than 1 token (drops dust/airdrops)
            entries = [e for e in entries if e["amount"] > 1]

            # 3b. Lookup proper names for unknown tokens via Helius DAS getAsset
            for e in entries:
                if e["mint"] in MINT_TO_SYMBOL:
                    continue
                try:
                    asset  = rpc("getAsset", {"id": e["mint"]})
                    symbol = ((asset.get("token_info") or {}).get("symbol") or
                              (asset.get("content", {}).get("metadata") or {}).get("symbol"))
                    if symbol:
                        e["symbol"] = symbol
                except Exception:
                    pass  # keep shortened mint as fallback

            # 4. Fetch prices only for non-zero mints (avoids 414 on large wallets)
            all_mints = [e["mint"] for e in entries]
            price_url = "https://lite-api.jup.ag/price/v3?ids=" + ",".join(all_mints)
            price_req = urllib.request.Request(price_url, headers={"User-Agent": "SolanaTracker/1.0"})
            try:
                with urllib.request.urlopen(price_req, timeout=5) as presp:
                    price_raw = json.loads(presp.read())
                price_map = {
                    mint: float(info["usdPrice"])
                    for mint, info in price_raw.items()
                    if info and info.get("usdPrice")
                }
            except Exception:
                price_map = {}

            # 5. Compute USD values — only keep tokens with a known price >= $0.01
            holdings = []
            for e in entries:
                price     = price_map.get(e["mint"])
                usd_value = e["amount"] * price if price is not None else None

                if usd_value is None:
                    continue
                if usd_value < 0.01:
                    continue

                holdings.append({
                    "mint":            e["mint"],
                    "symbol":          e["symbol"],
                    "amount":          e["amount"],
                    "usd_value":       usd_value,
                    "price_per_token": price,
                })

            # 5. Sort: largest USD value first, no-price tokens last
            holdings.sort(key=lambda h: (h["usd_value"] is None, -(h["usd_value"] or 0)))

            data = json.dumps(holdings).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        except Exception as e:
            import traceback
            traceback.print_exc()   # prints full traceback to server terminal
            err = json.dumps({"error": str(e)}).encode()
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err)))
            self.end_headers()
            self.wfile.write(err)

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
