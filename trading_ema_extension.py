"""4H EMA signal extension for breakout scanners.

This module is intentionally additive: it does not alter existing breakout
logic and can be called from both live-scan and backtest flows.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

import pandas as pd


EMA_EVENTS_CSV = "ema_4h_signals.csv"


@dataclass
class EmaSignal:
    symbol: str
    event: str
    date: pd.Timestamp
    close: float
    ema10: float
    ema50: float
    ema200: float

    def to_record(self) -> dict:
        record = asdict(self)
        record["date"] = pd.Timestamp(record["date"])
        return record


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = out.columns.str.strip().str.lower()
    return out


def ensure_datetime_column(df: pd.DataFrame) -> pd.DataFrame:
    out = normalize_columns(df)
    if isinstance(out.index, pd.DatetimeIndex):
        out = out.reset_index()

    for candidate in ["date", "datetime", "timestamp", "time", "index"]:
        if candidate in out.columns:
            out["date"] = pd.to_datetime(out[candidate], errors="coerce")
            if candidate != "date":
                out = out.drop(columns=[candidate], errors="ignore")
            break
    else:
        raise ValueError("No valid datetime column found for EMA scan.")

    out = out.dropna(subset=["date"]).drop_duplicates(subset=["date"])
    out = out.sort_values(by="date", kind="mergesort")
    return out


def resample_4h(df: pd.DataFrame) -> pd.DataFrame:
    out = ensure_datetime_column(df)
    required_cols = ["open", "high", "low", "close", "volume"]
    missing = [c for c in required_cols if c not in out.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    out = out.set_index("date")
    out = out.resample("4h").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )
    return out.dropna().reset_index()


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def evaluate_4h_ema_signals(df_raw: pd.DataFrame, symbol: str) -> list[EmaSignal]:
    """Detect 4H EMA events required by the scanner.

    Events:
    - CROSS_10_50: first close above EMA10 and EMA50 (golden continuation gate).
    - CLOSE_ABOVE_50: latest candle newly closes above EMA50.
    - CROSS_200_AFTER_10_50: after staying above EMA10/EMA50, close crosses EMA200.
    """

    df_4h = resample_4h(df_raw)
    if len(df_4h) < 220:
        return []

    df_4h["ema10"] = _ema(df_4h["close"], 10)
    df_4h["ema50"] = _ema(df_4h["close"], 50)
    df_4h["ema200"] = _ema(df_4h["close"], 200)

    # Keep rows with all EMA values populated.
    df_4h = df_4h.dropna(subset=["ema10", "ema50", "ema200"]).copy()
    if len(df_4h) < 3:
        return []

    prev_row = df_4h.iloc[-2]
    row = df_4h.iloc[-1]

    signals: list[EmaSignal] = []

    cross_10_50 = (
        (prev_row["close"] <= prev_row["ema10"] or prev_row["close"] <= prev_row["ema50"])
        and (row["close"] > row["ema10"])
        and (row["close"] > row["ema50"])
    )
    if cross_10_50:
        signals.append(
            EmaSignal(symbol, "CROSS_10_50", row["date"], row["close"], row["ema10"], row["ema50"], row["ema200"])
        )

    close_above_50 = (prev_row["close"] <= prev_row["ema50"]) and (row["close"] > row["ema50"])
    if close_above_50:
        signals.append(
            EmaSignal(symbol, "CLOSE_ABOVE_50", row["date"], row["close"], row["ema10"], row["ema50"], row["ema200"])
        )

    # Condition: price has already spent >=2 candles above EMA10 and EMA50, then breaks EMA200 now.
    above_10_50 = (df_4h["close"] > df_4h["ema10"]) & (df_4h["close"] > df_4h["ema50"])
    recent_above_count = int(above_10_50.iloc[-4:-1].sum())
    cross_200_now = (prev_row["close"] <= prev_row["ema200"]) and (row["close"] > row["ema200"])
    if recent_above_count >= 2 and cross_200_now:
        signals.append(
            EmaSignal(symbol, "CROSS_200_AFTER_10_50", row["date"], row["close"], row["ema10"], row["ema50"], row["ema200"])
        )

    return signals


def append_ema_events(signals: Iterable[EmaSignal], output_file: str = EMA_EVENTS_CSV) -> int:
    rows = [s.to_record() for s in signals]
    if not rows:
        return 0

    path = Path(output_file)
    df = pd.DataFrame(rows)

    if path.exists():
        existing = pd.read_csv(path)
        combined = pd.concat([existing, df], ignore_index=True)
        combined = combined.drop_duplicates(subset=["symbol", "event", "date"], keep="last")
    else:
        combined = df

    combined = combined.sort_values(["date", "symbol", "event"], ascending=[False, True, True])
    combined.to_csv(path, index=False)
    return len(rows)


def format_telegram_message(signals: Iterable[EmaSignal]) -> str:
    rows = list(signals)
    if not rows:
        return ""

    lines = ["📊 4H EMA SIGNALS"]
    for s in rows:
        lines.append(
            f"{s.symbol} | {s.event} | Close={s.close:.2f} | EMA10={s.ema10:.2f} | EMA50={s.ema50:.2f} | EMA200={s.ema200:.2f}"
        )
    return "\n".join(lines)
