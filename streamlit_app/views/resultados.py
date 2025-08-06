"""
Streamlit view for displaying trading results.

Shows profit and loss or other statistics about completed trades. This
placeholder displays a simple message.
"""

from __future__ import annotations

import streamlit as st  # type: ignore


def render() -> None:
    """Render the results view."""
    st.header("Trading Results")
    st.write("No trades executed yet.")
