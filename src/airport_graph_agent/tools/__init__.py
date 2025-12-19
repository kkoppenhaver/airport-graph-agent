"""Agent tools for airport graph extraction."""

from claude_agent_sdk import create_sdk_mcp_server

from airport_graph_agent.tools.analysis_tools import ANALYSIS_TOOLS
from airport_graph_agent.tools.graph_tools import GRAPH_TOOLS
from airport_graph_agent.tools.validation_tools import VALIDATION_TOOLS

# Combine all tools
ALL_TOOLS = GRAPH_TOOLS + ANALYSIS_TOOLS + VALIDATION_TOOLS

# Create MCP server with all tools
airport_graph_server = create_sdk_mcp_server(
    name="airport-graph",
    version="0.1.0",
    tools=ALL_TOOLS
)

__all__ = [
    "airport_graph_server",
    "ALL_TOOLS",
    "GRAPH_TOOLS",
    "ANALYSIS_TOOLS",
    "VALIDATION_TOOLS",
]
