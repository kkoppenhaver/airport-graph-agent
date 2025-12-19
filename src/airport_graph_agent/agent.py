"""Agent orchestration for airport diagram processing.

This module defines the system prompt and agent loop for processing
FAA airport diagrams into Neo4j graph databases.
"""

import asyncio
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)

from airport_graph_agent.db import clear_database, init_schema, verify_connection
from airport_graph_agent.tools import ALL_TOOLS, airport_graph_server

# System prompt for the airport diagram analysis agent
SYSTEM_PROMPT = """You are an expert at analyzing FAA airport diagrams and extracting their structure into a graph database.

## Your Task
Given an airport diagram image and ICAO code, you will:
1. Analyze the diagram to identify all airport elements
2. Create nodes for each element in the graph database
3. Create connections between elements
4. Validate your work against the original diagram

## Workflow

### Phase 1: Initial Analysis
1. Call `get_analysis_guidance` to get instructions for what to look for
2. Call `load_diagram_image` to view the airport diagram
3. Carefully study the diagram and identify:
   - All runways (note both ends of each runway)
   - All taxiways (note letters and paths)
   - FBOs and their locations
   - Terminal buildings
   - Ramp/parking areas
   - Where taxiways intersect

### Phase 2: Create Graph Nodes
Create nodes in this order:
1. **Runway ends** - Create 2 nodes per runway (e.g., 27L and 09R for a single runway)
2. **Taxiway intersections** - Where taxiways meet or branch
3. **Hold short positions** - Before each runway crossing point
4. **FBOs** - Fixed Base Operator locations
5. **Ramps** - Parking/apron areas
6. **Terminals** - If present

For each node, estimate the x,y position (0-100 scale based on diagram layout).

### Phase 3: Create Connections
Connect all nodes with `CONNECTS` relationships:
- Use the taxiway name for `via` (e.g., "A", "B")
- Set `requires_hold: true` for connections that cross runways
- Make most connections bidirectional
- Estimate relative distances (1-10 scale)
- Note the cardinal direction of travel

### Phase 4: Validation
1. Call `validate_graph_structure` to check for issues
2. Call `validate_against_diagram` to visually verify
3. Use `check_path_exists` to verify connectivity between key points
4. Fix any issues found

## ID Naming Convention
Use consistent IDs:
- Runway ends: `{airport}_rwy_{number}` (e.g., KDPA_rwy_27L)
- Taxiway intersections: `{airport}_twy_{letters}` (e.g., KDPA_twy_A_B)
- Hold shorts: `{airport}_hold_{taxiway}_{runway}` (e.g., KDPA_hold_A_27L)
- FBOs: `{airport}_fbo_{name}` (e.g., KDPA_fbo_atlantic)
- Ramps: `{airport}_ramp_{name}` (e.g., KDPA_ramp_main)
- Terminals: `{airport}_terminal_{name}` (e.g., KDPA_terminal_main)

## Important Notes
- Be thorough - capture ALL taxiway intersections, not just major ones
- Every runway crossing needs a hold short node
- Verify your work matches the diagram before declaring completion
- Report your progress periodically using `report_analysis_progress`

Begin by getting analysis guidance and loading the diagram."""


def get_tool_names() -> list[str]:
    """Get the list of tool names for the agent."""
    return [f"mcp__airport-graph__{t.name}" for t in ALL_TOOLS]


async def process_diagram(
    image_path: str,
    airport: str,
    clear_existing: bool = True,
    verbose: bool = True,
) -> dict:
    """Process an airport diagram and build the graph.

    Args:
        image_path: Path to the PNG airport diagram
        airport: ICAO airport code (e.g., "KDPA")
        clear_existing: If True, clear existing data for this airport first
        verbose: If True, print progress messages

    Returns:
        Dict with processing results
    """
    # Verify Neo4j connection
    if not verify_connection():
        raise RuntimeError("Failed to connect to Neo4j. Is it running?")

    # Initialize schema if needed
    init_schema()

    # Clear existing data for this airport if requested
    if clear_existing:
        if verbose:
            print(f"Clearing existing data for {airport}...")
        clear_database(airport)

    # Verify the image exists
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Diagram not found: {image_path}")

    if verbose:
        print(f"Processing {airport} diagram: {image_path}")
        print("Starting agent...")

    # Configure agent options
    options = ClaudeAgentOptions(
        mcp_servers={"airport-graph": airport_graph_server},
        allowed_tools=get_tool_names(),
        system_prompt=SYSTEM_PROMPT,
    )

    # Initial message to start the agent
    initial_message = f"""Please analyze the airport diagram for {airport}.

The diagram is located at: {image_path}

Follow your workflow to:
1. Load and analyze the diagram
2. Create all nodes (runways, taxiways, FBOs, etc.)
3. Create connections between nodes
4. Validate the resulting graph

Start by getting analysis guidance, then load the diagram image."""

    results = {
        "airport": airport,
        "image_path": image_path,
        "messages": [],
        "tool_calls": 0,
        "completed": False,
    }

    try:
        async with ClaudeSDKClient(options=options) as client:
            # Send initial message
            await client.query(initial_message)

            # Process responses
            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            if verbose:
                                print(f"\nAgent: {block.text[:500]}..." if len(block.text) > 500 else f"\nAgent: {block.text}")
                            results["messages"].append({"type": "text", "content": block.text})
                        elif isinstance(block, ToolUseBlock):
                            results["tool_calls"] += 1
                            if verbose:
                                print(f"\n[Tool: {block.name}]")
                        elif isinstance(block, ToolResultBlock):
                            if verbose and hasattr(block, 'content'):
                                # Truncate long results
                                content_str = str(block.content)[:200]
                                print(f"[Result: {content_str}...]" if len(str(block.content)) > 200 else f"[Result: {block.content}]")

            results["completed"] = True

    except Exception as e:
        results["error"] = str(e)
        if verbose:
            print(f"\nError: {e}")

    if verbose:
        print(f"\nProcessing complete. Tool calls made: {results['tool_calls']}")

    return results


def run_process_diagram(
    image_path: str,
    airport: str,
    clear_existing: bool = True,
    verbose: bool = True,
) -> dict:
    """Synchronous wrapper for process_diagram."""
    return asyncio.run(process_diagram(image_path, airport, clear_existing, verbose))
