import concurrent.futures
import statistics
import time
import urllib.request

def bench(url, n, workers):
    def one(_):
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                r.read()
        except Exception:
            return None
        return (time.perf_counter() - t0) * 1000
    with concurrent.futures.ThreadPoolExecutor(workers) as ex:
        lat = [x for x in ex.map(one, range(n)) if x is not None]
    lat.sort()
    q = lambda p: lat[min(len(lat)-1, int(len(lat)*p))]
    return q(0.50), q(0.95), q(0.99)

ED = "http://127.0.0.1:8080"
AP = "http://127.0.0.1:18800"   # port-forward straight to app svc (no edge)
print(f"{'target':34} {'workers':>7} {'p50':>7} {'p95':>7} {'p99':>7} (ms)")
for w in (1, 16, 32):
    for name, base in (("products (full path, DB)", ED), ("healthz (edge+app, no DB)", ED),
                       ("products direct to app (no edge)", AP), ("healthz direct to app", AP)):
        p50, p95, p99 = bench(base + ("/products" if "products" in name else "/healthz"), 150, w)
        print(f"{name:34} {w:>7} {p50:>7.1f} {p95:>7.1f} {p99:>7.1f}")
