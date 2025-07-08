# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details


import hashlib


def hash(content: str) -> int:
    return int(hashlib.md5(content.encode()).hexdigest(), 16)
