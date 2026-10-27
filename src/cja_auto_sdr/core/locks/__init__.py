"""Locking subsystem for cross-process coordination.

This package centralizes lock acquisition/release behavior behind
backend abstractions so application modules can use a stable API.
"""

from __future__ import annotations

from cja_auto_sdr.core.locks.backends import (
    FcntlFileLockBackend,
    LeaseFileLockBackend,
    LockInfo,
)
from cja_auto_sdr.core.locks.manager import LockManager, create_lock_backend

__all__ = [
    "FcntlFileLockBackend",
    "LeaseFileLockBackend",
    "LockInfo",
    "LockManager",
    "create_lock_backend",
]
