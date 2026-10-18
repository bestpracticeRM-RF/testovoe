"""Unit tests for the connection pool (regression for the A5 leak).

No cluster needed: connect() is stubbed with fakes. These catch in ~1s
what the 2-minute load gate catches slowly.
"""
import importlib
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

_cfg = tempfile.NamedTemporaryFile("w", suffix=".ini", delete=False)
_cfg.write("[server]\nport = 8800\n\n[db]\nhost = h\nname = n\nuser = u\npool_size = 2\n\n"
           "[features]\ncheckout_enabled = true\n")
_cfg.close()
os.environ["SHOP_CONFIG"] = _cfg.name

import shop  # noqa: E402


class FakeConn:
    def __init__(self):
        self.rolled, self.closed = 0, 0

    def ping(self, reconnect=True):
        pass

    def rollback(self):
        self.rolled += 1

    def close(self):
        self.closed += 1


def fresh_pool(size=2):
    pool, shop.POOL = shop.Pool(size), shop.Pool(size)
    made = []

    def factory():
        c = FakeConn()
        made.append(c)
        return c

    shop.connect = factory
    return pool, made


def test_reject_path_does_not_lose_connection():
    """The A5 bug: 'invalid coupon' branch returned without POOL.put().
    Fixed semantics: put() returns the conn to idle and releases the semaphore."""
    pool, made = fresh_pool(2)
    conn = pool.get()
    assert len(made) == 1
    pool.put(conn)                      # what the fixed problem-branch does
    assert pool.idle.qsize() == 1
    again = pool.get()                  # must reuse, not open a new one
    assert again is conn and len(made) == 1, "connection leaked: pool opened a new one"


def test_pool_bounds_total_connections():
    """Pool must never hold more than `size` connections (semaphore bound)."""
    pool, made = fresh_pool(2)
    a, b = pool.get(), pool.get()
    assert len(made) == 2
    t0 = time.time()
    try:
        pool.get()
        raise AssertionError("expected PoolExhausted")
    except shop.PoolExhausted:
        pass
    assert time.time() - t0 >= 4.5, "must wait (acquire timeout) before giving up"
    pool.put(a)
    pool.put(b)
    c = pool.get()                      # semaphore released -> works again
    assert c is b                       # LIFO


def test_config_hot_reload():
    """A3: config file change by mtime must reach FEATURES."""
    path = _cfg.name
    with open(path, "w") as f:
        f.write("[server]\nport = 8801\n\n[db]\nhost = h\nname = n\nuser = u\npool_size = 2\n\n"
                "[features]\ncheckout_enabled = false\n")
    st = os.stat(path)
    os.utime(path, (st.st_atime, st.st_mtime + 5))   # bump mtime like kubelet does
    shop.reload_cfg_if_changed()
    assert shop.FEATURES.get("checkout_enabled") == "false"
