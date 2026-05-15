"""LangGraph Engine Nodes: The computational execution units of the PR Review Agent.

Every node takes the Current `ReviewState`, performs an atomic operation (LLM analysis, 
GitHub action, or human interaction prompt), writes a corresponding structured `AuditEntry` 
to persistent storage, and returns a partial state update.

Complies with Vibe Code Rules: 100% type-hinted and type-safe.
"""

from __future__ import annotations

import os
import time

from langgraph.types import interrupt
from rich.console import Console

from common.database import write_audit_event
from common.github import fetch_pr, post_review_comment
from common.llm import get_llm
from common.schemas import (
    AUTO_APPROVE_THRESHOLD,
    ESCALATE_THRESHOLD,
    AuditEntry,
    Decision,
    PRAnalysis,
    ReviewState,
    risk_level_for,
)


console = Console()
AGENT_ID = "pr-review-agent@v0.1"


async def audit(state: ReviewState, entry: AuditEntry) -> None:
    """Write one structured AuditEntry row to the `audit_events` table.

    Encapsulates cross-referencing values from context state (`thread_id`, `pr_url`)
    to decouple callers from base persistence arguments.
    """
    thread_id = state.get("thread_id", "unknown-thread")
    pr_url = state.get("pr_url", "unknown-pr")
    await write_audit_event(thread_id=thread_id, pr_url=pr_url, entry=entry)


async def node_fetch_pr(state: ReviewState) -> ReviewState:
    """Fetch PR meta-information and raw diff text from GitHub API."""
    console.print("[cyan]-> fetch_pr[/cyan]")
    t0 = time.monotonic()
    
    pr_url = state.get("pr_url", "")
    with console.status("[dim]Fetching PR from GitHub...[/dim]"):
        pr = fetch_pr(pr_url)
    
    console.print(f"  [green][OK][/green] {len(pr.files_changed)} files, head {pr.head_sha[:7]}")
    
    execution_time_ms = int((time.monotonic() - t0) * 1000)
    
    await audit(state, AuditEntry(
        agent_id=AGENT_ID,
        action="fetch_pr",
        confidence=0.0,
        risk_level="med",
        decision="pending",
        reason=f"Fetched {len(pr.files_changed)} files, head={pr.head_sha[:7]}",
        execution_time_ms=execution_time_ms,
    ))
    
    return {
        "pr_title": pr.title,
        "pr_diff": pr.diff,
        "pr_files": pr.files_changed,
        "pr_head_sha": pr.head_sha,
    }


async def node_analyze(state: ReviewState) -> ReviewState:
    """Leverage LLM with structured output to produce deep review and confidence evaluation."""
    console.print("[cyan]-> analyze[/cyan]")
    t0 = time.monotonic()
    
    llm = get_llm().with_structured_output(PRAnalysis)
    pr_title = state.get("pr_title", "Untitled PR")
    pr_diff = state.get("pr_diff", "")
    
    with console.status("[dim]LLM reviewing the diff...[/dim]"):
        a: PRAnalysis = await llm.ainvoke([
            {"role": "system", "content": "Senior reviewer. Structured output."},
            {"role": "user", "content": f"Title: {pr_title}\nDiff:\n{pr_diff}"},
        ])
        
    console.print(f"  [green][OK][/green] confidence={a.confidence:.0%}, {len(a.comments)} comment(s)")
    
    execution_time_ms = int((time.monotonic() - t0) * 1000)
    
    # Extract reviewed files to support REQ-BNS-01 Top Risk Files analytics
    files_involved = sorted(list({c.file for c in a.comments if getattr(c, "file", None)}))
    files_suffix = f" [Files: {', '.join(files_involved)}]" if files_involved else ""
    
    await audit(state, AuditEntry(
        agent_id=AGENT_ID,
        action="analyze",
        confidence=a.confidence,
        risk_level=risk_level_for(a.confidence),
        decision="pending",
        reason=f"{a.confidence_reasoning}{files_suffix}",
        execution_time_ms=execution_time_ms,
    ))
    
    return {"analysis": a}


