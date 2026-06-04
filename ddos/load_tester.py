"""
HTTP Load Testing Tool
- Max bandwidth: 100 MB/s
- Protocol: HTTP/HTTPS
- Engine: asyncio + aiohttp
"""

import asyncio
import aiohttp
import time
import argparse
import sys
from dataclasses import dataclass, field
from collections import deque


MAX_BANDWIDTH_BYTES = 100 * 1024 * 1024  # 100 MB/s hard limit


@dataclass
class Stats:
    total_requests: int = 0
    success: int = 0
    failed: int = 0
    total_bytes_sent: int = 0
    total_bytes_recv: int = 0
    latencies: deque = field(default_factory=lambda: deque(maxlen=10000))
    start_time: float = field(default_factory=time.time)

    def rps(self) -> float:
        elapsed = time.time() - self.start_time
        return self.total_requests / elapsed if elapsed > 0 else 0

    def avg_latency_ms(self) -> float:
        return (sum(self.latencies) / len(self.latencies) * 1000) if self.latencies else 0

    def bandwidth_mbps(self) -> float:
        elapsed = time.time() - self.start_time
        total = self.total_bytes_sent + self.total_bytes_recv
        return (total / elapsed / 1024 / 1024) if elapsed > 0 else 0


class BandwidthLimiter:
    """Token bucket: enforces max bytes/sec across all workers."""

    def __init__(self, max_bytes_per_sec: int):
        self.max_bytes = max_bytes_per_sec
        self.tokens = float(max_bytes_per_sec)
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, bytes_needed: int):
        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self.last_refill
                self.tokens = min(self.max_bytes, self.tokens + elapsed * self.max_bytes)
                self.last_refill = now

                if self.tokens >= bytes_needed:
                    self.tokens -= bytes_needed
                    return

            await asyncio.sleep(0.005)


async def worker(
    session: aiohttp.ClientSession,
    url: str,
    method: str,
    headers: dict,
    body: bytes | None,
    stats: Stats,
    limiter: BandwidthLimiter,
    stop_event: asyncio.Event,
):
    while not stop_event.is_set():
        request_size = len(url.encode()) + sum(len(k) + len(v) for k, v in headers.items())
        if body:
            request_size += len(body)

        await limiter.acquire(request_size)

        t0 = time.monotonic()
        try:
            async with session.request(
                method, url, headers=headers, data=body, ssl=False
            ) as resp:
                response_body = await resp.read()
                latency = time.monotonic() - t0

                stats.total_requests += 1
                stats.success += 1
                stats.total_bytes_sent += request_size
                stats.total_bytes_recv += len(response_body)
                stats.latencies.append(latency)

        except Exception:
            stats.total_requests += 1
            stats.failed += 1


async def print_stats(stats: Stats, stop_event: asyncio.Event, interval: float = 1.0):
    while not stop_event.is_set():
        await asyncio.sleep(interval)
        elapsed = time.time() - stats.start_time
        print(
            f"\r[{elapsed:6.1f}s] "
            f"RPS: {stats.rps():7.1f}  "
            f"OK: {stats.success:8d}  "
            f"Fail: {stats.failed:6d}  "
            f"Avg latency: {stats.avg_latency_ms():6.1f}ms  "
            f"BW: {stats.bandwidth_mbps():.2f} MB/s",
            end="",
            flush=True,
        )


async def run(
    url: str,
    concurrency: int,
    duration: float,
    method: str,
    headers: dict,
    body: bytes | None,
    max_bandwidth: int,
):
    stats = Stats()
    limiter = BandwidthLimiter(max_bandwidth)
    stop_event = asyncio.Event()

    connector = aiohttp.TCPConnector(limit=concurrency, ssl=False)
    timeout = aiohttp.ClientTimeout(total=30, connect=10)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        workers = [
            asyncio.create_task(
                worker(session, url, method, headers, body, stats, limiter, stop_event)
            )
            for _ in range(concurrency)
        ]
        stats_task = asyncio.create_task(print_stats(stats, stop_event))

        await asyncio.sleep(duration)
        stop_event.set()

        await asyncio.gather(*workers, return_exceptions=True)
        stats_task.cancel()

    elapsed = time.time() - stats.start_time
    print("\n\n--- Results ---")
    print(f"Duration       : {elapsed:.2f}s")
    print(f"Total requests : {stats.total_requests}")
    print(f"Success        : {stats.success}")
    print(f"Failed         : {stats.failed}")
    print(f"RPS            : {stats.rps():.2f}")
    print(f"Avg latency    : {stats.avg_latency_ms():.2f} ms")
    print(f"Bytes sent     : {stats.total_bytes_sent / 1024 / 1024:.2f} MB")
    print(f"Bytes recv     : {stats.total_bytes_recv / 1024 / 1024:.2f} MB")
    print(f"Avg bandwidth  : {stats.bandwidth_mbps():.2f} MB/s")


def parse_header(value: str) -> tuple[str, str]:
    k, _, v = value.partition(":")
    return k.strip(), v.strip()


def main():
    parser = argparse.ArgumentParser(description="HTTP Load Tester (max 100 MB/s)")
    parser.add_argument("url", help="Target URL (e.g. http://localhost:8080/api)")
    parser.add_argument("-c", "--concurrency", type=int, default=50, help="Concurrent workers (default: 50)")
    parser.add_argument("-d", "--duration", type=float, default=30.0, help="Test duration in seconds (default: 30)")
    parser.add_argument("-m", "--method", default="GET", choices=["GET", "POST", "PUT", "DELETE", "HEAD"], help="HTTP method (default: GET)")
    parser.add_argument("-H", "--header", action="append", default=[], metavar="Key: Value", help="Custom header (repeatable)")
    parser.add_argument("-b", "--body", default=None, help="Request body string (for POST/PUT)")
    parser.add_argument("--body-file", default=None, help="Request body from file")
    parser.add_argument(
        "--max-bw",
        type=int,
        default=100,
        help="Max bandwidth in MB/s (default: 100, max: 100)",
    )
    args = parser.parse_args()

    max_bw_mb = min(args.max_bw, 100)  # hard cap at 100 MB/s
    max_bw_bytes = max_bw_mb * 1024 * 1024

    headers = dict(parse_header(h) for h in args.header)
    headers.setdefault("User-Agent", "LoadTester/1.0")

    body: bytes | None = None
    if args.body_file:
        with open(args.body_file, "rb") as f:
            body = f.read()
    elif args.body:
        body = args.body.encode()

    print(f"Target     : {args.url}")
    print(f"Method     : {args.method}")
    print(f"Concurrency: {args.concurrency}")
    print(f"Duration   : {args.duration}s")
    print(f"Max BW     : {max_bw_mb} MB/s")
    print()

    try:
        asyncio.run(
            run(
                url=args.url,
                concurrency=args.concurrency,
                duration=args.duration,
                method=args.method,
                headers=headers,
                body=body,
                max_bandwidth=max_bw_bytes,
            )
        )
    except KeyboardInterrupt:
        print("\nStopped by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
