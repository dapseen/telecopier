Here is a **Product Requirements Document (PRD)** tailored for Cursor AI or any dev agency to understand and build your **Telegram-to-MT5 Signal Automation SaaS**. It focuses on building a personal automation system that can later be offered as a commercial product.

---

## 📄 PRD: **Telegram to MT5 Trade Automation System (Codename: GoldMirror)**

**Author**: Adedapo Ajuwon
**Date**: 2025-05-17
**Stage**: V1 — Personal use with SaaS-readiness
**Target User**: Active traders using Telegram signals, especially prop firm traders

---

### 1. 📌 Problem Statement

Traders following high-performing Telegram signal providers often:

* Miss signals due to timezones or being offline
* Enter trades emotionally or inconsistently
* Violate prop firm rules due to poor risk management

The goal is to **automatically extract signals from a specific Telegram group** and **execute them on an MT5 trading account** with **safe risk rules, breakeven logic, and partial take-profit handling**.

---

### 2. 🎯 Goals & Objectives

| Goal                  | Description                                                        |
| --------------------- | ------------------------------------------------------------------ |
| Automate trading      | Parse structured trade signals and auto-execute them on MT5        |
| Smart risk handling   | Risk 0.25% per trade with lot size automation                      |
| Protect prop accounts | Implement breakeven logic, no trade during news, daily loss limits |
| Built-in analytics    | Track trades, PnL, missed trades, breakeven hit rate               |
| Ready for SaaS        | Modular design for multi-user support and potential monetization   |

---

### 3. 🧠 Core Features

#### 🔁 A. Telegram Signal Listener

* Connects to a specified Telegram channel (read-only)
* Detects new messages and edits
* Extracts:

  * Trade direction (Buy/Sell)
  * Symbol (e.g., XAUUSD)
  * Entry
  * SL
  * TP1, TP2, TP3, TP4

#### ⚙️ B. Signal Parser & Validator

* Assigns a **confidence score** (filters noise, e.g., jokes, swing calls)
* Ignores non-trade messages
* Stores signals in a local or cloud DB with status (`Pending`, `Executed`, `Expired`)

#### 💹 C. MT5 Trader Engine (via MetaTrader5 Python API)

* Logs into MT5 terminal
* Checks if market conditions match signal (price reach)
* Opens trade with:

  * Split TP structure (e.g., 0.05 lots for each TP if total = 0.2)
  * Move SL to breakeven after TP1 is hit
* Enforces:

  * Max risk = 0.25% of account per signal
  * No more than 2 open trades
  * Pause after loss (1hr cooldown)

#### 📈 D. Trade Analytics Module (local dashboard)

* Dashboard UI or Telegram Bot summary:

  * Daily PnL
  * Trades taken vs missed
  * BE hit %, SL %
* Export option: CSV or JSON

#### 🛡️ E. Risk Protection Logic

* Don’t trade during NFP/FOMC (news filter)
* Max daily loss cutoff (e.g., \$200/day)
* Don’t re-enter same signal if stopped out
* Auto-close all if 2 SLs in a row

---

### 4. 🔧 Architecture

| Layer       | Description                                             |
| ----------- | ------------------------------------------------------- |
| Input       | Telegram Bot/Client API                                 |
| Processing  | Python-based signal parser & logic executor             |
| Execution   | MetaTrader5 Python API                                  |
| Storage     | SQLite or JSON logs for MVP                             |
| Optional UI | Streamlit, FastAPI dashboard, or Telegram bot interface |

---

### 5. 🔌 Tech Stack

| Component        | Tool                                |
| ---------------- | ----------------------------------- |
| Signal Ingestion | `telethon` or `python-telegram-bot` |
| Parser           | Regex + NLP fallback                |
| Trading API      | `MetaTrader5` Python package        |
| Risk Logic       | Custom Python logic                 |
| UI (optional)    | Streamlit or FastAPI                |
| Hosting          | Local or Windows VPS (user-run)     |

---

### 6. 🚨 Edge Cases to Handle

* Telegram messages edited after original post (update signal)
* Partial messages (e.g., SL sent first, TPs later)
* Conflicting signals within 30 mins
* Market closed or symbol not found on MT5
* MT5 disconnection or trade rejection
* Slippage on volatile entries
* User overrides (pause bot from UI or Telegram command)

---

### 7. 🧪 Success Criteria

* 95% signal parsing accuracy
* Trades executed within 3 seconds of signal
* Breakeven logic working in backtests
* Logs clean and traceable
* User can set risk % per trade and modify it

---

### 8. 🚀 Future Enhancements (SaaS mode)

* Multi-user account support with separate Telegram keys
* Hosted dashboard + secure MT5 bridge installer
* Subscription plans and Stripe integration
* User notifications (TP hit, SL hit, breakeven, etc.)
* Affiliate dashboard for prop firms

---