async def node_route(state: ReviewState) -> ReviewState:
    """Assess confidence score and set deterministic destination routes based on thresholds."""
    console.print("[cyan]-> route[/cyan]")
    t0 = time.monotonic()
    
    analysis = state.get("analysis")
    if not analysis:
        raise ValueError("Graph Inconsistency: node_route entered without valid LLM analysis.")
        
    confidence = analysis.confidence
    decision: Decision = "human_approval"
    
    if confidence >= AUTO_APPROVE_THRESHOLD:
        decision = "auto_approve"
    elif confidence < ESCALATE_THRESHOLD:
        decision = "escalate"
        
    console.print(f"  [green][OK][/green] decision=[bold]{decision}[/bold] (confidence={confidence:.0%})")
    
    execution_time_ms = int((time.monotonic() - t0) * 1000)
    
    # Map Decision to schema description literals
    audit_decision = "pending"
    if decision == "auto_approve":
        audit_decision = "auto"
    elif decision == "escalate":
        audit_decision = "escalate"
        
    await audit(state, AuditEntry(
        agent_id=AGENT_ID,
        action="route",
        confidence=confidence,
        risk_level=risk_level_for(confidence),
        decision=audit_decision,
        reason=f"Confidence thresholds routing mapped to routing node: {decision}",
        execution_time_ms=execution_time_ms,
    ))
    
    return {"decision": decision}


async def node_human_review(state: ReviewState) -> ReviewState:
    """Execute a UI-suspendable interrupt awaiting explicit review actions from an engineer."""
    console.print("[cyan]-> human_review[/cyan]")
    t0 = time.monotonic()
    
    analysis = state.get("analysis")
    if not analysis:
        raise ValueError("Graph Inconsistency: node_human_review entered without valid analysis.")
        
    # Log BEFORE the interrupt (waiting state)
    await audit(state, AuditEntry(
        agent_id=AGENT_ID,
        action="human_approval",
        confidence=analysis.confidence,
        risk_level=risk_level_for(analysis.confidence),
        decision="pending",
        reason="Interrupt triggered: awaiting manual human review choice",
        execution_time_ms=int((time.monotonic() - t0) * 1000),
    ))
    
    # Suspend execution and surface state for UI input
    t1 = time.monotonic()
    resp = interrupt({
        "kind": "approval_request",
        "pr_url": state.get("pr_url"),
        "confidence": analysis.confidence,
        "confidence_reasoning": analysis.confidence_reasoning,
        "summary": analysis.summary,
        "comments": [c.model_dump() for c in analysis.comments],
        "diff_preview": state.get("pr_diff", "")[:2000],
    })
    
    # Resume: capture feedback and metadata
    choice = resp.get("choice", "reject")
    feedback = resp.get("feedback", "")
    reviewer_id = os.environ.get("GITHUB_USER", "unknown_reviewer")
    
    execution_time_ms = int((time.monotonic() - t1) * 1000)
    
    # Map HumanChoice response to schema decision literals
    audit_decision = "reject"
    if choice in ["approve", "reject", "edit"]:
        audit_decision = choice
        
    await audit(state, AuditEntry(
        agent_id=AGENT_ID,
        action="human_approval",
        confidence=analysis.confidence,
        risk_level=risk_level_for(analysis.confidence),
        reviewer_id=reviewer_id,
        decision=audit_decision,
        reason=f"Human responded: choice={choice}, feedback={feedback}",
        execution_time_ms=execution_time_ms,
    ))
    
    return {"human_choice": choice, "human_feedback": feedback}


