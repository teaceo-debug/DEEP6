"""Kronos subprocess worker for E10 bias engine.

This module runs inside a dedicated subprocess. The main asyncio event loop
communicates with it via multiprocessing.Pipe. PyTorch inference (200-400ms on
M2 Mac MPS) never blocks the main event loop.

Architecture:
  main process  ←→  multiprocessing.Pipe  ←→  KronosWorkerProcess (subprocess)
                                                   └─ run_kronos_worker()
                                                       └─ Kronos-small model

Pipe protocol:
  REQUEST:  {"type": "ping"}
  RESPONSE: {"type": "pong"}

  REQUEST:  {"type": "infer", "ohlcv": list[dict], "num_samples": int}
  RESPONSE: KronosBias dataclass (pickled through pipe)

  REQUEST:  {"type": "shutdown"}
  RESPONSE: (none — subprocess exits)

Per KRON-01..06, ARCH-02 (subprocess isolation), T-06-01 (recv timeout).
"""
from __future__ import annotations

import sys
import time
from multiprocessing import Process, Pipe
from multiprocessing.connection import Connection
from typing import Optional

import numpy as np
import pandas as pd

# torch is imported lazily inside _select_device / _load_model so that
# importing this module doesn't require PyTorch in the main process.


def _select_device(requested: str) -> str:
    """Select inference device.

    If requested == "auto", probe mps → cuda → cpu.
    Otherwise return the requested device as-is.

    Logs selected device to stderr (visible in subprocess output).
    """
    if requested != "auto":
        return requested

    try:
        import torch
        if torch.backends.mps.is_available():
            print("KronosWorker: selected device=mps", file=sys.stderr, flush=True)
            return "mps"
        if torch.cuda.is_available():
            print("KronosWorker: selected device=cuda", file=sys.stderr, flush=True)
            return "cuda"
    except ImportError:
        pass

    print("KronosWorker: selected device=cpu (fallback)", file=sys.stderr, flush=True)
    return "cpu"


def _load_model(cfg) -> tuple:
    """Load Kronos-small from HuggingFace Hub.

    Args:
        cfg: KronosConfig instance.

    Returns:
        (model, tokenizer, predictor) if successful; (None, None, None) on ImportError.
    """
    device = _select_device(cfg.device)
    try:
        from model import Kronos, KronosTokenizer, KronosPredictor  # type: ignore

        tokenizer = KronosTokenizer.from_pretrained(cfg.tokenizer_name)
        model = Kronos.from_pretrained(cfg.model_name)
        if device != "cpu":
            model = model.to(device)
        predictor = KronosPredictor(model, tokenizer, max_context=512)
        print(
            f"KronosWorker: model loaded ({cfg.model_name}) on {device}",
            file=sys.stderr, flush=True
        )
        return model, tokenizer, predictor
    except ImportError:
        print(
            "KronosWorker: Kronos model not installed — will use fallback momentum bias.",
            file=sys.stderr, flush=True
        )
        return None, None, None
    except Exception as exc:
        print(f"KronosWorker: model load failed — {exc}", file=sys.stderr, flush=True)
        return None, None, None


