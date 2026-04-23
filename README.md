# :earth_americas: GDP dashboard template

A simple Streamlit app showing the GDP of different countries in the world.

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://gdp-dashboard-template.streamlit.app/)

### How to run it on your own machine

1. Install the requirements

   ```
   $ pip install -r requirements.txt
   ```

2. Run the app

   ```
   $ streamlit run streamlit_app.py
   ```

## 4H EMA scanner extension (additive)

This repo now includes `trading_ema_extension.py`, a drop-in module for the trading script you shared.
It adds 4-hour EMA checks without changing your existing breakout/portfolio logic:

- EMA10 / EMA50 cross detection (`CROSS_10_50`)
- Last-candle close above EMA50 (`CLOSE_ABOVE_50`)
- EMA200 breakout after candles already stayed above EMA10+EMA50 (`CROSS_200_AFTER_10_50`)

### Integration points in your scanner/backtest loop

```python
from trading_ema_extension import evaluate_4h_ema_signals, append_ema_events, format_telegram_message

# Inside per-symbol loop (live and backtest):
ema_signals = evaluate_4h_ema_signals(df_raw, symbol)
if ema_signals:
    append_ema_events(ema_signals, "ema_4h_signals.csv")
    print(format_telegram_message(ema_signals))
    send_telegram_message(format_telegram_message(ema_signals))
```

The CSV deduplicates by `symbol + event + date`, so the same event is not repeatedly stored.