def _render_comment_body(state: ReviewState) -> str:
    """Format the comprehensive final PR comment synthesizing LLM reviews and human adjustments."""
    a = state.get("analysis")
    if not a:
        return ""
        
    lines = [f"### Automated review (confidence {a.confidence:.0%})", "", a.summary, ""]
    for c in a.comments:
        lines.append(f"- **[{c.severity}]** `{c.file}:{c.line or '?'}` — {c.body}")
        
    human_feedback = state.get("human_feedback")
    if human_feedback:
        lines.append(f"\n_Reviewer note: {human_feedback}_")
        
    escalation_answers = state.get("escalation_answers")
    if escalation_answers:
        lines.append("\n_Reviewer answered escalation questions:_")
        for q, ans in escalation_answers.items():
            lines.append(f"> **{q}** {ans}")
            
    return "\n".join(lines)


def _post(state: ReviewState) -> str:
    """Execute low-level API commit to GitHub. Propagates exceptions to callers."""
    pr_url = state.get("pr_url", "")
    comment_body = _render_comment_body(state)
    post_review_comment(pr_url, comment_body)
    console.print(f"  [green][OK][/green] posted comment to {pr_url}")
    return "committed"


async def node_commit(state: ReviewState) -> ReviewState:
    """Final exit node aggregating either human-approved edits or synthesized escalations for PR posting."""
    console.print("[cyan]-> commit[/cyan]")
    t0 = time.monotonic()
    
    analysis = state.get("analysis")
    if not analysis:
        raise ValueError("Graph Inconsistency: node_commit reached without valid analysis.")
        
    escalation_answers = state.get("escalation_answers")
    human_choice = state.get("human_choice")
    
    action = "rejected"
    risk_level = risk_level_for(analysis.confidence)
    reason = ""
    
    try:
        # Only commit if user approved OR if it came through synthesized escalation answers.
        if escalation_answers or human_choice == "approve":
            action = _post(state)
            reason = f"Commit finalize output action state: {action}"
        else:
            console.print(f"  [yellow][SKIP][/yellow] skipping comment (choice={human_choice})")
            action = "rejected"
            reason = f"Skipped comment by user choice: {human_choice}"
    except Exception as e:
        console.print(f"  [red][FAIL][/red] node_commit failed: {e}")
        action = "commit_failed"
        risk_level = "high"
        reason = f"GitHub API post failed with error: {str(e)}"
        
    execution_time_ms = int((time.monotonic() - t0) * 1000)
    
    audit_decision = "reject"
    if action == "committed":
        audit_decision = "approve"
    elif action == "commit_failed":
        audit_decision = "fail"
        
    await audit(state, AuditEntry(
        agent_id=AGENT_ID,
        action="commit",
        confidence=analysis.confidence,
        risk_level=risk_level,
        decision=audit_decision,
        reason=reason,
        execution_time_ms=execution_time_ms,
    ))
    
    return {"final_action": action}


async def node_auto_approve(state: ReviewState) -> ReviewState:
    """Fast-track high confidence analyses directly to GitHub API bypass-review posting."""
    console.print("[cyan]-> auto_approve[/cyan]  [dim]high confidence — posting directly[/dim]")
    t0 = time.monotonic()
    
    analysis = state.get("analysis")
    if not analysis:
        raise ValueError("Graph Inconsistency: node_auto_approve reached without valid analysis.")
        
    action = "auto_rejected"
    risk_level = risk_level_for(analysis.confidence)
    reason = ""
    
    try:
        action = _post(state)
        reason = f"Fast-track automated approval result: {action}"
    except Exception as e:
        console.print(f"  [red][FAIL][/red] node_auto_approve failed: {e}")
        action = "commit_failed"
        risk_level = "high"
        reason = f"Fast-track automated posting failed: {str(e)}"
    
    execution_time_ms = int((time.monotonic() - t0) * 1000)
    
    await audit(state, AuditEntry(
        agent_id=AGENT_ID,
        action="commit",
        confidence=analysis.confidence,
        risk_level=risk_level,
        decision="auto" if action == "committed" else "fail",
        reason=reason,
        execution_time_ms=execution_time_ms,
    ))
    
    return {"final_action": f"auto_{action}"}


