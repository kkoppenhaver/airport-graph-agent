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

# Use Opus for better image identification accuracy
AGENT_MODEL = "claude-opus-4-20250514"

# System prompt for the airport diagram analysis agent
SYSTEM_PROMPT = """You are an expert at analyzing FAA airport diagrams and extracting their structure into a graph database.

## Your Task
Given an airport diagram image and ICAO code, you will:
1. Analyze the diagram to identify all airport elements
2. Create nodes for each element in the graph database
3. Create connections between elements
4. Validate your work against the original diagram

## Visual Identification Guide for FAA Diagrams

CRITICAL: FAA airport diagrams follow strict visual conventions. Use these to accurately identify elements:

### Runways
- **Appearance**: Solid BLACK elongated shapes (the darkest elements on the diagram)
- **Labels**: Runway numbers appear as TEXT at each END of the black shape (e.g., "2L" at one end, "20R" at the other)
- **Runway numbers are magnetic headings divided by 10** (runway 20 = 200° heading, runway 02 = 020° heading)
- **Parallel runways** have L/R/C suffixes (Left/Right/Center)
- **IMPORTANT**: Look for the RUNWAY LEGEND box (usually on the right side) which lists all runways like "RWY 02L-20R"
- Count the solid black shapes to verify the number of runways matches the legend

### Taxiways
- **Appearance**: GREY outlined paths (lighter than runways, not solid black)
- **Labels**: Single letters or letter+number combinations (A, B, C, W, W1, W2, etc.)
- Labels appear ON or ADJACENT to the grey paths
- Taxiways connect runways to ramps and to each other
- Follow the grey paths to understand connectivity

### What to IGNORE (DO NOT create nodes for these)
- Frequency boxes (ATIS, TOWER, GND CON, etc.)
- Notes and text blocks around the edges
- Elevation numbers (ELEV 759, etc.)
- Magnetic variation information
- Coordinates (latitude/longitude)
- Dimension text on runways (like "7571 X 150")
- "CLOSED" markings
- Blast pad annotations

## Workflow

### Phase 1: Initial Analysis
1. Call `get_analysis_guidance` to get instructions for what to look for
2. Call `load_diagram_image` to view the airport diagram
3. Carefully study the diagram using the visual guide above:
   - Find ONLY the solid black runway rectangles and their numbers
   - Check the RUNWAY LEGEND to confirm the exact number of runways
   - Trace the grey taxiway paths and note their letters
   - Identify FBO buildings (usually labeled by name on the periphery)
   - Find ramp/parking areas (open grey areas)

### Phase 2: Path Tracing Verification (IMPORTANT)
After initial identification, use path tracing to find any missed taxiways:
1. Call `trace_paths_from_point` starting from each runway end
2. Pass your list of already-known taxiways
3. The tool will help you discover any taxiways you missed
4. Repeat from 2-3 different starting points (e.g., different runway ends, main ramp)
5. Also call `scan_diagram_region` on edge areas (left-edge, bottom-left, etc.) where taxiways might be missed

This phase catches small connector taxiways and edge taxiways that are easy to miss on first pass.

### Phase 3: Create Graph Nodes
Create nodes in this order:
1. **Runway ends** - Create 2 nodes per runway (e.g., 27L and 09R for a single runway)
2. **Taxiway intersections** - Where taxiways meet or branch
3. **Hold short positions** - Before each runway crossing point
4. **FBOs** - Fixed Base Operator locations
5. **Ramps** - Parking/apron areas
6. **Terminals** - If present

For each node, estimate the x,y position (0-100 scale based on diagram layout).

### Phase 4: Create Connections
Connect all nodes with `CONNECTS` relationships:
- Use the taxiway name for `via` (e.g., "A", "B")
- Set `requires_hold: true` for connections that cross runways
- Make most connections bidirectional
- Estimate relative distances (1-10 scale)
- Note the cardinal direction of travel

### Phase 5: Validation
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
- **VERIFY RUNWAYS AGAINST THE LEGEND** - The runway legend box tells you exactly how many runways exist. Do not create more runway ends than the legend indicates.
- **Runways are solid black shapes** - if you don't see a solid black elongated shape, it's not a runway
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

    # Configure agent options - use Opus for better image identification
    options = ClaudeAgentOptions(
        model=AGENT_MODEL,
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
