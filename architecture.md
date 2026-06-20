# Architecture — SignalCore

## Origin: Porting a Standalone Bot to a GenVM Contract

The source material was a full asyncio Python trading bot with a 5-minute
polling loop, subprocess-based exchange execution via a `bgc` CLI tool,
live Bitget API key custody, and an MCP client session for market data.
None of that architecture has a GenVM equivalent, since contracts:

  - have no background process or event loop (only execute on transaction)
  - cannot spawn OS subprocesses
  - have no custody model for external exchange credentials
  - can only reach the outside world via gl.nondet.web.render() and
    gl.nondet.exec_prompt()

This contract therefore extracts and translates only the DECISION-MAKING
core -- the part that benefits from decentralization -- and discards the
execution/custody layer entirely.

## Storage Design

Single TreeMap[str, str] with prefixed keys:

  "owner"                    -> contract owner
  "config:symbol"            -> tracked symbol
  "config:max_position"      -> position cap (string float)
  "config:order_size"        -> per-signal order size (string float)
  "config:max_drawdown_pct"  -> drawdown limit (string float, e.g. "0.05")
  "position:current"         -> current accumulated position
  "position:peak_equity"     -> session-peak equity watermark
  "breaker:tripped"          -> "true" / "false"
  "breaker:reason"           -> trip reason
  "signal:{id}"              -> JSON signal evaluation record
  "signal_count"             -> total signals evaluated

All numeric values are stored as strings and cast to float/int inside
method bodies, since GenLayer write method parameters do not support
float directly.

## Replacing the Hardcoded Formula with AI Consensus

Original:
  composite_score = (fg_signal*0.35) + (ls_signal*0.25) +
                     (taker_signal*0.20) + (news_score*0.20)

This contract instead asks 5 independent validator nodes to read the SAME
live web data and news context, and each independently produce a
composite_score via LLM reasoning. gl.eq_principle.strict_eq() requires
all 5 to agree before the score is used. This trades a fixed formula for
a judgment-based consensus -- arguably better suited to qualitative
signals like "is this long/short ratio dangerously crowded" which don't
reduce cleanly to a single hardcoded threshold in all market regimes.

## Preserved Risk Logic (same order of checks as the original)

  1. Fail-closed: not calibrated -> BLOCKED
  2. Sentiment veto: composite_score < -0.5 -> BLOCKED
  3. Crowded long/short veto: score > 0.15 AND crowded -> BLOCKED
  4. Position cap: order_size > headroom -> BLOCKED, else BUY
  5. Drawdown circuit breaker: checked every cycle regardless of decision,
     can override a BUY decision into BLOCKED if drawdown limit is hit

## Why register_fill() Exists Separately From evaluate_signal()

The contract intentionally separates SIGNAL (what the AI consensus
recommends) from FILL (what actually happened on the exchange). This
mirrors the original bot's dry-run vs live execution distinction --
evaluate_signal() never assumes an order was filled. An off-chain
execution layer (a slimmed-down version of the original Bitget bridge,
with the scoring logic removed) reads the signal, decides whether to
act, places the real order, and reports the outcome back via
register_fill(). This keeps the contract honest: it can never claim
position changes it didn't actually observe.

## No Auto-Reset on Circuit Breaker

Identical philosophy to the original RiskCircuitBreaker: once tripped,
state stays tripped until reset_circuit_breaker() is explicitly called
by the owner. Auto-resetting on a bad signal risks re-entering a losing
position repeatedly -- the manual gate is intentional, not an oversight.

## Type Constraints

  Class annotations : TreeMap[str, str] only
  Method parameters  : str, u256, bool   (NOT float, dict)
  Write returns      : typing.Any
  View returns        : str               (NOT dict, list)
