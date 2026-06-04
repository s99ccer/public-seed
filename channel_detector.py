import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import requests
import json
from datetime import datetime, timedelta
from collections import defaultdict

# ---------- 1. Fetch OHLC from Bitstamp ----------
def fetch_ohlc(step=3600, limit=500):
    url = f"https://www.bitstamp.net/api/v2/ohlc/btcusd/"
    params = {"step": step, "limit": limit}
    r = requests.get(url, params=params, timeout=10)
    data = r.json()["data"]["ohlc"]
    ohlc = []
    for bar in data:
        ts = int(bar["timestamp"])
        ohlc.append({
            "time": datetime.utcfromtimestamp(ts),
            "open": float(bar["open"]),
            "high": float(bar["high"]),
            "low": float(bar["low"]),
            "close": float(bar["close"])
        })
    return ohlc

# ---------- 2. Swing Point (Zigzag) ----------
def zigzag(prices, pct=1.5):
    highs = np.array([p["high"] for p in prices])
    lows = np.array([p["low"] for p in prices])
    n = len(prices)
    pivots = []
    direction = 0
    last_pivot = 0
    ref = prices[0]
    for i in range(1, n):
        if direction >= 0:
            if prices[i]["high"] > prices[last_pivot]["high"]:
                last_pivot = i
            elif prices[i]["high"] <= prices[last_pivot]["high"] * (1 - pct / 100):
                pivots.append((last_pivot, prices[last_pivot]["high"], "high"))
                direction = -1
                last_pivot = i
        if direction <= 0:
            if prices[i]["low"] < prices[last_pivot]["low"]:
                last_pivot = i
            elif prices[i]["low"] >= prices[last_pivot]["low"] * (1 + pct / 100):
                pivots.append((last_pivot, prices[last_pivot]["low"], "low"))
                direction = 1
                last_pivot = i
    pivots.append((last_pivot, prices[last_pivot]["close"], "close"))
    return pivots

# ---------- 3. Parallel Channel Detection ----------
def detect_channels(data, min_touch=2, max_channels=5):
    pivots = zigzag(data, pct=2.5)
    highs = [p for p in pivots if p[2] == "high"]
    lows = [p for p in pivots if p[2] == "low"]
    idx = np.arange(len(data))
    closes = np.array([d["close"] for d in data])

    channels = []
    def slope_line(x, p1, p2):
        x1, y1 = p1
        x2, y2 = p2
        if x2 == x1: return None
        m = (y2 - y1) / (x2 - x1)
        b = y1 - m * x1
        return m, b

    def parallel_through(points_src, point_dst):
        x1, y1 = points_src[0]
        x2, y2 = points_src[1]
        if x2 == x1: return None
        m = (y2 - y1) / (x2 - x1)
        b = point_dst[1] - m * point_dst[0]
        return m, b

    def score_channel(data, m, b1, b2):
        inside = 0
        total = len(data)
        for i, d in enumerate(data):
            y = d["close"]
            line_val = m * i + b1
            line_val2 = m * i + b2
            lower = min(line_val, line_val2)
            upper = max(line_val, line_val2)
            if lower <= y <= upper:
                inside += 1
        return inside / total

    def count_touches(data, m, b, tol=0.008):
        touches = 0
        for i, d in enumerate(data):
            y = d["close"]
            pred = m * i + b
            if abs(y - pred) / y < tol:
                touches += 1
        return touches

    # Case 1: connect two pivot lows, parallel through highest high
    for i in range(len(lows)):
        for j in range(i + 2, len(lows)):
            p1 = (lows[i][0], lows[i][1])
            p2 = (lows[j][0], lows[j][1])
            seg = slope_line(idx, p1, p2)
            if seg is None: continue
            m, b1 = seg
            mid_highs = [h for h in highs if h[0] > p1[0] and h[0] < p2[0]]
            if not mid_highs: continue
            best_high = max(mid_highs, key=lambda h: h[1])
            parallel = parallel_through((p1, p2), (best_high[0], best_high[1]))
            if parallel is None: continue
            m_p, b2 = parallel
            b_low, b_high = (b1, b2) if b1 < b2 else (b2, b1)
            sc = score_channel(data, m, b_low, b_high)
            touches_low = count_touches(data, m, b1)
            touches_high = count_touches(data, m, b2)
            if touches_low >= min_touch and touches_high >= min_touch:
                channels.append({
                    "m": m, "b_low": b_low, "b_high": b_high,
                    "score": sc, "type": "bull", "p1": p1, "p2": p2, "p3": (best_high[0], best_high[1]),
                    "touches_low": touches_low, "touches_high": touches_high
                })

    # Case 2: connect two pivot highs, parallel through lowest low
    for i in range(len(highs)):
        for j in range(i + 2, len(highs)):
            p1 = (highs[i][0], highs[i][1])
            p2 = (highs[j][0], highs[j][1])
            seg = slope_line(idx, p1, p2)
            if seg is None: continue
            m, b1 = seg
            mid_lows = [l for l in lows if l[0] > p1[0] and l[0] < p2[0]]
            if not mid_lows: continue
            best_low = min(mid_lows, key=lambda l: l[1])
            parallel = parallel_through((p1, p2), (best_low[0], best_low[1]))
            if parallel is None: continue
            m_p, b2 = parallel
            b_low, b_high = (b1, b2) if b1 < b2 else (b2, b1)
            sc = score_channel(data, m, b_low, b_high)
            touches_high = count_touches(data, m, b1)
            touches_low = count_touches(data, m, b2)
            if touches_high >= min_touch and touches_low >= min_touch:
                channels.append({
                    "m": m, "b_low": b_low, "b_high": b_high,
                    "score": sc, "type": "bear", "p1": p1, "p2": p2, "p3": (best_low[0], best_low[1]),
                    "touches_low": touches_low, "touches_high": touches_high
                })

    # Sort by score then total touches
    channels.sort(key=lambda c: (c["score"], c["touches_low"] + c["touches_high"]), reverse=True)
    return channels[:max_channels]

