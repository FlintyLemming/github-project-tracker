"""Streamlit Web Dashboard for GitHub AI Tracker."""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st

# Page configuration
st.set_page_config(
    page_title="GitHub AI Tracker",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .summary-card {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 20px;
        margin-bottom: 20px;
    }
    .stat-box {
        background-color: #262730;
        border-radius: 5px;
        padding: 10px;
        text-align: center;
    }
    .repo-header {
        color: #1f77b4;
        font-size: 1.2em;
        font-weight: bold;
    }
    .date-tag {
        background-color: #4CAF50;
        color: white;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.8em;
    }
</style>
""", unsafe_allow_html=True)


def get_db_connection():
    """Get database connection."""
    db_path = Path("./data/tracker.db")
    if not db_path.exists():
        return None
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_all_repos():
    """Get all tracked repositories."""
    conn = get_db_connection()
    if not conn:
        return []
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT repo_full_name
        FROM summaries
        ORDER BY repo_full_name
    """)
    repos = [row["repo_full_name"] for row in cursor.fetchall()]
    conn.close()
    return repos


def get_summaries(repo_name=None, start_date=None, end_date=None):
    """Get summaries with optional filters."""
    conn = get_db_connection()
    if not conn:
        return []

    cursor = conn.cursor()
    query = "SELECT * FROM summaries WHERE 1=1"
    params = []

    if repo_name and repo_name != "All":
        query += " AND repo_full_name = ?"
        params.append(repo_name)

    if start_date:
        query += " AND summary_date >= ?"
        params.append(start_date.strftime("%Y-%m-%d"))

    if end_date:
        query += " AND summary_date <= ?"
        params.append(end_date.strftime("%Y-%m-%d"))

    query += " ORDER BY summary_date DESC, created_at DESC"

    cursor.execute(query, params)
    summaries = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return summaries


def get_statistics():
    """Get dashboard statistics."""
    conn = get_db_connection()
    if not conn:
        return {"total_repos": 0, "total_summaries": 0, "total_prs": 0, "total_releases": 0}

    cursor = conn.cursor()

    # Total repos
    cursor.execute("SELECT COUNT(DISTINCT repo_full_name) as count FROM summaries")
    total_repos = cursor.fetchone()["count"]

    # Total summaries
    cursor.execute("SELECT COUNT(*) as count FROM summaries")
    total_summaries = cursor.fetchone()["count"]

    # Total PRs and Releases
    cursor.execute("SELECT SUM(pr_count) as prs, SUM(release_count) as releases FROM summaries")
    row = cursor.fetchone()
    total_prs = row["prs"] or 0
    total_releases = row["releases"] or 0

    conn.close()

    return {
        "total_repos": total_repos,
        "total_summaries": total_summaries,
        "total_prs": total_prs,
        "total_releases": total_releases
    }


def main():
    """Main Streamlit application."""
    # Header
    st.title("📦 GitHub AI Tracker")
    st.markdown("实时追踪 GitHub 项目动态，AI 智能总结更新内容")

    # Sidebar
    with st.sidebar:
        st.header("🔍 筛选条件")

        # Repository filter
        repos = get_all_repos()
        repo_options = ["All"] + repos
        selected_repo = st.selectbox(
            "选择项目",
            repo_options,
            index=0
        )

        # Date range filter
        st.subheader("日期范围")
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input(
                "开始日期",
                value=datetime.now() - timedelta(days=30),
                max_value=datetime.now()
            )
        with col2:
            end_date = st.date_input(
                "结束日期",
                value=datetime.now(),
                max_value=datetime.now()
            )

        # Refresh button
        if st.button("🔄 刷新数据", use_container_width=True):
            st.rerun()

        st.divider()

        # Statistics
        st.header("📊 统计信息")
        stats = get_statistics()

        col1, col2 = st.columns(2)
        with col1:
            st.metric("追踪项目", stats["total_repos"])
            st.metric("PR 数量", stats["total_prs"])
        with col2:
            st.metric("总结数量", stats["total_summaries"])
            st.metric("版本发布", stats["total_releases"])

    # Main content
    summaries = get_summaries(
        repo_name=selected_repo if selected_repo != "All" else None,
        start_date=start_date,
        end_date=end_date
    )

    if not summaries:
        st.info("📭 暂无数据。请等待追踪程序运行后查看结果。")
        return

    # Display summaries
    st.subheader(f"📋 更新记录 ({len(summaries)} 条)")

    for summary in summaries:
        repo_name = summary["repo_full_name"]
        summary_date = summary["summary_date"]
        content = summary["content"]
        pr_count = summary.get("pr_count", 0)
        release_count = summary.get("release_count", 0)

        with st.expander(f"**{repo_name}** - {summary_date}", expanded=False):
            # Stats row
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.markdown(f"📅 **日期**: {summary_date}")
            with col2:
                st.markdown(f"🔀 **PR**: {pr_count}")
            with col3:
                st.markdown(f"🏷️ **发布**: {release_count}")
            with col4:
                repo_url = f"https://github.com/{repo_name}"
                st.markdown(f"[🔗 查看仓库]({repo_url})")

            st.divider()

            # Summary content
            st.markdown(content)

    # Footer
    st.divider()
    st.markdown(
        "<div style='text-align: center; color: gray;'>"
        "GitHub AI Tracker - Powered by Streamlit"
        "</div>",
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()
