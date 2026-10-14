#!/usr/bin/env python3
"""Synthetic shop traffic. Usage: tools/load.py [--url URL] [--rps N] [--duration SEC]"""
import argparse
import collections
import json
import random
import threading
import time
import urllib.error
import urllib.request

SKUS = ["SKU-9538", "SKU-5348", "SKU-7418", "SKU-8720", "SKU-2883", "SKU-4167", "SKU-6100", "SKU-7385"]
SOLD_OUT = "SKU-9239"
COUPONS = ["WELCOME10", "FALL15"]
EXPIRED = "JULY20"


def pick(rng):
    r = rng.random()
    if r < 0.60:
        return "GET", "/products", None
    if r < 0.90:
        body = {"sku": rng.choice(SKUS), "qty": rng.randint(1, 3)}
        if rng.random() < 0.3:
            body["coupon"] = rng.choice(COUPONS)
        return "POST", "/checkout", body
    if r < 0.94:
        return "POST", "/checkout", {"sku": f"SKU-{rng.randint(90000, 99999)}", "qty": 1}
    if r < 0.97:
        return "POST", "/checkout", {"sku": SOLD_OUT, "qty": 1}
    return "POST", "/checkout", {"sku": rng.choice(SKUS), "qty": 1, "coupon": EXPIRED}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8080")
    ap.add_argument("--rps", type=float, default=15)
    ap.add_argument("--duration", type=int, default=120)
    ap.add_argument("--workers", type=int, default=32)
    args = ap.parse_args()

    stats = collections.Counter()
    window = collections.Counter()
    lat = []
    lock = threading.Lock()
    deadline = time.time() + args.duration
    interval = args.workers / args.rps

    def worker(seed):
        rng = random.Random(seed)
        time.sleep(rng.random() * interval)
        while time.time() < deadline:
            started = time.time()
            method, path, body = pick(rng)
            data = json.dumps(body).encode() if body is not None else None
            req = urllib.request.Request(args.url + path, data=data, method=method,
                                         headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    code = resp.status
            except urllib.error.HTTPError as e:
                code = e.code
            except Exception as e:
                code = type(e).__name__
            took = time.time() - started
            with lock:
                stats[code] += 1
                window[code] += 1
                lat.append(took)
            time.sleep(max(0.0, interval - took))

    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(args.workers)]
    for t in threads:
        t.start()
    while time.time() < deadline:
        time.sleep(5)
        with lock:
            snap = dict(window)
            window.clear()
            recent = sorted(lat[-200:])
        p99 = recent[int(len(recent) * 0.99) - 1] if recent else 0
        print(time.strftime("%H:%M:%S"), " ".join(f"{k}={v}" for k, v in sorted(snap.items(), key=str)),
              f"p99={p99:.2f}s", flush=True)
    for t in threads:
        t.join(timeout=25)
    print("total:", dict(stats))
    bad = sum(v for k, v in stats.items() if not isinstance(k, int) or k >= 500)
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