def _run_stochastic_inference(predictor, ohlcv: list[dict], cfg) -> "KronosBias":
    """Run Kronos stochastic inference, returning a KronosBias result.

    Mirrors KronosEngine._run_inference() exactly so behaviour is identical
    to the legacy synchronous path.

    Args:
        predictor: KronosPredictor instance (not None).
        ohlcv:     List of bar dicts with keys open/high/low/close/volume.
        cfg:       KronosConfig instance.

    Returns:
        KronosBias with direction, confidence, and timing.
    """
    # Import here — this runs inside the subprocess
    from deep6.engines.kronos_bias import KronosBias  # type: ignore

    df = pd.DataFrame(ohlcv[-cfg.lookback:])
    current_close = float(df.iloc[-1]["close"])

    t0 = time.perf_counter()

    predictions = []
    for _ in range(cfg.num_samples):
        try:
            pred = predictor.predict(
                df=df[["open", "high", "low", "close", "volume"]],
                x_timestamp=pd.Series(range(len(df))),
                y_timestamp=pd.Series(range(len(df), len(df) + cfg.pred_len)),
                T=1.0, top_p=0.9,
            )
            if pred is not None and len(pred) > 0:
                predictions.append(float(pred.iloc[-1]["close"]))
        except Exception:
            continue

    elapsed_ms = (time.perf_counter() - t0) * 1000

    if not predictions:
        return _fallback_bias(ohlcv)

    mean_close = float(np.mean(predictions))
    std_close = float(np.std(predictions))
    delta = mean_close - current_close

    direction = +1 if delta > 0 else -1 if delta < 0 else 0

    if abs(delta) > 0:
        uncertainty = std_close / abs(delta)
        confidence = max(0.0, min(100.0, (1.0 - uncertainty) * 100.0))
    else:
        confidence = 0.0

    return KronosBias(
        direction=direction,
        confidence=confidence,
        predicted_close=mean_close,
        current_close=current_close,
        samples=len(predictions),
        inference_time_ms=elapsed_ms,
        bars_since_inference=0,
        detail=(
            f"KRONOS: {'BULL' if direction > 0 else 'BEAR'} bias "
            f"conf={confidence:.0f}% pred={mean_close:.2f} "
            f"({elapsed_ms:.0f}ms, {len(predictions)} samples)"
        ),
    )


def _fallback_bias(ohlcv: list[dict]) -> "KronosBias":
    """Simple momentum fallback when Kronos model is unavailable.

    Copies KronosEngine._fallback_bias() logic. Returns direction 0 and
    confidence capped at 50 — indicates uncertainty, not conviction.

    Args:
        ohlcv: List of bar dicts. Fewer than 10 bars → direction=0, confidence=0.
    """
    from deep6.engines.kronos_bias import KronosBias  # type: ignore

    if len(ohlcv) < 10:
        return KronosBias(
            direction=0, confidence=0, predicted_close=0, current_close=0,
            samples=0, inference_time_ms=0, bars_since_inference=0,
            detail="KRONOS: fallback — insufficient data (need 10+ bars)",
        )

    closes = [b["close"] for b in ohlcv[-10:]]
    slope = float(np.polyfit(range(len(closes)), closes, 1)[0])
    current = float(closes[-1])
    direction = +1 if slope > 0 else -1 if slope < 0 else 0
    confidence = min(abs(slope) / 2.0 * 100.0, 50.0)  # Cap at 50 for fallback

    return KronosBias(
        direction=direction,
        confidence=confidence,
        predicted_close=current + slope * 5,
        current_close=current,
        samples=0,
        inference_time_ms=0,
        bars_since_inference=0,
        detail=(
            f"KRONOS FALLBACK: momentum {'BULL' if direction > 0 else 'BEAR'} "
            f"slope={slope:.2f} conf={confidence:.0f}%"
        ),
    )


def run_kronos_worker(conn: Connection, cfg) -> None:
    """Main subprocess entry point. Loaded once; serves inference requests forever.

    Pipe protocol loop:
      recv request dict → process → send result
      {"type": "shutdown"} breaks the loop.

    All exceptions are caught so a single bad request never crashes the worker.

    Args:
        conn: Child end of multiprocessing.Pipe.
        cfg:  KronosConfig instance (pickled by multiprocessing).
    """
    _model, _tokenizer, predictor = _load_model(cfg)

    while True:
        try:
            request = conn.recv()
        except EOFError:
            # Parent closed the pipe — exit cleanly
            break
        except Exception as exc:
            print(f"KronosWorker: recv error — {exc}", file=sys.stderr, flush=True)
            break

        try:
            req_type = request.get("type") if isinstance(request, dict) else None

            if req_type == "ping":
                conn.send({"type": "pong"})

            elif req_type == "infer":
                ohlcv = request.get("ohlcv", [])
                num_samples = request.get("num_samples", cfg.num_samples)

                if predictor is not None:
                    # Temporarily override num_samples via a local cfg clone
                    from dataclasses import replace as dc_replace
                    run_cfg = dc_replace(cfg, num_samples=num_samples)
                    bias = _run_stochastic_inference(predictor, ohlcv, run_cfg)
                else:
                    bias = _fallback_bias(ohlcv)

                conn.send(bias)

            elif req_type == "shutdown":
                break

            else:
                # Unknown request type — send error dict and continue
                conn.send({"type": "error", "message": f"unknown request type: {req_type!r}"})

        except Exception as exc:
            print(f"KronosWorker: request processing error — {exc}", file=sys.stderr, flush=True)
            try:
                conn.send({"type": "error", "message": str(exc)})
            except Exception:
                pass

    conn.close()


