"""LangGraph State Machine orchestrator.

Defines the computational graph structure, wires node transitions, registers conditional 
routing logic based on confidence scores, and compiles the runnable interface with persistent 
checkpointing.
"""

from __future__ import annotations

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from common.schemas import ReviewState
from engine.nodes import (
    node_analyze,
    node_auto_approve,
    node_commit,
    node_escalate,
    node_fetch_pr,
    node_human_review,
    node_route,
    node_synthesize,
)


def build_graph(checkpointer: AsyncSqliteSaver) -> CompiledStateGraph:
    """Construct the StateGraph execution pipeline and compile it with Sqlite checkpointing."""
    g = StateGraph(ReviewState)
    
    # Register computational Nodes
    g.add_node("fetch_pr", node_fetch_pr)
    g.add_node("analyze", node_analyze)
    g.add_node("route", node_route)
    g.add_node("auto_approve", node_auto_approve)
    g.add_node("human_review", node_human_review)
    g.add_node("commit", node_commit)
    g.add_node("escalate", node_escalate)
    g.add_node("synthesize", node_synthesize)
    
    # Define Static Edges
    g.add_edge(START, "fetch_pr")
    g.add_edge("fetch_pr", "analyze")
    g.add_edge("analyze", "route")
    
    # Define Conditional Edges from routing evaluation
    g.add_conditional_edges(
        "route",
        lambda s: s.get("decision", "human_approval"),
        {
            "auto_approve": "auto_approve",
            "human_approval": "human_review",
            "escalate": "escalate"
        },
    )
    
    # Define Convergence and End Edges
    g.add_edge("auto_approve", END)
    g.add_edge("human_review", "commit")
    g.add_edge("commit", END)
    g.add_edge("escalate", "synthesize")
    g.add_edge("synthesize", "commit")
    
    # Compile graph integrating the persistence checkpoint saver
    return g.compile(checkpointer=checkpointer)