async def node_escalate(state: ReviewState) -> ReviewState:
    """Suspend graph for low-confidence scenarios, querying reviewers with high-priority targeted questions."""
    console.print("[cyan]-> escalate[/cyan]")
    t0 = time.monotonic()
    
    analysis = state.get("analysis")
    if not analysis:
        raise ValueError("Graph Inconsistency: node_escalate reached without valid analysis.")
        
    questions = analysis.escalation_questions or ["What is the intent of this PR?"]
    
    # Log BEFORE Interrupt (waiting state)
    await audit(state, AuditEntry(
        agent_id=AGENT_ID,
        action="escalate",
        confidence=analysis.confidence,
        risk_level=risk_level_for(analysis.confidence),
        decision="pending",
        reason=f"Interrupt triggered: Escalated review with {len(questions)} queries.",
        execution_time_ms=int((time.monotonic() - t0) * 1000),
    ))
    
    # Suspend execution
    t1 = time.monotonic()
    answers = interrupt({
        "kind": "escalation",
        "pr_url": state.get("pr_url"),
        "confidence": analysis.confidence,
        "confidence_reasoning": analysis.confidence_reasoning,
        "summary": analysis.summary,
        "risk_factors": analysis.risk_factors,
        "questions": questions,
    })
    
    # Resume
    reviewer_id = os.environ.get("GITHUB_USER", "unknown_reviewer")
    execution_time_ms = int((time.monotonic() - t1) * 1000)
    
    await audit(state, AuditEntry(
        agent_id=AGENT_ID,
        action="escalate",
        confidence=analysis.confidence,
        risk_level=risk_level_for(analysis.confidence),
        reviewer_id=reviewer_id,
        decision="escalate",
        reason=f"Escalation resolved: User answered {len(answers)} queries.",
        execution_time_ms=execution_time_ms,
    ))
    
    return {"escalation_answers": answers}


async def node_synthesize(state: ReviewState) -> ReviewState:
    """Re-evaluate review assertions merging the original diff and manual escalation responses."""
    console.print("[cyan]-> synthesize[/cyan]")
    t0 = time.monotonic()
    
    original_analysis = state.get("analysis")
    orig_summary = ""
    orig_risks = []
    if original_analysis:
        orig_summary = original_analysis.summary
        orig_risks = original_analysis.risk_factors
        
    escalation_answers = state.get("escalation_answers") or {}
    qa = "\n".join(f"Q: {q}\nA: {a}" for q, a in escalation_answers.items())
    
    llm = get_llm().with_structured_output(PRAnalysis)
    pr_diff = state.get("pr_diff", "")
    
    prompt_content = (
        f"Original Analysis Summary: {orig_summary}\n"
        f"Original Risk Factors: {', '.join(orig_risks)}\n\n"
        f"Diff:\n{pr_diff}\n\n"
        f"Reviewer's Responses to Escalated Questions:\n{qa}\n\n"
        "Based on the developer's answers and the original diff, please re-evaluate the review. "
        "Formulate the final review comment resolving the previous red flags and incorporating reviewer answers."
    )
    
    with console.status("[dim]LLM refining review with reviewer answers...[/dim]"):
        refined: PRAnalysis = await llm.ainvoke([
            {"role": "system", "content": "You are an advanced PR reviewer refining your previous analysis based on user responses."},
            {"role": "user", "content": prompt_content},
        ])
        
    console.print(f"  [green][OK][/green] refined confidence={refined.confidence:.0%}")
    
    execution_time_ms = int((time.monotonic() - t0) * 1000)
    
    await audit(state, AuditEntry(
        agent_id=AGENT_ID,
        action="synthesize",
        confidence=refined.confidence,
        risk_level=risk_level_for(refined.confidence),
        decision="pending",
        reason="Analysis synthesized with refinement LLM run",
        execution_time_ms=execution_time_ms,
    ))
    
    return {"analysis": refined}