class KronosWorkerProcess:
    """Manages the lifecycle of the Kronos inference subprocess.

    Usage:
        worker = KronosWorkerProcess(KronosConfig())
        worker.start()
        bias = worker.request_inference(ohlcv_list, num_samples=20)
        worker.stop()

    The subprocess loads Kronos-small once at startup and serves all subsequent
    inference requests without reloading. Communication is via multiprocessing.Pipe.

    Per T-06-01: request_inference has a 5-second timeout; stop() terminates
    the subprocess if it doesn't exit within 5 seconds.
    """

    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self._process: Optional[Process] = None
        self._conn: Optional[Connection] = None

    def start(self) -> None:
        """Start the Kronos worker subprocess.

        Creates a bidirectional Pipe and spawns the subprocess.
        Must be called before ping() or request_inference().
        """
        parent_conn, child_conn = Pipe(duplex=True)
        self._conn = parent_conn
        self._process = Process(
            target=run_kronos_worker,
            args=(child_conn, self.cfg),
            daemon=True,
        )
        self._process.start()
        # Close child end in parent process (only subprocess should hold it)
        child_conn.close()

    def stop(self) -> None:
        """Cleanly shut down the worker subprocess.

        Sends shutdown sentinel, waits up to 5 seconds, then terminates if needed.
        """
        if self._conn is not None:
            try:
                self._conn.send({"type": "shutdown"})
            except Exception:
                pass

        if self._process is not None:
            self._process.join(timeout=5)
            if self._process.is_alive():
                self._process.terminate()
                self._process.join(timeout=2)

    def ping(self) -> bool:
        """Check subprocess health. Returns True if subprocess responds with pong.

        Returns False on timeout or communication error.
        Does NOT require the Kronos model to be loaded.
        """
        if self._conn is None:
            return False
        try:
            self._conn.send({"type": "ping"})
            if self._conn.poll(timeout=2.0):
                response = self._conn.recv()
                return isinstance(response, dict) and response.get("type") == "pong"
            return False
        except Exception:
            return False

    def request_inference(self, ohlcv: list[dict], num_samples: int) -> "KronosBias":
        """Request Kronos inference from the subprocess.

        Sends ohlcv data to the subprocess and waits for a KronosBias response.
        This is a blocking call — wrap in loop.run_in_executor() for async use.

        Args:
            ohlcv:       List of bar dicts (open/high/low/close/volume).
            num_samples: Number of stochastic samples to generate.

        Returns:
            KronosBias dataclass with direction, confidence, and timing.

        Raises:
            TimeoutError: If subprocess does not respond within 5 seconds.
        """
        if self._conn is None:
            raise RuntimeError("KronosWorkerProcess not started — call start() first")

        self._conn.send({"type": "infer", "ohlcv": ohlcv, "num_samples": num_samples})

        if self._conn.poll(timeout=5.0):
            return self._conn.recv()

        raise TimeoutError(
            "KronosWorkerProcess did not respond within 5 seconds. "
            "Subprocess may be overloaded or crashed."
        )
