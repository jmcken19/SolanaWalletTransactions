Solana Wallet Transaction Tracker

A Python + SQL project that fetches transaction history for a Solana wallet using the Helius API, stores it in a local SQLite database, and displays summary reports in the terminal.

[Terminal Output]
<img width="699" height="325" alt="sql" src="https://github.com/user-attachments/assets/05f9b033-57c7-44f2-934f-f5343fa46503" />

Tech Stack

Python 3.11+
SQLite3
Helius API (Solana enhanced transactions)
requests, python-dotenv
Features

Paginates through up to 500 transactions (5 pages × 100)
Parses token swaps — resolves mint addresses to readable names (wSOL, USDC, etc.)
Converts lamport fees to SOL
Displays: transactions by type, recent transactions, failed transactions
Setup

Clone the repo
pip install requests python-dotenv
Create a .env file: HELIUS_API_KEY=your_key_here
Run python main.py
