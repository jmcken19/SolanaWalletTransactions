from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
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
                        WHERE token_in  IS NOT NULL AND token_in  <> ''
                        UNION ALL
                        SELECT token_out AS token, amount_out AS amount
                        FROM transactions
                        WHERE token_out IS NOT NULL AND token_out <> ''
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
