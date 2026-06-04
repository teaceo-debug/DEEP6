# Playbook: DOM Signal Development

## Goal
Build a new DOM signal detector, wire it into the registry,
verify it fires correctly, and measure its edge.

## The DOM Signal Architecture

Every signal detector in deep6v2 follows this interface:

```python
class ISignalDetector(Protocol):
    def on_bar(self, bar: FootprintBar, ctx: SessionContext) -> list[SignalResult]: ...

class IDepthConsumingDetector(ISignalDetector, Protocol):
    def on_depth(self, snapshot: DOMSnapshot) -> None: ...  # called on every DOM update
```

### FootprintBar has (from synthesized OHLCV):
```python
bar.open, bar.high, bar.low, bar.close  # OHLCV
bar.delta       # int: total_ask_vol - total_bid_vol (synthetic estimate)
bar.total_volume
bar.bid_volumes # dict[float, int]: {price: sell_aggressor_volume}
bar.ask_volumes # dict[float, int]: {price: buy_aggressor_volume}
bar.poc_price, bar.poc_volume
bar.vah, bar.val  # value area high/low (70% of session volume)
bar.cvd         # cumulative delta (running since session open)
bar.bar_index   # 0-based within session
bar.timestamp
```

### SessionContext has:
```python
ctx.atr         # 14-bar average true range
ctx.cvd         # same as bar.cvd
ctx.vah, ctx.val, ctx.poc  # session profile (updated each bar)
ctx.bar_history  # deque[FootprintBar] — last 200 bars
ctx.price_history, ctx.cvd_history, ctx.delta_history
ctx.poc_history, ctx.vol_history
ctx.current_bar
```

## Building a new signal (template)

```python
# deep6v2/signals/my_dom_signal.py
from deep6v2.config.signals import SignalConfig
from deep6v2.types.bar import FootprintBar
from deep6v2.types.signal import Direction, SignalId, SignalResult
from deep6v2.types.session import SessionContext


class MyDOMSignalDetector:
    """One line description of what this detects."""

    def __init__(self, config: SignalConfig | None = None) -> None:
        self._config = config or SignalConfig()

    def on_bar(self, bar: FootprintBar, ctx: SessionContext) -> list[SignalResult]:
        results: list[SignalResult] = []

        # Need at least N bars of history
        if len(ctx.bar_history) < 3:
            return results

        # Your detection logic here
        strength = self._compute_strength(bar, ctx)
        if strength <= 0:
            return results

        direction = self._determine_direction(bar, ctx)

        results.append(SignalResult(
            signal_id=SignalId.MY_SIGNAL_ID,  # add to SignalId enum first
            direction=direction,
            strength=min(strength, 1.0),
            detail=f"my_signal at {bar.close:.2f} strength={strength:.3f}",
            price=bar.close,
        ))
        return results

    def _compute_strength(self, bar: FootprintBar, ctx: SessionContext) -> float:
        # Return 0.0 if condition not met, 0.0-1.0 if met
        ...

    def _determine_direction(self, bar: FootprintBar, ctx: SessionContext) -> Direction:
        ...
```

## Wiring the new signal

### 1. Add to SignalId enum
```python
# deep6v2/types/signal.py
class SignalId(str, Enum):
    ...
    MY_SIGNAL_ID = "MY_SIGNAL_ID"  # add here
```

### 2. Add to SIGNAL_TO_CATEGORY mapping
```python
# deep6v2/types/signal.py
SIGNAL_TO_CATEGORY: dict[SignalId, SignalCategory | None] = {
    ...
    SignalId.MY_SIGNAL_ID: SignalCategory.ABSORPTION,  # or whichever category
}
```

### 3. Register in DetectorRegistry
```python
# deep6v2/signals/registry.py
from deep6v2.signals.my_dom_signal import MyDOMSignalDetector

@classmethod
def create_default(cls, config: SignalConfig | None = None) -> "DetectorRegistry":
    ...
    my_signal = MyDOMSignalDetector(signal_config)
    detectors = [
        ...,
        my_signal,  # add here
    ]
```

### 4. Add to scoring weights
```python
# deep6v2/config/scoring.py
class ScoringConfig(BaseSettings):
    ...
    my_category_weight: float = 15.0  # tune this later
```

## Testing the signal

### Unit test pattern (tests_v2/signals/test_my_signal.py)
```python
from tests_v2.conftest import sample_footprint_bar, sample_session_context

def test_fires_on_expected_condition():
    bar = sample_footprint_bar(delta=-500, total_volume=2000)
    ctx = sample_session_context()
    detector = MyDOMSignalDetector()
    results = detector.on_bar(bar, ctx)
    assert any(r.signal_id == SignalId.MY_SIGNAL_ID for r in results)
    assert results[0].direction == Direction.BULLISH
    assert 0 < results[0].strength <= 1.0

def test_does_not_fire_on_noise():
    bar = sample_footprint_bar(delta=10, total_volume=100)
    ctx = sample_session_context()
    detector = MyDOMSignalDetector()
    results = detector.on_bar(bar, ctx)
    assert not results
```

### Edge measurement after wiring
```bash
# Re-run collection to include new signal
python scripts/signal_collect.py

# Measure edge
python scripts/signal_analyze.py --signal MY_SIGNAL_ID --window 5
```

## DOM-specific signal ideas to explore

These are unbuilt or partially built — high research value:

| Signal | Detection method | Expected edge |
|--------|-----------------|---------------|
| **Delta extremes at VAH/VAL** | DELT_N when price at value area extreme | HIGH — confluence with structure |
| **POC rejection** | Multiple bars near POC, delta diverges | MEDIUM |
| **Volume node punch-through** | Price crosses HVN with accelerating delta | HIGH |
| **Aggressor exhaustion** | Large delta spike → next bar delta reverts | HIGH |
| **Multi-bar absorption** | Absorption signal on 3 consecutive bars | HIGH — very rare, very reliable |
| **Opening range break with volume** | First 30-min high/low break + high volume | MEDIUM |
| **CVD vs price multi-bar divergence** | DELT_04 variant with 5-bar lookback | HIGH |
| **Session POC magnet** | Price within 2 ticks of POC, high volume | MEDIUM |
| **Failed auction at extreme** | AUCT_01 variant — price tests extreme, retreats | HIGH |

## MBO-exclusive signals (require Databento data)

These CANNOT be built on synthesized OHLCV. They go in `cross_market/features/`:

| Signal | MBO requirement |
|--------|----------------|
| Spoof by order ID | exchange_order_id lifecycle: ADD → no fill → CANCEL <5s |
| True iceberg | Refresh ADD events at same price after fills (order ID tracking) |
| Queue depletion rate | depth_order_priority tracking → time-to-fill estimation |
| Large order cancel wave | Multiple exchange_order_ids cancelled in <500ms |
| Layering detection | 3+ contiguous levels, few orders (coordinated), dissolves on approach |

For MBO signals, use the cross-market plan infrastructure:
- `cross_market/connectors/rithmic_mbo_connector.py` (live)
- `cross_market/replay/mbo_replay_engine.py` (Databento historical)
- `cross_market/book/mbo_order_book.py` (state management)
