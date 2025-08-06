"""
Streamlit view for excluded tokens.

Displays tokens that have been excluded from trading (e.g. detected
honeypots). This is a stub implementation.
"""

from __future__ import annotations

import streamlit as st  # type: ignore


def render() -> None:
    """Render the excluded tokens view."""
    st.header("Excluded Tokens")
    st.write("No excluded tokens.")
