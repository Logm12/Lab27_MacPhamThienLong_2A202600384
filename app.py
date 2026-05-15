"""Streamlit web UI for the HITL PR Review Agent.

Provides a 2-column dashboard featuring live Diff previews, AI Analytics dashboards, 
Confidence tracking visuals, dynamic interaction cards, and historical state restoration.

Run with:
    uv run streamlit run app.py
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime
from typing import Any

import streamlit as st
from dotenv import load_dotenv
from langgraph.types import Command

from audit.analytics import (
    get_analytics_metrics,
    get_calibration_curve,
    get_confidence_trend,
    get_performance_metrics,
    get_recent_sessions,
    get_top_risk_files,
)
from common.database import get_checkpointer
from engine.graph import build_graph

# Prioritize local environment configuration overrides
load_dotenv(".env.local")
load_dotenv(".env")


# ─── Token Persistence Helpers ─────────────────────────────────────────────────
def get_persisted_token() -> str:
    """Retrieve persisted GitHub Token from local storage if present."""
    if os.path.exists(".env.local"):
        with open(".env.local", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("GITHUB_TOKEN="):
                    return line.strip().split("=", 1)[1]
    return os.environ.get("GITHUB_TOKEN", "")


def save_persisted_token(token: str) -> None:
    """Save GitHub Token safely into gitignored local context."""
    with open(".env.local", "w", encoding="utf-8") as f:
        f.write(f"GITHUB_TOKEN={token}\n")


def clear_persisted_token() -> None:
    """Purge gitignored local context token storage."""
    if os.path.exists(".env.local"):
        try:
            os.remove(".env.local")
        except Exception:
            pass


# ─── Session State Initializer ───────────────────────────────────────────────
def init_session_state() -> None:
    """Verify state presence and set robust default placeholders."""
    defaults = {
        "thread_id": None,
        "pr_url": "",
        "interrupt_payload": None,
        "final": None,
        "pr_diff": "",
        "analysis": None,
        "history_checkpoint": None,
        "github_token": get_persisted_token(),
        "remember_token": os.path.exists(".env.local"),
        "validation_error": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


init_session_state()


# ─── Layout Config ───────────────────────────────────────────────────────────
st.set_page_config(page_title="HITL PR Review Agent Pro", layout="wide")

# Custom CSS inject for the Confidence progress bar and UI cleanups
st.markdown(
    """
    <style>
    .stProgress > div > div > div > div {
        background-color: #4f46e5;
    }
    .confidence-container {
        width: 100%; 
        background-color: #f3f4f6; 
        border-radius: 8px; 
        height: 26px; 
        overflow: hidden;
        box-shadow: inset 0 1px 2px rgba(0,0,0,0.1);
        margin: 10px 0;
    }
    .confidence-bar {
        height: 100%; 
        text-align: center; 
        color: white; 
        font-size: 13px; 
        font-weight: 700; 
        line-height: 26px; 
        transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1);
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def render_confidence_bar(confidence: float) -> None:
    """Compute threshold buckets and render an HSL Hues dynamic confidence tracker."""
    pct = int(confidence * 100)
    # REQ-UI-02 Threshold Logic
    if confidence < 0.58:
        color = "#ef4444"  # Vivid Red
    elif confidence <= 0.72:
        color = "#f59e0b"  # Deep Yellow/Amber
    else:
        color = "#10b981"  # Strong Emerald Green
        
    st.markdown(
        f"""
        <div class="confidence-container">
          <div class="confidence-bar" style="width: {pct}%; background-color: {color};">
            Confidence {pct}%
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


async def fork_thread_checkpoint(old_thread: str, checkpoint_id: str) -> str:
    """Clones a specific checkpoint snapshot into a fresh thread ID to initialize branching."""
    new_thread = f"{old_thread}_fork_{str(uuid.uuid4())[:6]}"
    async with get_checkpointer() as cp:
        g = build_graph(cp)
        # Fetch origin snapshot
        src_state = await g.aget_state({"configurable": {"thread_id": old_thread, "checkpoint_id": checkpoint_id}})
        
        # Determine node cursor insertion point
        as_node = "fetch_pr"
        if src_state.metadata and "source" in src_state.metadata:
            as_node = src_state.metadata["source"]
            
        # Copy exact snapshot value memory into the new branched namespace
        await g.aupdate_state(
            {"configurable": {"thread_id": new_thread}},
            src_state.values,
            as_node=as_node
        )
    return new_thread


# ─── Graph Runtime Orchestrator ──────────────────────────────────────────────
async def run_graph_async(
    pr_url: str, 
    thread_id: str, 
    resume_value: Any = None,
    checkpoint_config: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Encapsulate the safe checkpointer context and drive LangGraph execution."""
    async with get_checkpointer() as cp:
        app = build_graph(cp)
        
        # Allow target checkpoint ID override for time-travel resumption
        cfg = {"configurable": {"thread_id": thread_id}}
        if checkpoint_config:
            cfg.update(checkpoint_config)

        if resume_value is not None:
            # Interrupted Resume Loop
            result = await app.ainvoke(Command(resume=resume_value), cfg)
        else:
            # Brand New Start Loop
            result = await app.ainvoke(
                {"pr_url": pr_url, "thread_id": thread_id}, 
                cfg
            )
        return result


def run_graph_sync(
    pr_url: str, 
    thread_id: str, 
    resume_value: Any = None,
    checkpoint_config: dict[str, Any] | None = None
) -> None:
    """Wrap async invocation with a status block to update local session state."""
    with st.status("Agent thinking...", expanded=True) as status:
        status.write("Initializing graph execution state...")
        try:
            result = asyncio.run(run_graph_async(
                pr_url, thread_id, resume_value, checkpoint_config
            ))
            status.write("Analyzing outputs and persistent states...")
            
            # Persist active diff/analysis to session state for UI consistency
            if "__interrupt__" in result:
                st.session_state.interrupt_payload = result["__interrupt__"][0].value
                # Fetch the intermediate state keys to render the Diff immediately
                async def get_inter_state():
                    async with get_checkpointer() as cp:
                        g = build_graph(cp)
                        return await g.aget_state({"configurable": {"thread_id": thread_id}})
                
                curr_state = asyncio.run(get_inter_state())
                vals = curr_state.values
                st.session_state.pr_diff = vals.get("pr_diff", "")
                st.session_state.analysis = vals.get("analysis", None)
                st.session_state.final = None
            else:
                st.session_state.interrupt_payload = None
                st.session_state.final = result
                st.session_state.pr_diff = result.get("pr_diff", "")
                st.session_state.analysis = result.get("analysis", None)
                
            status.update(label="Execution step complete!", state="complete", expanded=False)
        except Exception as e:
            status.update(label=f"Execution failed: {str(e)}", state="error", expanded=True)
            st.error(f"A critical graph exception occurred: {e}")


# ─── Core Sidebar UI Components ─────────────────────────────────────────────
with st.sidebar:
    st.title("Agent Settings")
    
    # Mask token input securely - favor thread-safe session memory
    github_token = st.text_input(
        "GitHub Access Token", 
        type="password", 
        value=st.session_state["github_token"],
        help="Used to post final comments back to PRs."
    )
    st.session_state["github_token"] = github_token
    
    remember_token = st.checkbox(
        "Remember Token", 
        value=st.session_state["remember_token"],
        help="Persists your PAT securely to .env.local so it persists across sessions."
    )
    st.session_state["remember_token"] = remember_token
    
    # Dynamic Persistence trigger
    if remember_token and github_token:
        save_persisted_token(github_token)
    elif not remember_token:
        clear_persisted_token()
        
    st.divider()
    
    # Task 4: Advanced Mode & Time-travel Listing
    advanced_mode = st.toggle("Advanced Mode (Time-Travel)", value=False)
    
    if advanced_mode and st.session_state.thread_id:
        st.subheader("Checkpoint History")
        
        async def fetch_history():
            async with get_checkpointer() as cp:
                g = build_graph(cp)
                history_objs = []
                async for state_wrapper in g.aget_state_history({"configurable": {"thread_id": st.session_state.thread_id}}):
                    history_objs.append(state_wrapper)
                return history_objs
                
        try:
            states = asyncio.run(fetch_history())
            if not states:
                st.info("No historical checkpoints found.")
            else:
                st.caption("Click to resume from a previous state:")
                for s in states:
                    step_name = s.next[0] if s.next else "END"
                    timestamp_str = "Now"
                    # Attempt to extract timestamp metadata if stored
                    meta = s.metadata or {}
                    ts = meta.get("created_at")
                    if ts:
                        timestamp_str = ts.split(".")[0].replace("T", " ")
                        
                    col_state, col_btn = st.columns([3, 2])
                    col_state.markdown(f"**`{step_name}`**  \n<small>{timestamp_str}</small>", unsafe_allow_html=True)
                    
                    # Handle state jump safely preserving branching
                    if col_btn.button("Revert ↩", key=f"ckpt_{s.config['configurable']['checkpoint_id']}"):
                        st.warning(f"Forking history to {step_name}...")
                        
                        # Clone snapshot memory into a fresh unique thread
                        new_thread = asyncio.run(fork_thread_checkpoint(
                            st.session_state.thread_id,
                            s.config["configurable"]["checkpoint_id"]
                        ))
                        
                        # Pivot active stream state context
                        st.session_state.thread_id = new_thread
                        st.session_state.pr_diff = s.values.get("pr_diff", "")
                        st.session_state.analysis = s.values.get("analysis", None)
                        
                        if s.next:
                            # Retrieve the interrupt metadata to render the response forms instantly
                            async def fetch_restored_interrupt():
                                async with get_checkpointer() as cp:
                                    g = build_graph(cp)
                                    res = await g.aget_state({"configurable": {"thread_id": new_thread}})
                                    if res.tasks and res.tasks[0].interrupts:
                                        return res.tasks[0].interrupts[0].value
                                    return None
                                    
                            st.session_state.interrupt_payload = asyncio.run(fetch_restored_interrupt())
                            st.session_state.final = None
                        else:
                            st.session_state.final = s.values
                            st.session_state.interrupt_payload = None
                            
                        st.rerun()
        except Exception as e:
            st.error(f"Failed retrieving checkpoint history: {e}")
            
    st.divider()
    
    # Sidebar — populate from recent sessions queries
    st.subheader("Recent Review Sessions")
    try:
        recent = asyncio.run(get_recent_sessions())
        if recent:
            for item in recent[:8]:
                title = item["pr_url"].split("/")[-1]
                btn_label = f"#{title} ({item['worst_risk']})"
                if st.button(btn_label, key=f"hist_{item['thread_id']}", use_container_width=True):
                    st.session_state.thread_id = item["thread_id"]
                    st.session_state.pr_url = item["pr_url"]
                    # Force resync of the graph state values
                    async def get_restored_state():
                        async with get_checkpointer() as cp:
                            g = build_graph(cp)
                            return await g.aget_state({"configurable": {"thread_id": item["thread_id"]}})
                    restored = asyncio.run(get_restored_state())
                    st.session_state.pr_diff = restored.values.get("pr_diff", "")
                    st.session_state.analysis = restored.values.get("analysis", None)
                    if restored.next:
                        # Fetch the interrupt payload from active tasks if suspended
                        if restored.tasks and restored.tasks[0].interrupts:
                            st.session_state.interrupt_payload = restored.tasks[0].interrupts[0].value
                        else:
                            st.session_state.interrupt_payload = None
                        st.session_state.final = None
                    else:
                        st.session_state.final = restored.values
                        st.session_state.interrupt_payload = None
                    st.rerun()
        else:
            st.caption("No previous sessions found.")
    except Exception as e:
        st.caption(f"Database session query disabled: {e}")


# ─── Main Functional Tabs ────────────────────────────────────────────────────
tab_review, tab_analytics = st.tabs(["Active Review Engine", "Analytics Dashboard"])

# ─── TAB 1: Active Review Engine ──────────────────────────────────────────────
with tab_review:
    st.subheader("Initiate Pull Request Analysis")
    
    with st.form("pr_initiator"):
        in_url = st.text_input(
            "GitHub Pull Request URL",
            value=st.session_state.pr_url,
            placeholder="https://github.com/owner/repo/pull/123"
        )
        trigger = st.form_submit_button("Begin Review Cycle", type="primary")
        
    if trigger and in_url:
        st.session_state.validation_error = None
        st.session_state.pr_url = in_url
        st.session_state.thread_id = str(uuid.uuid4())
        st.session_state.interrupt_payload = None
        st.session_state.final = None
        st.session_state.pr_diff = ""
        st.session_state.analysis = None
        
        # Non-blocking pre-flight warning for the developer experience
        from common.github import check_write_permission
        ok, msg = check_write_permission(in_url)
        if not ok:
            st.warning(f"Token Diagnostic: {msg}. You can analyze this PR, but may not be able to post comments.")
            
        run_graph_sync(in_url, st.session_state.thread_id)
        st.rerun()
        
    st.divider()
    
    # Phase 2: Two-Column Screen Layout
    col_diff, col_actions = st.columns([2, 1])
    
    with col_diff:
        st.subheader("Pull Request Unified Diff")
        if st.session_state.pr_diff:
            st.code(st.session_state.pr_diff, language="diff", line_numbers=True)
        else:
            st.info("Diff content is not loaded yet. Please trigger a review analysis.")
            
    with col_actions:
        st.subheader("Agent Action Hub")
        
        # Show analysis card info if we have it
        analysis = st.session_state.analysis
        if analysis:
            # Dynamic CSS Confidence Bar
            render_confidence_bar(analysis.confidence)
            
            with st.expander("📋 Analysis Findings Summary", expanded=True):
                st.markdown(f"**Reasoning:** {analysis.confidence_reasoning}")
                st.markdown(analysis.summary)
                
                if analysis.comments:
                    st.write("**Detailed Criticisms:**")
                    for c in analysis.comments:
                        # Work with both Pydantic models and plain dicts gracefully
                        cmt_file = getattr(c, "file", c.get("file") if isinstance(c, dict) else "?")
                        cmt_line = getattr(c, "line", c.get("line") if isinstance(c, dict) else "?")
                        cmt_body = getattr(c, "body", c.get("body") if isinstance(c, dict) else "")
                        cmt_sev = getattr(c, "severity", c.get("severity") if isinstance(c, dict) else "info")
                        st.markdown(f"- **[{cmt_sev}]** `{cmt_file}:{cmt_line}` → {cmt_body}")
        
        # Handle Active Interrupts (Form Interactivity)
        payload = st.session_state.interrupt_payload
        if payload:
            kind = payload.get("kind")
            st.divider()
            
            if kind == "approval_request":
                st.warning("Waiting for Approval Action")
                
                if st.session_state.validation_error:
                    st.error(st.session_state.validation_error)
                    
                feedback = st.text_input("Reviewer feedback (optional)", key="user_feedback")
                
                c1, c2, c3 = st.columns(3)
                if c1.button("Approve ✅", type="primary", use_container_width=True):
                    # Hardened Pre-commit scope authorization gate
                    from common.github import check_write_permission
                    ok, msg = check_write_permission(st.session_state.pr_url)
                    if ok:
                        st.session_state.validation_error = None
                        run_graph_sync(
                            st.session_state.pr_url, 
                            st.session_state.thread_id, 
                            resume_value={"choice": "approve", "feedback": feedback}
                        )
                        st.rerun()
                    else:
                        st.session_state.validation_error = f"🚫 Permission Denied: {msg}"
                        st.rerun()
                if c2.button("Reject ❌", use_container_width=True):
                    st.session_state.validation_error = None
                    run_graph_sync(
                        st.session_state.pr_url, 
                        st.session_state.thread_id, 
                        resume_value={"choice": "reject", "feedback": feedback}
                    )
                    st.rerun()
                if c3.button("Edit 📝", use_container_width=True):
                    run_graph_sync(
                        st.session_state.pr_url, 
                        st.session_state.thread_id, 
                        resume_value={"choice": "edit", "feedback": feedback}
                    )
                    st.rerun()
                    
            elif kind == "escalation":
                st.error("Low-Confidence Escalation Form")
                if payload.get("risk_factors"):
                    st.error(f"**Identified Risks:** {', '.join(payload['risk_factors'])}")
                    
                # Task 3.2: Separate text inputs per question inside st.form
                with st.form("escalation_resolution"):
                    st.write("Please answer the following agent queries to assist resolution:")
                    ans_dict = {}
                    q_list = payload.get("questions", ["Please clarify the intent of this PR?"])
                    
                    for idx, q in enumerate(q_list):
                        ans_dict[q] = st.text_input(f"Question {idx+1}: {q}", key=f"q_ans_{idx}")
                        
                    submitted_answers = st.form_submit_button("Resolve Escalation ⚡", type="primary")
                    if submitted_answers:
                        run_graph_sync(
                            st.session_state.pr_url, 
                            st.session_state.thread_id, 
                            resume_value=ans_dict
                        )
                        st.rerun()
        
        # Handle Reached Final Output Endpoints
        final = st.session_state.final
        if final:
            st.divider()
            action = final.get("final_action", "unknown")
            if "commit" in action or "auto" in action:
                st.success(f"Complete: Posted review back to GitHub ({action})")
            elif action == "rejected":
                st.info("Complete: Pull Request review was rejected.")
            else:
                st.info(f"Flow finalized: {action}")
                
            st.caption(f"Active Thread ID: `{st.session_state.thread_id}`")


# ─── TAB 2: Analytics Dashboard ───────────────────────────────────────────────
with tab_analytics:
    st.header("Historical Pipeline Telemetry")
    
    try:
        metrics = asyncio.run(get_analytics_metrics())
        
        # REQ-BNS-01 st.metric displays
        m1, m2, m3 = st.columns(3)
        m1.metric("Average Confidence Score", f"{metrics['avg_confidence']:.1%}")
        m2.metric("Total Reviewed Sessions", int(metrics["total_sessions"]))
        m3.metric("Approval Target Rate", f"{metrics['approval_rate']:.1%}")
        
        st.divider()
        
        # Confidence Trend Charts
        st.subheader("Confidence Progression")
        trend = asyncio.run(get_confidence_trend())
        if trend:
            import pandas as pd
            df = pd.DataFrame(trend)
            # Transform to standard timestamp representation
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df.set_index("timestamp", inplace=True)
            st.bar_chart(df["confidence"])
        else:
            st.info("Insufficient chronological data present to project historical trends.")
            
        st.divider()
        
        # REQ-BNS-01: Expanders to maintain clean UI
        c_left, c_right = st.columns(2)
        
        with c_left:
            with st.expander("Calibration Curve Insights", expanded=True):
                calib_data = asyncio.run(get_calibration_curve())
                if calib_data:
                    import pandas as pd
                    df_calib = pd.DataFrame(calib_data)
                    # Render a clear correlation scatter map
                    st.markdown("<small>Matches AI confidence outputs against finalized Lead Developer choices.</small>", unsafe_allow_html=True)
                    st.scatter_chart(df_calib, x="confidence", y="decision", color="decision", size=25)
                else:
                    st.caption("Calibration curve data will unlock once 3+ finalized reviews accumulate.")
                    
        with c_right:
            with st.expander("High-Frequency Risk File Hotspots", expanded=True):
                risk_files = asyncio.run(get_top_risk_files())
                if risk_files:
                    import pandas as pd
                    df_risk = pd.DataFrame(risk_files)
                    st.markdown("<small>Identifies code paths flagged in high-risk (< 58% confidence) cycles.</small>", unsafe_allow_html=True)
                    st.dataframe(
                        df_risk, 
                        column_config={
                            "file": "Filename Path",
                            "flags": st.column_config.ProgressColumn("Flag Frequency", format="%d flags", min_value=0, max_value=15)
                        },
                        use_container_width=True, 
                        hide_index=True
                    )
                else:
                    st.caption("No high-frequency risk file data recorded yet.")
                    
        st.divider()
        
        with st.expander("Persona Latency Metrics", expanded=False):
            perf_metrics = asyncio.run(get_performance_metrics())
            if perf_metrics:
                import pandas as pd
                st.markdown("<small>Average computation and response times (seconds) derived from direct audit action steps.</small>", unsafe_allow_html=True)
                col_p1, col_p2, col_p3 = st.columns(3)
                
                keys = list(perf_metrics.keys())
                if len(keys) >= 1:
                    col_p1.metric(keys[0], f"{perf_metrics[keys[0]]:.2f}s")
                if len(keys) >= 2:
                    col_p2.metric(keys[1], f"{perf_metrics[keys[1]]:.2f}s")
                if len(keys) >= 3:
                    col_p3.metric(keys[2], f"{perf_metrics[keys[2]]:.2f}s")
                    
                # Render graphical representation for easier parsing
                df_perf = pd.DataFrame([{"Persona": k, "Average Response (sec)": v} for k, v in perf_metrics.items()])
                st.bar_chart(df_perf, x="Persona", y="Average Response (sec)", color="#4f46e5")
            else:
                st.caption("Insufficient timeline events to extract performance benchmarks.")
            
    except Exception as e:
        st.error(f"Telemetry Dashboard failed to construct: {e}")
        st.caption("Ensure the underlying schema and audit tables exist and have logged values.")
