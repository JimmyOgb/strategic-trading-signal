# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *

import json
import typing


class StrategicTradingSignal(gl.Contract):
    # Single TreeMap — keys are prefixed strings:
    #   "owner"                    -> contract owner address
    #   "config:symbol"            -> tracked symbol e.g. "BTCUSDT"
    #   "config:max_position"      -> str float, position cap
    #   "config:order_size"        -> str float, per-signal order size
    #   "config:max_drawdown_pct"  -> str float, e.g. "0.05"
    #   "position:current"         -> str float, current accumulated position
    #   "position:peak_equity"     -> str float, session-peak equity watermark
    #   "breaker:tripped"          -> "true" / "false"
    #   "breaker:reason"           -> trip reason string
    #   "signal:{id}"              -> JSON signal evaluation record (audit trail)
    #   "signal_count"             -> total signals evaluated
    state: TreeMap[str, str]

    def __init__(self):
        self.state = TreeMap()
        self.state["owner"]                   = str(gl.message.sender_address)
        self.state["config:symbol"]           = "BTCUSDT"
        self.state["config:max_position"]     = "0.01"
        self.state["config:order_size"]       = "0.001"
        self.state["config:max_drawdown_pct"] = "0.05"
        self.state["position:current"]        = "0.0"
        self.state["position:peak_equity"]    = "0.0"
        self.state["breaker:tripped"]         = "false"
        self.state["breaker:reason"]          = ""
        self.state["signal_count"]            = "0"

    # ── helpers ────────────────────────────────────────────────────────

    def _is_owner(self) -> bool:
        return str(gl.message.sender_address) == self.state["owner"]

    def _signal_key(self, sid: int) -> str:
        return "signal:" + str(sid)

    def _signal_count(self) -> int:
        return int(self.state["signal_count"])

    # ── write methods ──────────────────────────────────────────────────

    @gl.public.write
    def configure(
        self,
        symbol: str,
        max_position: str,
        order_size: str,
        max_drawdown_pct: str,
    ) -> typing.Any:
        """
        Owner-only: configure the tracked symbol and risk parameters.
        Mirrors the original bot's MAX_POSITION_SIZE / ORDER_SIZE /
        MAX_DRAWDOWN_PCT environment variables, now stored on-chain
        instead of in a local .env file.
        """
        if not self._is_owner():
            raise Exception("Only the contract owner can configure risk parameters.")

        self.state["config:symbol"]           = symbol.upper()
        self.state["config:max_position"]     = max_position
        self.state["config:order_size"]       = order_size
        self.state["config:max_drawdown_pct"] = max_drawdown_pct

        return (
            "Configured " + symbol.upper()
            + " | max_position=" + max_position
            + " | order_size=" + order_size
            + " | max_drawdown=" + max_drawdown_pct
        )

    @gl.public.write
    def reset_circuit_breaker(self) -> typing.Any:
        """
        Owner-only: manually clears a tripped circuit breaker after review.
        Mirrors the original design's "fail-closed, manual restart required"
        philosophy — there is no auto-reset path on-chain either.
        """
        if not self._is_owner():
            raise Exception("Only the contract owner can reset the circuit breaker.")

        self.state["breaker:tripped"]      = "false"
        self.state["breaker:reason"]       = ""
        self.state["position:peak_equity"] = "0.0"

        return "Circuit breaker manually reset by owner. Peak equity watermark cleared."

    @gl.public.write
    def evaluate_signal(self, market_data_url: str, news_query: str) -> typing.Any:
        """
        Core strategy step. Fetches live market/sentiment data, runs 5-node
        AI consensus to produce a composite trading signal, applies the same
        fail-closed risk vetoes as the original bot (sentiment veto, crowded
        long-short veto, position cap, drawdown circuit breaker), and records
        a BUY / HOLD / BLOCKED decision on-chain. This contract never holds
        exchange API keys and never submits orders itself — it produces a
        verifiable, AI-consensus-backed signal that an off-chain execution
        bot (or the user) can choose to act on.

        Args:
            market_data_url: URL to fetch live sentiment/derivatives data from
                             (e.g. a Fear & Greed Index page, exchange stats page).
            news_query:      Keyword/topic to evaluate news sentiment for.

        Returns:
            Decision string: "BUY", "HOLD", or "BLOCKED: <reason>".
        """
        if self.state["breaker:tripped"] == "true":
            return "BLOCKED: Circuit breaker tripped — " + self.state["breaker:reason"]

        symbol      = self.state["config:symbol"]
        max_pos     = float(self.state["config:max_position"])
        order_size  = float(self.state["config:order_size"])
        max_dd      = float(self.state["config:max_drawdown_pct"])
        current_pos = float(self.state["position:current"])
        peak_equity = float(self.state["position:peak_equity"])
        url         = market_data_url
        keyword     = news_query

        def run_signal_analysis() -> typing.Any:
            try:
                market_data = gl.nondet.web.render(url, mode="text")[:3000]
            except Exception:
                market_data = "Market data source unavailable."

            prompt = f"""
You are a quantitative crypto trading analyst producing a composite market
sentiment signal for {symbol}.

Live market/sentiment data from the source below:
{market_data}

News/topic keyword to weigh: {keyword}

Analyze the data for:
1. Fear & Greed style sentiment (extreme fear = contrarian bullish, extreme greed = caution)
2. Long/short positioning crowding (overcrowded longs = squeeze risk, bearish veto signal)
3. Taker buy/sell aggression ratio
4. News sentiment tone for the given keyword

Respond with the following JSON format:
{{
    "composite_score": float,        // -1.0 (strongly bearish) to 1.0 (strongly bullish)
    "long_short_crowded": bool,      // true if long positioning looks dangerously crowded
    "calibrated": bool,              // true if enough reliable data was available to judge
    "reasoning": str                 // one or two sentence explanation
}}
It is mandatory that you respond only using the JSON format above,
nothing else. Don't include any other words or characters,
your output must be only JSON without any formatting prefix or suffix.
This result should be perfectly parsable by a JSON parser without errors.
"""
            result = (
                gl.nondet.exec_prompt(prompt)
                .replace("```json", "")
                .replace("```", "")
            )
            print(result)
            return json.loads(result)

        analysis = gl.eq_principle.strict_eq(run_signal_analysis)

        composite_score     = float(analysis.get("composite_score", 0.0))
        long_short_crowded  = bool(analysis.get("long_short_crowded", False))
        calibrated          = bool(analysis.get("calibrated", False))
        reasoning           = analysis.get("reasoning", "")

        sid = self._signal_count()
        decision = "HOLD"
        block_reason = ""

        # ── Fail-closed: uncalibrated data blocks any action ──────────
        if not calibrated:
            decision = "BLOCKED"
            block_reason = "Market data uncalibrated or incomplete. Failing closed."

        # ── Sentiment veto (mirrors original: composite < -0.5 blocks buys) ──
        elif composite_score < -0.5:
            decision = "BLOCKED"
            block_reason = "Composite score " + str(round(composite_score, 2)) + " triggers downside veto."

        # ── Crowded long-short veto ──────────────────────────────────
        elif composite_score > 0.15 and long_short_crowded:
            decision = "BLOCKED"
            block_reason = "Bullish score but long positioning is overcrowded — squeeze risk veto."

        # ── Position cap check ─────────────────────────────────────
        elif composite_score > 0.15:
            headroom = max(0.0, max_pos - current_pos)
            if order_size > headroom:
                decision = "BLOCKED"
                block_reason = (
                    "Order size " + str(order_size)
                    + " exceeds remaining position headroom " + str(round(headroom, 6))
                    + " (cap " + str(max_pos) + ", current " + str(current_pos) + ")."
                )
            else:
                decision = "BUY"

        # ── Drawdown circuit breaker (uses current_pos as equity proxy) ──
        current_equity = current_pos
        if current_equity > peak_equity:
            self.state["position:peak_equity"] = str(current_equity)
        elif peak_equity > 0:
            drawdown = (peak_equity - current_equity) / peak_equity
            if drawdown >= max_dd:
                self.state["breaker:tripped"] = "true"
                self.state["breaker:reason"] = (
                    "Drawdown " + str(round(drawdown * 100, 2)) + "% exceeded max allowed "
                    + str(round(max_dd * 100, 2)) + "% (peak " + str(peak_equity)
                    + ", current " + str(current_equity) + ")."
                )
                decision = "BLOCKED"
                block_reason = "Circuit breaker tripped this cycle — " + self.state["breaker:reason"]

        # ── Persist the signal record (audit trail) ──────────────────
        record = json.dumps({
            "id":                 sid,
            "symbol":             symbol,
            "composite_score":    composite_score,
            "long_short_crowded": long_short_crowded,
            "calibrated":         calibrated,
            "reasoning":          reasoning,
            "decision":           decision,
            "block_reason":       block_reason,
        })
        self.state[self._signal_key(sid)] = record
        self.state["signal_count"] = str(sid + 1)

        if decision == "BUY":
            return "BUY — score " + str(round(composite_score, 2)) + ". " + reasoning
        elif decision == "HOLD":
            return "HOLD — score " + str(round(composite_score, 2)) + " inside steady band. " + reasoning
        else:
            return "BLOCKED: " + block_reason

    @gl.public.write
    def register_fill(self, side: str, amount: str) -> typing.Any:
        """
        Owner-only: records that an off-chain execution bot actually filled
        an order based on a prior signal, updating the on-chain position
        tracker. This mirrors the original RiskCircuitBreaker.register_fill()
        but is now an explicit, auditable on-chain transaction rather than
        in-process Python state.

        Args:
            side:   "buy" or "sell"
            amount: Fill amount as a string (e.g. "0.001")
        """
        if not self._is_owner():
            raise Exception("Only the contract owner can register fills.")

        s   = side.lower()
        amt = float(amount)
        current = float(self.state["position:current"])

        if s == "buy":
            current += amt
        elif s == "sell":
            current = max(0.0, current - amt)
        else:
            raise Exception("Invalid side. Must be 'buy' or 'sell'.")

        self.state["position:current"] = str(current)

        return "Fill registered: " + s.upper() + " " + amount + ". New position: " + str(current)

    # ── view methods ───────────────────────────────────────────────────

    @gl.public.view
    def get_signal(self, signal_id: u256) -> str:
        """Returns a single signal evaluation record as JSON."""
        k = self._signal_key(int(signal_id))
        if k not in self.state:
            return '{"error": "Signal not found."}'
        return self.state[k]

    @gl.public.view
    def get_risk_status(self) -> str:
        """Returns the current risk/circuit-breaker status summary."""
        return (
            "Symbol: "        + self.state["config:symbol"]
            + " | Position: "  + self.state["position:current"]
            + " / "            + self.state["config:max_position"]
            + " | Breaker: "   + ("TRIPPED — " + self.state["breaker:reason"] if self.state["breaker:tripped"] == "true" else "OK")
        )

    @gl.public.view
    def get_total_signals(self) -> str:
        """Returns the total number of signals evaluated."""
        return self.state["signal_count"]

    @gl.public.view
    def get_owner(self) -> str:
        """Returns the contract owner address."""
        return self.state["owner"]
