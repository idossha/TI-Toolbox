#!/usr/bin/env python3
"""Streamlit dashboard for TI-Toolbox download and engagement stats."""

import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).parent / "stats.db"


@st.cache_data(ttl=300)
def load_releases_latest() -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        """
        SELECT tag, asset, downloads
        FROM github_releases
        WHERE date = (SELECT MAX(date) FROM github_releases)
        ORDER BY tag DESC, asset
        """,
        conn,
    )
    conn.close()
    return df


@st.cache_data(ttl=300)
def load_releases_totals() -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        """
        SELECT date, SUM(downloads) as total_dl
        FROM github_releases
        GROUP BY date
        ORDER BY date
        """,
        conn,
    )
    conn.close()
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


@st.cache_data(ttl=300)
def load_views() -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT date, views, uniques FROM github_views ORDER BY date", conn
    )
    conn.close()
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


@st.cache_data(ttl=300)
def load_clones() -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT date, clones, uniques FROM github_clones ORDER BY date", conn
    )
    conn.close()
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


@st.cache_data(ttl=300)
def load_referrers() -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        """
        SELECT referrer, count, uniques
        FROM github_referrers
        WHERE date = (SELECT MAX(date) FROM github_referrers)
        ORDER BY count DESC
        """,
        conn,
    )
    conn.close()
    return df


def platform_breakdown(df: pd.DataFrame) -> dict:
    """Infer OS and arch from asset filenames."""
    if df.empty:
        return {}
    # Skip metadata files (blockmaps, yml update files)
    real = df[~df["asset"].str.contains(r"\.(blockmap|yml)$", regex=True)]
    totals = {
        "macOS (arm64)": real[real["asset"].str.contains("arm64.dmg")]["downloads"].sum(),
        "macOS (x86)":   real[real["asset"].str.contains(r"(?<!arm64)\.dmg$", regex=True)]["downloads"].sum(),
        "Windows":       real[real["asset"].str.contains(r"\.exe$", regex=True)]["downloads"].sum(),
        "Linux AppImage": real[real["asset"].str.contains("AppImage")]["downloads"].sum(),
        "Linux .deb":    real[real["asset"].str.contains(r"\.deb$", regex=True)]["downloads"].sum(),
    }
    return {k: int(v) for k, v in totals.items() if v > 0}


def main() -> None:
    st.set_page_config(page_title="TI-Toolbox stats", layout="wide")
    st.title("TI-Toolbox download & engagement stats")

    if not DB_PATH.exists():
        st.error(f"Database not found at `{DB_PATH}`. Run `python fetch_stats.py` first.")
        return

    releases = load_releases_latest()
    totals = load_releases_totals()
    views = load_views()
    clones = load_clones()

    # --- Top metrics ---
    col1, col2, col3, col4 = st.columns(4)

    total_dl = int(totals.iloc[-1]["total_dl"]) if not totals.empty else 0
    prev_dl = int(totals.iloc[-2]["total_dl"]) if len(totals) > 1 else None
    col1.metric(
        "Total downloads",
        f"{total_dl:,}",
        delta=f"+{total_dl - prev_dl:,}" if prev_dl is not None else None,
    )

    total_views = int(views["views"].sum()) if not views.empty else 0
    col2.metric("Repo views (tracked)", f"{total_views:,}")

    total_clones = int(clones["clones"].sum()) if not clones.empty else 0
    col3.metric("Git clones (tracked)", f"{total_clones:,}")

    unique_cloners = int(clones["uniques"].sum()) if not clones.empty else 0
    col4.metric("Unique cloners (tracked)", f"{unique_cloners:,}")

    # --- Platform breakdown ---
    st.divider()
    st.subheader("Downloads by platform")
    plat = platform_breakdown(releases)
    if plat:
        cols = st.columns(len(plat))
        for col, (label, count) in zip(cols, plat.items()):
            col.metric(label, f"{count:,}")
    else:
        st.info("No release data yet.")

    # --- Charts ---
    st.divider()
    left, right = st.columns(2)

    with left:
        st.subheader("Repo page views over time")
        if not views.empty and len(views) > 1:
            st.line_chart(views.set_index("date")[["views", "uniques"]])
        else:
            st.info("Need at least 2 days of data.")

        st.subheader("Git clones over time")
        if not clones.empty and len(clones) > 1:
            st.line_chart(clones.set_index("date")[["clones", "uniques"]])
        else:
            st.info("Need at least 2 days of data.")

    with right:
        st.subheader("Cumulative downloads over time")
        if not totals.empty and len(totals) > 1:
            st.line_chart(totals.set_index("date")[["total_dl"]])
        else:
            st.info("Need at least 2 days of data.")

        st.subheader("Top referrers (last 14 days)")
        refs = load_referrers()
        if not refs.empty:
            st.bar_chart(refs.set_index("referrer")["count"])
        else:
            st.info("No referrer data yet.")

    # --- Per-release table ---
    st.divider()
    st.subheader("Downloads per release & asset (latest snapshot)")
    if not releases.empty:
        real = releases[~releases["asset"].str.contains(r"\.(blockmap|yml)$", regex=True)]
        st.dataframe(real, use_container_width=True, hide_index=True)

    st.caption("Data collected daily via GitHub Actions. Run `python tracking/fetch_stats.py` to update manually.")


if __name__ == "__main__":
    main()
