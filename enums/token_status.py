"""
Enumeration for token statuses within the bsc_sniper application.

Tokens discovered by the system can be categorised into different states
such as candidates, excluded (e.g. honeypots), currently being followed for
trading, or already sold.
"""

from __future__ import annotations

from enum import Enum


class TokenStatus(str, Enum):
    """Possible states for a token in the system."""

    CANDIDATE = "candidate"
    EXCLUDED = "excluded"
    FOLLOWING = "following"
    SOLD = "sold"
