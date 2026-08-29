"""
Thread-safe port pool for allocating RTP UDP ports.

Each concurrent SIP call needs a unique port pair (RTP + RTCP).
Includes a cooldown period after release to avoid stale-packet crossover
when a port is reused immediately.
"""

import threading
import time

from .config import RTP_PORT_START, RTP_PORT_END
from src.core.logger import logger


class PortPool:
    """Thread-safe pool of UDP ports for RTP sockets."""

    # A released port must sit idle this long before it can be handed out again. The old value
    # of 5 seconds was short enough that a peer still sending RTP to a just-ended call could
    # have its packets arrive at a socket already rebound to a different call.
    COOLDOWN_SECONDS = 30

    def __init__(self, start: int, end: int):
        # Step by 2 so port+1 is free for RTCP
        # Map port → release_timestamp (0.0 = immediately eligible)
        self._free: dict[int, float] = {p: 0.0 for p in range(start, end, 2)}
        self._lock = threading.Lock()
        # Rotating cursor. Ports are handed out round-robin rather than lowest-first so the
        # whole range is cycled through before any port comes back around; lowest-first meant
        # the same handful of low ports were reused over and over under load.
        self._order: list[int] = sorted(self._free)
        self._cursor = 0
        logger.info(f"[PortPool] Ready with {len(self._free)} ports ({start}-{end})")

    def acquire(self) -> int:
        with self._lock:
            now = time.time()
            total = len(self._order)
            for offset in range(total):
                port = self._order[(self._cursor + offset) % total]
                released_at = self._free.get(port)
                if released_at is None:
                    continue  # currently in use
                if now - released_at < self.COOLDOWN_SECONDS:
                    continue  # still cooling down
                self._cursor = (self._cursor + offset + 1) % total
                del self._free[port]
                logger.debug(f"[PortPool] Acquired {port}. Remaining: {len(self._free)}")
                return port
            raise RuntimeError(
                f"No free RTP ports in {RTP_PORT_START}-{RTP_PORT_END}. "
                "Increase RTP_PORT_END or reduce concurrent calls."
            )

    def release(self, port: int) -> None:
        with self._lock:
            self._free[port] = time.time()  # start cooldown
            logger.debug(f"[PortPool] Released {port}. Remaining: {len(self._free)}")


_port_pool: PortPool | None = None
_port_pool_lock = threading.Lock()


def get_port_pool() -> PortPool:
    global _port_pool
    with _port_pool_lock:
        if _port_pool is None:
            _port_pool = PortPool(RTP_PORT_START, RTP_PORT_END)
        return _port_pool
