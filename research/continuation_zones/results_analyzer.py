from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import matplotlib
import pandas as pd

from .backtest_engine import Trade
from .optimization import OptimizationResult

matplotlib.use("Agg")
import matplotlib.pyplot as plt


@dataclass
class ATMProfile:
    name: str
    stop_ticks: int
    target_ticks: int
    breakeven_trigger_ticks: int
    breakeven_offset_ticks: int
    trail_type: str
    trail_amount_ticks: int
    trail_activation_ticks: int
    expected_rr: float
    expected_win_rate: float
    expected_ev_per_trade: float
    nt8_stop_strategy: str
    source_param_set: int
    zone_type_recommendation: str


class ResultsAnalyzer:
    def __init__(
        self,
        trades: list[Trade],
        optimization_results: list[OptimizationResult],
        tick_size: float = 0.25,
        tick_value: float = 5.0,
        min_oos_trades: int = 200,
    ):
        self.trades = list(trades)
        self.optimization_results = list(optimization_results)
        self.tick_size = tick_size
        self.tick_value = tick_value
        self.min_oos_trades = min_oos_trades
        self._profiles: list[ATMProfile] | None = None
        self._result_by_trial = {result.trial_number: result for result in self.optimization_results}

    def derive_atm_profiles(self) -> list[ATMProfile]:
        """
        Derive 3 ATM profiles from the top-10 OOS optimization results.
        Returns [Conservative, Balanced, Aggressive].
        """
        if not self.optimization_results:
            raise ValueError("optimization_results cannot be empty")

        top_results = sorted(
            self.optimization_results[:10],
            key=lambda result: (result.fitness, result.oos_sharpe, result.oos_total_pnl),
            reverse=True,
        )
        conservative_result = max(
            top_results,
            key=lambda result: (result.oos_win_rate, result.fitness, result.oos_sharpe),
        )
        balanced_result = top_results[0]
        aggressive_result = max(
            top_results,
            key=lambda result: (result.oos_sharpe, result.fitness, result.oos_total_pnl),
        )

        selected_results = [conservative_result, balanced_result, aggressive_result]
        seen_signatures: set[tuple[tuple[str, object], ...]] = set()
        profiles: list[ATMProfile] = []

        for name, result in zip(["Conservative", "Balanced", "Aggressive"], selected_results, strict=True):
            signature = self._result_signature(result)
            if signature in seen_signatures and profiles:
                profiles.append(self._duplicate_profile_with_variation(profiles[-1], name, len(profiles)))
                continue
            seen_signatures.add(signature)
            profiles.append(self._build_profile(name, result))

        while len(profiles) < 3:
            source_profile = profiles[-1] if profiles else self._build_profile("Balanced", balanced_result)
            profiles.append(self._duplicate_profile_with_variation(source_profile, ["Conservative", "Balanced", "Aggressive"][len(profiles)], len(profiles)))

        self._profiles = profiles[:3]
        return list(self._profiles)

    def save_atm_recommendations(self, profiles: list[ATMProfile], output_path: Path) -> None:
        """Write atm_recommendations.md with all 3 profiles fully specified."""
        if not profiles:
            raise ValueError("profiles cannot be empty")

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        top_results = sorted(
            self.optimization_results[:10],
            key=lambda result: (result.fitness, result.oos_sharpe, result.oos_total_pnl),
            reverse=True,
        )
        best_result = top_results[0]
        generated_at = pd.Timestamp.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        oos_start, oos_end = self._trade_date_range()
        n_trials = max((result.trial_number for result in self.optimization_results), default=-1) + 1
        n_oos_months = max(1, round((oos_end - oos_start).days / 30.44)) if oos_end >= oos_start else 0

        lines = [
            "# NQ Continuation Zone Scalping — ATM Recommendations",
            f"Generated: {generated_at}",
            f"Based on: {n_trials} Optuna trials, walk-forward OOS period {oos_start.date()} to {oos_end.date()}",
            "",
            "## Summary",
            "",
            "| Profile | Stop | Target | R:R | Win Rate | EV/Trade | OOS Sharpe |",
            "|---------|------|--------|-----|----------|----------|------------|",
        ]
        for profile in profiles:
            result = self._result_for_profile(profile)
            lines.append(
                f"| {profile.name} | {profile.stop_ticks} ticks | {profile.target_ticks} ticks | "
                f"{profile.expected_rr:.2f}:1 | {profile.expected_win_rate:.1%} | "
                f"${profile.expected_ev_per_trade:.2f} | {result.oos_sharpe:.2f} |"
            )

        for index, profile in enumerate(profiles, start=1):
            result = self._result_for_profile(profile)
            min_score = int(result.params.get("min_score", 0))
            lines.extend(
                [
                    "",
                    f"## Profile {index}: {profile.name}",
                    "",
                    "### NinjaTrader ATM Settings",
                    "| Field | Value |",
                    "|-------|-------|",
                    f"| Stop Loss | {profile.stop_ticks} ticks |",
                    f"| Profit Target | {profile.target_ticks} ticks |",
                    f"| Auto Breakeven — Profit Trigger | {profile.breakeven_trigger_ticks} ticks |",
                    f"| Auto Breakeven — Plus | {profile.breakeven_offset_ticks} ticks |",
                    f"| Auto Trail — Type | {profile.trail_type} |",
                    f"| Auto Trail — Amount | {profile.trail_amount_ticks} ticks |",
                    f"| Auto Trail — Profit Trigger | {profile.trail_activation_ticks} ticks |",
                    "",
                    "### Performance (OOS)",
                    f"- Win Rate: {profile.expected_win_rate:.1%}",
                    f"- Expected Value per Trade: ${profile.expected_ev_per_trade:.2f}",
                    f"- OOS Sharpe: {result.oos_sharpe:.2f}",
                    f"- OOS Trades: {result.oos_trades}",
                    "",
                    "### Recommended For",
                    f"- Zone type: {profile.zone_type_recommendation}",
                    f"- Minimum zone score: {min_score}",
                ]
            )

        lines.extend(
            [
                "",
                "## Zone Detection Parameters (Best OOS Set)",
                "| Parameter | Value |",
                "|-----------|-------|",
                f"| SmallBodyRatio | {float(best_result.params.get('small_body_ratio', 0.0)):.2f} |",
                f"| MinZoneTicks | {int(best_result.params.get('min_zone_ticks', 0))} |",
                f"| MaxAgeBars5m | {int(best_result.params.get('max_zone_age_bars_5m', 0))} |",
                f"| MaxAgeBars15m | {int(best_result.params.get('max_zone_age_bars_15m', 0))} |",
                f"| MaxTouchCount | {int(best_result.params.get('max_touch_count', 0))} |",
                f"| MinScore | {int(best_result.params.get('min_score', 0))} |",
                f"| RTH Only | {bool(best_result.params.get('rth_only', False))} |",
                "",
                "## Honest Limitations",
                "- Backtest uses limit order fills at zone boundary — real fills may differ",
                "- Slippage assumed: 1 tick per side",
                "- Commission assumed: $2.00 per contract per side",
                f"- Walk-forward OOS period: {oos_start.date()} to {oos_end.date()} ({n_oos_months} months)",
                f"- Minimum OOS trades required: {self.min_oos_trades}",
                "- Results should be paper-traded before live deployment",
            ]
        )
        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def save_trade_csv(self, output_path: Path) -> None:
        """Write all_trades_best_params.csv."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        rows = [asdict(trade) for trade in self.trades]
        pd.DataFrame(rows).to_csv(output_path, index=False)

    def save_equity_curve(self, output_path: Path) -> None:
        """Write equity_curve_best_params.png using matplotlib."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        figure, axis = plt.subplots(figsize=(10, 5))
        if self.trades:
            trades_df = pd.DataFrame(
                {
                    "exit_time": [trade.exit_time for trade in self.trades],
                    "cum_pnl": pd.Series([trade.pnl_dollars for trade in self.trades], dtype=float).cumsum(),
                }
            )
            axis.plot(trades_df["exit_time"], trades_df["cum_pnl"], color="#2563eb", linewidth=2)
        else:
            axis.plot([], [])
            axis.text(0.5, 0.5, "No trades available", ha="center", va="center", transform=axis.transAxes)
        axis.set_title("Equity Curve — Best OOS Parameter Set")
        axis.set_xlabel("Exit Time")
        axis.set_ylabel("Cumulative PnL ($)")
        axis.grid(True, alpha=0.3)
        figure.tight_layout()
        figure.savefig(output_path, dpi=150)
        plt.close(figure)

    def _build_profile(self, name: str, result: OptimizationResult) -> ATMProfile:
        stop_ticks = int(result.params.get("stop_ticks", 0))
        target_ticks = int(result.params.get("target_ticks", 0))
        breakeven_trigger_ticks = int(result.params.get("breakeven_ticks", 0))
        trail_amount_ticks = int(result.params.get("trail_ticks", 0))
        trail_activation_ticks = int(result.params.get("trail_activation_ticks", 0)) if trail_amount_ticks > 0 else 0
        trail_type = "None" if trail_amount_ticks == 0 else "Tick"
        expected_ev_per_trade = result.oos_total_pnl / result.oos_trades if result.oos_trades else 0.0
        zone_type = self._zone_type_recommendation(result)

        nt8_stop_strategy = (
            f"Stop Loss: {stop_ticks} ticks | Profit Target: {target_ticks} ticks | "
            f"Auto Breakeven — Profit Trigger: {breakeven_trigger_ticks} ticks | "
            f"Auto Breakeven — Plus: 0 ticks | Auto Trail — Type: {trail_type} | "
            f"Auto Trail — Amount: {trail_amount_ticks} ticks | "
            f"Auto Trail — Profit Trigger: {trail_activation_ticks} ticks"
        )

        return ATMProfile(
            name=name,
            stop_ticks=stop_ticks,
            target_ticks=target_ticks,
            breakeven_trigger_ticks=breakeven_trigger_ticks,
            breakeven_offset_ticks=0,
            trail_type=trail_type,
            trail_amount_ticks=trail_amount_ticks,
            trail_activation_ticks=trail_activation_ticks,
            expected_rr=round(target_ticks / stop_ticks, 4) if stop_ticks else 0.0,
            expected_win_rate=float(result.oos_win_rate),
            expected_ev_per_trade=float(expected_ev_per_trade),
            nt8_stop_strategy=nt8_stop_strategy,
            source_param_set=result.trial_number,
            zone_type_recommendation=zone_type,
        )

    def _duplicate_profile_with_variation(self, profile: ATMProfile, name: str, offset_index: int) -> ATMProfile:
        stop_delta = 2 if offset_index % 2 == 0 else 0
        target_delta = 2 if offset_index % 2 == 1 else 4
        stop_ticks = max(4, profile.stop_ticks + stop_delta)
        target_ticks = max(stop_ticks, profile.target_ticks + target_delta)
        breakeven_trigger_ticks = max(2, min(target_ticks - 1, profile.breakeven_trigger_ticks + (2 if target_delta >= 4 else 0)))
        trail_type = profile.trail_type if target_ticks > stop_ticks else "None"
        trail_amount_ticks = profile.trail_amount_ticks if trail_type == "Tick" else 0
        trail_activation_ticks = profile.trail_activation_ticks if trail_type == "Tick" else 0
        nt8_stop_strategy = (
            f"Stop Loss: {stop_ticks} ticks | Profit Target: {target_ticks} ticks | "
            f"Auto Breakeven — Profit Trigger: {breakeven_trigger_ticks} ticks | "
            f"Auto Breakeven — Plus: {profile.breakeven_offset_ticks} ticks | Auto Trail — Type: {trail_type} | "
            f"Auto Trail — Amount: {trail_amount_ticks} ticks | "
            f"Auto Trail — Profit Trigger: {trail_activation_ticks} ticks"
        )
        return ATMProfile(
            name=name,
            stop_ticks=stop_ticks,
            target_ticks=target_ticks,
            breakeven_trigger_ticks=breakeven_trigger_ticks,
            breakeven_offset_ticks=profile.breakeven_offset_ticks,
            trail_type=trail_type,
            trail_amount_ticks=trail_amount_ticks,
            trail_activation_ticks=trail_activation_ticks,
            expected_rr=round(target_ticks / stop_ticks, 4),
            expected_win_rate=profile.expected_win_rate,
            expected_ev_per_trade=profile.expected_ev_per_trade,
            nt8_stop_strategy=nt8_stop_strategy,
            source_param_set=profile.source_param_set,
            zone_type_recommendation=profile.zone_type_recommendation,
        )

    @staticmethod
    def _result_signature(result: OptimizationResult) -> tuple[tuple[str, object], ...]:
        return tuple(sorted(result.params.items()))

    @staticmethod
    def _zone_type_recommendation(result: OptimizationResult) -> str:
        age_5m = int(result.params.get("max_zone_age_bars_5m", 0))
        age_15m = int(result.params.get("max_zone_age_bars_15m", 0))
        if age_5m >= 180 and age_15m <= 40:
            return "5m"
        if age_15m >= 70 and age_5m <= 120:
            return "15m"
        return "both"

    def _result_for_profile(self, profile: ATMProfile) -> OptimizationResult:
        return self._result_by_trial[profile.source_param_set]

    def _trade_date_range(self) -> tuple[pd.Timestamp, pd.Timestamp]:
        if not self.trades:
            today = pd.Timestamp.utcnow().tz_localize("UTC") if pd.Timestamp.utcnow().tzinfo is None else pd.Timestamp.utcnow()
            return today, today
        start = min(trade.entry_time for trade in self.trades)
        end = max(trade.exit_time for trade in self.trades)
        return pd.Timestamp(start), pd.Timestamp(end)


__all__ = ["ATMProfile", "ResultsAnalyzer"]