# ---------- 4. Draw Chart ----------
def draw_channel(data, channel, ax, color="orange"):
    n = len(data)
    times = np.array([d["time"] for d in data])
    x_nums = mdates.date2num(times)
    m = channel["m"]
    idx_ext = np.array([0, n - 1])
    y_low = m * idx_ext + channel["b_low"]
    y_high = m * idx_ext + channel["b_high"]
    x_ext = np.array([x_nums[0], x_nums[-1]])
    ax.plot(x_ext, y_low, color=color, linewidth=1.5, linestyle="-")
    ax.plot(x_ext, y_high, color=color, linewidth=1.5, linestyle="-")
    ax.fill_between(x_ext, y_low, y_high, color=color, alpha=0.08)
    label = f"Channel ({channel['type']}) score={channel['score']:.0%}"
    if channel.get("p1"):
        label += f"\nP1(idx={channel['p1'][0]}), P3(idx={channel['p3'][0]})"
    return label

def plot_parallel_channels(data, channels, save_path=None):
    fig, ax = plt.subplots(figsize=(14, 7))
    times = np.array([d["time"] for d in data])
    closes = np.array([d["close"] for d in data])
    highs = np.array([d["high"] for d in data])
    lows = np.array([d["low"] for d in data])
    ax.plot(times, closes, color="black", linewidth=0.8, label="BTCUSD")
    ax.fill_between(times, lows, highs, color="gray", alpha=0.15)
    colors = ["orange", "purple", "cyan", "lime", "magenta"]
    for i, ch in enumerate(channels):
        label = draw_channel(data, ch, ax, color=colors[i % len(colors)])
        if ch.get("p1"):
            for pt in [ch["p1"], ch.get("p3")]:
                if pt:
                    ax.scatter(times[int(pt[0])], pt[1], color=colors[i % len(colors)], s=30, zorder=5)
    ax.legend(loc="best", fontsize=8)
    ax.set_title("BTCUSD - Parallel Channel Auto Detection", fontsize=14)
    ax.set_ylabel("Price (USD)")
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    fig.autofmt_xdate()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Saved to {save_path}")
    else:
        plt.show()
    plt.close()

# ---------- 5. Main ----------
if __name__ == "__main__":
    import sys
    step = 86400  # 일봉
    limit = 365
    if len(sys.argv) > 1:
        step = int(sys.argv[1])
    if len(sys.argv) > 2:
        limit = int(sys.argv[2])

    print(f"Fetching BTCUSD {step}s OHLC last {limit} bars...")
    data = fetch_ohlc(step=step, limit=limit)
    if not data:
        print("No data fetched")
        sys.exit(1)
    print(f"Got {len(data)} bars from {data[0]['time']} to {data[-1]['time']}")

    channels = detect_channels(data, min_touch=2, max_channels=4)
    print(f"\nDetected {len(channels)} channels:")
    for i, ch in enumerate(channels):
        print(f"  #{i+1}: {ch['type']} | slope={ch['m']:.4f} | score={ch['score']:.0%} | touches_L={ch['touches_low']} H={ch['touches_high']}")

    outpath = r"C:\test\btc_parallel_channel.png"
    plot_parallel_channels(data, channels, save_path=outpath)
    print(f"\nChart saved. Open: start {outpath}")
