import configparser
import json
import logging
import os
import queue
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pymysql

logging.Formatter.converter = time.gmtime
logging.basicConfig(level=logging.INFO, format="%(asctime)sZ %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("shop")

CFG = configparser.ConfigParser()
CFG.read(os.environ.get("SHOP_CONFIG", "/etc/shop/shop.ini"))
FEATURES = CFG["features"]


def connect():
    return pymysql.connect(
        host=CFG["db"]["host"],
        user=CFG["db"]["user"],
        password=os.environ["DB_PASSWORD"],
        database=CFG["db"]["name"],
        connect_timeout=3,
        read_timeout=10,
        write_timeout=10,
        autocommit=False,
    )


class Pool:
    def __init__(self, size):
        self.size = size
        self.idle = queue.LifoQueue()
        self.in_use = set()
        self.lock = threading.Lock()

    def get(self):
        try:
            conn = self.idle.get_nowait()
            conn.ping(reconnect=True)
        except queue.Empty:
            conn = connect()
        with self.lock:
            self.in_use.add(conn)
        return conn

    def put(self, conn):
        with self.lock:
            self.in_use.discard(conn)
        try:
            conn.rollback()
        except pymysql.MySQLError:
            conn.close()
            return
        if self.idle.qsize() < self.size:
            self.idle.put(conn)
        else:
            conn.close()

    def stats(self):
        with self.lock:
            return len(self.in_use), self.idle.qsize()


POOL = Pool(CFG.getint("db", "pool_size"))
STATS = {}
STATS_LOCK = threading.Lock()


class Rejected(Exception):
    def __init__(self, status, reason):
        super().__init__(reason)
        self.status = status
        self.reason = reason


def validate(cur, sku, qty, coupon):
    """Returns (total, None) or (None, (status, body)) for business-level rejections."""
    cur.execute("SELECT price, stock FROM products WHERE sku=%s FOR UPDATE", (sku,))
    row = cur.fetchone()
    if row is None:
        raise Rejected(404, "unknown sku")
    price, stock = row
    if stock < qty:
        raise Rejected(409, "out of stock")
    discount = 0
    if coupon:
        cur.execute("SELECT discount FROM coupons WHERE code=%s AND active=1", (coupon,))
        found = cur.fetchone()
        if found is None:
            return None, (400, {"error": "invalid coupon"})
        discount = found[0]
    return price * qty * (100 - discount) // 100, None


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def reply(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        with STATS_LOCK:
            STATS[status] = STATS.get(status, 0) + 1
        if status >= 500:
            log.error("%s %s -> %d %s", self.command, self.path, status, body)

    def read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        if self.path == "/healthz":
            return self.reply(200, {"status": "ok"})
        if self.path == "/ready":
            return self.ready()
        if self.path == "/products":
            return self.products()
        if self.path == "/metrics":
            return self.metrics()
        self.reply(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/checkout":
            return self.checkout()
        self.reply(404, {"error": "not found"})

    def ready(self):
        try:
            conn = connect()
            conn.cursor().execute("SELECT 1")
            conn.close()
        except pymysql.MySQLError as e:
            log.warning("readiness: db check failed: %s", e)
            return self.reply(503, {"db": str(e)})
        self.reply(200, {"db": "ok"})

    def products(self):
        try:
            conn = POOL.get()
        except pymysql.MySQLError as e:
            return self.reply(500, {"error": str(e)})
        try:
            cur = conn.cursor()
            cur.execute("SELECT sku, name, price, stock FROM products ORDER BY sku")
            rows = [dict(zip(("sku", "name", "price", "stock"), r)) for r in cur.fetchall()]
        except pymysql.MySQLError as e:
            return self.reply(500, {"error": str(e)})
        finally:
            POOL.put(conn)
        self.reply(200, rows)

    def metrics(self):
        in_use, idle = POOL.stats()
        lines = [f"shop_pool_in_use {in_use}", f"shop_pool_idle {idle}"]
        with STATS_LOCK:
            lines += [f'shop_responses_total{{code="{k}"}} {v}' for k, v in sorted(STATS.items())]
        data = ("\n".join(lines) + "\n").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def checkout(self):
        if not FEATURES.getboolean("checkout_enabled", fallback=False):
            return self.reply(503, {"error": "checkout disabled"})
        try:
            order = self.read_json()
            sku, qty, coupon = str(order["sku"]), int(order.get("qty", 1)), order.get("coupon")
        except (ValueError, KeyError, TypeError):
            return self.reply(400, {"error": "bad request"})
        try:
            conn = POOL.get()
        except pymysql.MySQLError as e:
            return self.reply(500, {"error": str(e)})
        try:
            cur = conn.cursor()
            total, problem = validate(cur, sku, qty, coupon)
            if problem:
                conn.rollback()
                log.info("checkout rejected: sku=%s qty=%s coupon=%s -> %s", sku, qty, coupon, problem[1]["error"])
                return self.reply(*problem)
            cur.execute("UPDATE products SET stock = stock - %s WHERE sku=%s", (qty, sku))
            cur.execute("INSERT INTO orders (sku, qty, coupon, total) VALUES (%s, %s, %s, %s)",
                        (sku, qty, coupon, total))
            conn.commit()
            order_id = cur.lastrowid
        except Rejected as e:
            POOL.put(conn)
            return self.reply(e.status, {"error": e.reason})
        except pymysql.MySQLError as e:
            POOL.put(conn)
            return self.reply(500, {"error": str(e)})
        POOL.put(conn)
        self.reply(201, {"order_id": order_id, "total": total})


def telemetry():
    target = os.environ.get("OTEL_ENDPOINT", "otel-collector.observability.svc.cluster.local:4317")
    host, port = target.rsplit(":", 1)
    while True:
        try:
            socket.create_connection((host, int(port)), timeout=2).close()
        except OSError as e:
            log.error("telemetry: export failed to %s: %s (spans dropped: %d)", target, e, 512)
        time.sleep(20)


if __name__ == "__main__":
    threading.Thread(target=telemetry, daemon=True).start()
    port = CFG.getint("server", "port")
    log.info("shop starting on :%d, checkout_enabled=%s", port, FEATURES.get("checkout_enabled"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
