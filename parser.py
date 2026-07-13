#this will remove the long addresses from the terminal for better viewing
KNOWN_TOKENS = {
    # Native / wrapped SOL
    "So11111111111111111111111111111111111111112": "wSOL",

    # Stablecoins
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": "USDT",
    "USDH1Hdt8P7qTQKDSpeZDnDRKqTucBM5ciqMP2kYtAf": "USDH",

    # Popular Solana ecosystem tokens
    "DezXAZ8z7PnrnRJjz3Fh4Cz9WcbQTUk2e37hTd5C59w": "BONK",
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN": "JUP",
    "JitoSo111111111111111111111111111111111111111": "JitoSOL",
    "mSoLzYCxNqgBJwTfMxKWR7fmDjnZ7HepfsSwnYwbsR": "mSOL",
    "bSo13r4TkiE4G6HUPZepS9z6E6T8Jq3EqW3eJ5W2RCP": "bSOL",

    # DeFi / protocol tokens
    "RAYdiumWg6jQbkqQ87Qp8U7Pvp5PrF5yZV8u47pzjV": "RAY",
    "orcaEKTdK7LKz57vaAYfXqXbUQmNEw4RkY7qR9VYkq": "ORCA",
    "MNDEjY1MmuJz2cg3N7E8zG8Dr2Lk1n6Kgxk6D6LmS4": "MNDE",
    "SAMoKQ46D8UY4egkGx3VnPfSwpD3bEoGz3YYNo7S1K": "SAMO",

    # Meme / community tokens
    "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgTL": "SAMO",
    "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm": "WIF",
    "HhJpBhZc3L4QxrzBFW91tYYQJgWPs2F7GQZpkz7g5Xtg": "MYRO",
}

def _resolve_mint(mint: str) -> str:
    return KNOWN_TOKENS.get(mint, mint)

# this function takes the raw data and parses it into a list of dictionaries 
def parse_transactions(raw: list[dict]) -> list[dict]:
    results = [parse_one(txn) for txn in raw]
    return [r for r in results if r is not None]
#List comprehension allows to build a list in one line instead of writing a loop

# this function takes a single transaction and parses it into the dictionary
def parse_one(txn: dict) -> dict | None:
    try:
        transfers = txn.get("tokenTransfers", [])
        return {
            "signature":  txn["signature"],
            "block_time": txn["timestamp"],
            "slot":       txn["slot"],
            "fee":        txn["fee"],

            "status": "success" if txn.get("transactionError") is None else "failed",

            "source":      txn.get("source", ""),
            "type":        txn.get("type", ""),
            "description": txn.get("description", ""),


            #
            "token_in":  _resolve_mint(transfers[0]["mint"]) if len(transfers) > 0 else "",
            "amount_in": transfers[0]["tokenAmount"]          if len(transfers) > 0 else 0.0,
            "token_out": _resolve_mint(transfers[1]["mint"]) if len(transfers) > 1 else "",
            "amount_out": transfers[1]["tokenAmount"]         if len(transfers) > 1 else 0.0,
                    }
    except KeyError:
        return None
