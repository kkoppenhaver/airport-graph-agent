"""Analysis tools for airport diagram extraction.

These tools help the agent systematically analyze airport diagrams
and track what elements have been identified.
"""

import base64
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool


@tool(
    "get_analysis_guidance",
    "Get guidance on what elements to look for in an FAA airport diagram. Call this first to understand what to extract.",
    {
        "type": "object",
        "properties": {
            "airport": {
                "type": "string",
                "description": "ICAO airport code (e.g., KDPA)"
            }
        },
        "required": ["airport"]
    }
)
async def get_analysis_guidance(args: dict[str, Any]) -> dict[str, Any]:
    """Provide guidance on analyzing an airport diagram."""
    airport = args["airport"]

    guidance = f"""Analyzing airport diagram for {airport}. Look for these elements:

## 1. RUNWAYS (identify first)
- Find all runway numbers (e.g., 27L/09R, 36/18)
- Note the runway heading from the numbers (runway 27 = 270° heading)
- Identify both ends of each runway as separate nodes
- Look for runway length markings if visible

## 2. TAXIWAYS
- Identify taxiway letters/names (A, B, C, AA, etc.)
- Find intersections where taxiways meet
- Note parallel taxiways to runways
- Identify connector taxiways between parallel taxiways

## 3. HOLD SHORT POSITIONS
- Located before every runway crossing point
- Usually marked with hold short lines on the diagram
- Create a hold_short node at each location

## 4. RAMPS AND PARKING
- Main ramp/apron areas
- GA (General Aviation) parking areas
- Commercial parking areas

## 5. FBOs (Fixed Base Operators)
- Look for named FBO locations
- Usually on the periphery of the airport
- Common names: Atlantic Aviation, Signature Flight Support, etc.

## 6. TERMINALS
- Passenger terminal buildings
- Cargo terminals

## Positioning Guidelines:
- Use 0-100 scale for x,y coordinates
- x=0 is left edge, x=100 is right edge
- y=0 is top, y=100 is bottom
- Estimate positions based on the diagram layout

## ID Naming Convention:
- Runway ends: {airport}_rwy_27L, {airport}_rwy_09R
- Taxiway intersections: {airport}_twy_A_B (intersection of A and B)
- Hold shorts: {airport}_hold_A_27L (taxiway A hold short of 27L)
- FBOs: {airport}_fbo_atlantic
- Ramps: {airport}_ramp_main
- Terminals: {airport}_terminal_main

Start by identifying all runways, then taxiways, then connections."""

    return {
        "content": [{"type": "text", "text": guidance}]
    }


@tool(
    "load_diagram_image",
    "Load an airport diagram image file and return it for analysis. The image will be included in your context for visual analysis.",
    {
        "type": "object",
        "properties": {
            "image_path": {
                "type": "string",
                "description": "Path to the PNG airport diagram file"
            }
        },
        "required": ["image_path"]
    }
)
async def load_diagram_image(args: dict[str, Any]) -> dict[str, Any]:
    """Load and return an airport diagram image for analysis."""
    image_path = args["image_path"]

    try:
        path = Path(image_path)
        if not path.exists():
            return {
                "content": [{"type": "text", "text": f"Error: Image file not found: {image_path}"}],
                "is_error": True
            }

        # Determine media type
        suffix = path.suffix.lower()
        if suffix == ".png":
            media_type = "image/png"
        elif suffix in [".jpg", ".jpeg"]:
            media_type = "image/jpeg"
        elif suffix == ".gif":
            media_type = "image/gif"
        elif suffix == ".webp":
            media_type = "image/webp"
        else:
            return {
                "content": [{"type": "text", "text": f"Error: Unsupported image format: {suffix}"}],
                "is_error": True
            }

        # Read and encode the image
        with open(path, "rb") as f:
            image_data = base64.standard_b64encode(f.read()).decode("utf-8")

        return {
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_data,
                    }
                },
                {
                    "type": "text",
                    "text": f"Airport diagram loaded from {image_path}. Analyze this image to identify airport elements."
                }
            ]
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"Error loading image: {str(e)}"}],
            "is_error": True
        }


@tool(
    "report_analysis_progress",
    "Report what elements have been identified so far and what remains. Use this to track your progress.",
    {
        "type": "object",
        "properties": {
            "airport": {
                "type": "string",
                "description": "ICAO airport code"
            },
            "runways_found": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of runway identifiers found (e.g., ['27L/09R', '36/18'])"
            },
            "taxiways_found": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of taxiway letters found (e.g., ['A', 'B', 'C'])"
            },
            "fbos_found": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of FBO names found"
            },
            "nodes_created": {
                "type": "integer",
                "description": "Number of nodes created so far"
            },
            "connections_created": {
                "type": "integer",
                "description": "Number of connections created so far"
            },
            "remaining_work": {
                "type": "string",
                "description": "Description of what still needs to be done"
            }
        },
        "required": ["airport", "runways_found", "taxiways_found"]
    }
)
async def report_analysis_progress(args: dict[str, Any]) -> dict[str, Any]:
    """Report analysis progress."""
    airport = args["airport"]
    runways = args.get("runways_found", [])
    taxiways = args.get("taxiways_found", [])
    fbos = args.get("fbos_found", [])
    nodes_created = args.get("nodes_created", 0)
    connections_created = args.get("connections_created", 0)
    remaining = args.get("remaining_work", "Not specified")

    report = f"""Analysis Progress for {airport}:

## Elements Identified:
- Runways: {', '.join(runways) if runways else 'None yet'}
- Taxiways: {', '.join(taxiways) if taxiways else 'None yet'}
- FBOs: {', '.join(fbos) if fbos else 'None yet'}

## Graph Status:
- Nodes created: {nodes_created}
- Connections created: {connections_created}

## Remaining Work:
{remaining}

## Next Steps:
"""
    if not runways:
        report += "1. Identify all runways first\n"
    elif not taxiways:
        report += "1. Identify all taxiways\n"
    elif nodes_created == 0:
        report += "1. Start creating nodes for identified elements\n"
    elif connections_created == 0:
        report += "1. Create connections between nodes\n"
    else:
        report += "1. Continue creating remaining connections\n"
        report += "2. Verify all hold short positions are marked\n"
        report += "3. Run validation when complete\n"

    return {
        "content": [{"type": "text", "text": report}]
    }


# Export all analysis tools
ANALYSIS_TOOLS = [get_analysis_guidance, load_diagram_image, report_analysis_progress]
