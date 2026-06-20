# 📡 SignalCore — AI Trading Signal Oracle

> A GenLayer Intelligent Contract that produces verifiable, AI-consensus-backed trading signals — translating a fail-closed risk-management trading bot architecture into a trustless on-chain decision engine.

[![GenLayer Studio](https://img.shields.io/badge/GenLayer_Studio-Open_Contract-3b82f6?style=for-the-badge&logoColor=white)](https://studio.genlayer.com/?import-contract=0x9ba3126C5f800F455fb22887507C5eb635327246)
[![Network](https://img.shields.io/badge/Network-GenLayer_Studionet-22c55e?style=for-the-badge)](https://studio.genlayer.com)
[![License](https://img.shields.io/badge/License-MIT-f59e0b?style=for-the-badge)](LICENSE)

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Live Deployment](#-live-deployment)
- [Why This Isn't a 1:1 Port](#-why-this-isnt-a-11-port)
- [How It Works](#-how-it-works)
- [Contract Architecture](#-contract-architecture)
- [Methods](#-methods)
- [Frontend](#-frontend)
- [Getting Started](#-getting-started)
- [Project Structure](#-project-structure)
- [Tech Stack](#-tech-stack)

---

## 🌐 Overview

**SignalCore** is the GenLayer Intelligent Contract translation of a standalone Python asyncio trading bot. The original bot polled market sentiment data every 5 minutes, computed a hardcoded weighted composite score, and placed real spot orders on Bitget via a CLI subprocess bridge.

This contract preserves the **decision-making philosophy** — composite sentiment scoring, fail-closed data validation, sentiment vetoes, crowded long/short squeeze protection, position caps, and a manual-reset-only drawdown circuit breaker — and re-expresses it using GenLayer's actual strengths: five independent AI validators reaching consensus on a live, real-world signal instead of a single hardcoded formula running on one server.

It produces a `BUY` / `HOLD` / `BLOCKED: reason` signal with a full on-chain audit trail. It does **not** execute trades or hold exchange credentials — that responsibility stays with an off-chain execution layer, which reports fills back via `register_fill()`.

---

## 🚀 Live Deployment

| Resource | Link |
|---|---|
| **Contract on GenLayer Studio** | [0x9ba3126C5f800F455fb22887507C5eb635327246](https://studio.genlayer.com/?import-contract=0x9ba3126C5f800F455fb22887507C5eb635327246) |
| **Network** | GenLayer Studionet |
| **Contract Address** | `0x9ba3126C5f800F455fb22887507C5eb635327246` |

---

## ⚠️ Why This Isn't a 1:1 Port

The original script is a standalone process — `asyncio` event loop, `subprocess` calls to a `bgc` CLI, live Bitget API key custody, and an MCP client session. None of that has a GenVM equivalent:

| Original Bot Component | GenVM Reality |
|---|---|
| `asyncio` 5-minute loop (`main_loop`) | Contracts only execute on incoming transactions — no background process exists |
| `subprocess.create_subprocess_exec(["npx", "bgc", ...])` | Contracts cannot spawn OS processes |
| `BitgetExecutionBridge` placing live orders | No custody model for external exchange API keys inside a contract |
| `MarketDataMcpClient` (MCP `ClientSession`) | Contracts can only reach the outside world via `gl.nondet.web.render()` / `gl.nondet.exec_prompt()` |
| `.env` / `os.getenv()` | No environment variables on-chain — config now lives in contract state, settable via `configure()` |

What carries over **faithfully**:

| Original Logic | This Contract |
|---|---|
| Hardcoded weighted formula (`fg*0.35 + ls*0.25 + taker*0.20 + news*0.20`) | 5 AI validators independently reach consensus on a composite score from live data |
| `if not snapshot.calibrated: return False` | Same fail-closed check |
| `composite_score < -0.5` veto | Same threshold |
| Crowded long/short squeeze veto | Same concept, AI-judged from live data |
| `RiskCircuitBreaker` (cap, drawdown, no auto-reset) | Same math, same manual-reset-only philosophy |
| `register_fill()` | Same method name and purpose, now an explicit on-chain transaction |

---

## ⚙️ How It Works

```
configure(symbol, max_position, order_size, max_drawdown_pct)
        │
        └── owner sets risk parameters, stored on-chain

evaluate_signal(market_data_url, news_query)
        │
        ├── if breaker tripped → return BLOCKED immediately
        │
        └── run_signal_analysis() inner function
                │
                ├── gl.nondet.web.render(market_data_url, mode="text")[:3000]
                ├── gl.nondet.exec_prompt(prompt)
                │   5 validator nodes independently judge:
                │   · Fear & Greed style sentiment
                │   · Long/short positioning crowding
                │   · Taker buy/sell aggression
                │   · News sentiment for the given keyword
                │
                └── gl.eq_principle.strict_eq()
                    All 5 nodes return identical
                    {composite_score, long_short_crowded, calibrated, reasoning}
                            │
            ┌───────────────┼───────────────┬──────────────────┐
       uncalibrated    score < -0.5    crowded longs      position cap
            │                │              │                  │
         BLOCKED          BLOCKED        BLOCKED            BLOCKED
                                                                 │
                                                         score > 0.15 & OK
                                                                 │
                                                               BUY
            │
      drawdown check (peak vs current position as equity proxy)
            │
      if tripped → BLOCKED, breaker.tripped = true (manual reset required)

register_fill(side, amount)
        │
        └── owner records an actual off-chain fill, updating position:current

reset_circuit_breaker()
        │
        └── owner-only manual clear after review (no auto-reset, by design)
```

---

## 🏗️ Contract Architecture

```python
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

class StrategicTradingSignal(gl.Contract):
    state: TreeMap[str, str]
```

### Storage Design

Single `TreeMap[str, str]` with prefixed keys:

| Key | Value | Description |
|---|---|---|
| `"owner"` | `"0xOwner…"` | Contract owner |
| `"config:symbol"` | `"BTCUSDT"` | Tracked symbol |
| `"config:max_position"` | `"0.01"` | Position cap |
| `"config:order_size"` | `"0.001"` | Per-signal order size |
| `"config:max_drawdown_pct"` | `"0.05"` | Drawdown limit (5%) |
| `"position:current"` | `"0.003"` | Current accumulated position |
| `"position:peak_equity"` | `"0.005"` | Session-peak equity watermark |
| `"breaker:tripped"` | `"false"` | Circuit breaker state |
| `"breaker:reason"` | `""` | Trip reason, if tripped |
| `"signal:{id}"` | JSON | Full signal evaluation record (audit trail) |
| `"signal_count"` | `"7"` | Total signals evaluated |

---

## 📌 Methods

### Write Methods

#### `configure(symbol, max_position, order_size, max_drawdown_pct) → str`
Owner-only. Sets risk parameters.

#### `evaluate_signal(market_data_url, news_query) → str`
Core method. Runs 5-node AI consensus, applies all risk vetoes, returns `"BUY — ..."`, `"HOLD — ..."`, or `"BLOCKED: ..."`.

#### `register_fill(side, amount) → str`
Owner-only. Records an actual off-chain fill against the position tracker.

#### `reset_circuit_breaker() → str`
Owner-only. Manually clears a tripped breaker. No auto-reset exists, by design — mirrors the original bot's philosophy that a bad signal shouldn't auto-recover into repeated losses.

### View Methods

| Method | Returns |
|---|---|
| `get_signal(signal_id)` | Full JSON signal record |
| `get_risk_status()` | `"Symbol: BTCUSDT \| Position: 0.003 / 0.01 \| Breaker: OK"` |
| `get_total_signals()` | Total signal count |
| `get_owner()` | Owner address |

---

## 🖥️ Frontend

Quant terminal aesthetic — dark blue/charcoal, professional trading-desk feel:

- **Circuit breaker banner** — prominent red alert bar when tripped, with owner-only reset button
- **Configure panel** — symbol, position cap, order size, drawdown % inputs
- **Evaluate Signal panel** — 5-node consensus animation, color-coded verdict card (green BUY / amber HOLD / red BLOCKED)
- **Register Fill panel** — side + amount, updates position tracker
- **Risk Status card** — live symbol/position/breaker summary
- **Signal History table** — every evaluation with composite score and decision pill
- **Transaction log** — all calls with status indicators

### Running locally

```bash
open frontend/index.html
npx serve frontend/
python3 -m http.server 8080 --directory frontend/
```

### Deploying

```bash
netlify deploy --prod --dir frontend/
vercel --prod
```

---

## 🏁 Getting Started

### 1. Open in GenLayer Studio
```
https://studio.genlayer.com/?import-contract=0x9ba3126C5f800F455fb22887507C5eb635327246
```

### 2. Configure Risk Parameters
```
configure("BTCUSDT", "0.01", "0.001", "0.05")
```

### 3. Evaluate a Signal
```
evaluate_signal("https://alternative.me/crypto/fear-and-greed-index/", "BTC")
```

### 4. Register a Fill (after off-chain execution)
```
register_fill("buy", "0.001")
```

### 5. Check Risk Status
```
get_risk_status()
→ "Symbol: BTCUSDT | Position: 0.001 / 0.01 | Breaker: OK"
```

---

## 📁 Project Structure

```
strategic-trading-signal/
├── contract/
│   └── strategic_trading_signal.py   # GenLayer Intelligent Contract
├── frontend/
│   └── index.html                    # Quant terminal dashboard
├── docs/
│   └── architecture.md               # Storage design, port rationale, consensus notes
├── .gitignore
├── LICENSE
├── package.json
└── README.md
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **Blockchain** | GenLayer (L2, Studionet) |
| **Contract Language** | Python (GenLayer Intelligent Contract) |
| **AI Consensus** | `gl.eq_principle.strict_eq` — 5 validator nodes |
| **Web Data** | `gl.nondet.web.render` → live sentiment/market sources |
| **LLM Execution** | `gl.nondet.exec_prompt` (multi-model via OpenRouter) |
| **Storage** | `TreeMap[str, str]` with prefixed key namespacing |
| **Frontend** | Vanilla HTML / CSS / JS — zero dependencies |
| **Fonts** | Inter · JetBrains Mono |

---

## 📜 License

MIT — see [LICENSE](LICENSE) for details.
