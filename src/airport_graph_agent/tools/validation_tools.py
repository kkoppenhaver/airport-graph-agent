"""Validation tools for airport graph extraction.

These tools help validate the extracted graph for completeness and accuracy.
"""

import base64
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

from airport_graph_agent.db import get_all_connections, get_all_nodes, get_graph_stats


@tool(
    "validate_graph_structure",
    "Run programmatic validation checks on the graph structure. Checks for connectivity issues, orphan nodes, and missing elements.",
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
async def validate_graph_structure(args: dict[str, Any]) -> dict[str, Any]:
    """Validate the graph structure for an airport."""
    airport = args["airport"]

    try:
        nodes = get_all_nodes(airport)
        connections = get_all_connections(airport)
        stats = get_graph_stats(airport)

        issues: list[str] = []
        warnings: list[str] = []

        # Build adjacency info
        connected_nodes: set[str] = set()
        for conn in connections:
            connected_nodes.add(conn["from_id"])
            connected_nodes.add(conn["to_id"])

        node_ids = {n["id"] for n in nodes}
        node_types = {n["id"]: n["type"] for n in nodes}

        # Check 1: Orphan nodes (no connections)
        orphan_nodes = node_ids - connected_nodes
        for orphan in orphan_nodes:
            node_type = node_types.get(orphan, "Unknown")
            issues.append(f"Orphan node (no connections): {orphan} ({node_type})")

        # Check 2: Runway ends should come in pairs
        runway_ends = [n for n in nodes if n["type"] == "RunwayEnd"]
        runway_ids: dict[str, list] = {}
        for rwy in runway_ends:
            # Extract runway_id from the node - we need to query it
            # For now, just check we have an even number
            pass
        if len(runway_ends) % 2 != 0:
            warnings.append(f"Odd number of runway ends ({len(runway_ends)}). Runways should have 2 ends each.")

        # Check 3: Hold short nodes should connect to runway ends
        hold_shorts = [n for n in nodes if n["type"] == "HoldShort"]
        for hs in hold_shorts:
            hs_connections = [c for c in connections if c["from_id"] == hs["id"] or c["to_id"] == hs["id"]]
            connects_to_runway = any(
                node_types.get(c["to_id"]) == "RunwayEnd" or node_types.get(c["from_id"]) == "RunwayEnd"
                for c in hs_connections
            )
            if not connects_to_runway:
                warnings.append(f"Hold short {hs['name']} doesn't connect to any runway end")

        # Check 4: Every taxiway intersection should have at least 2 connections
        taxiway_intersections = [n for n in nodes if n["type"] == "TaxiwayIntersection"]
        for twy in taxiway_intersections:
            twy_connections = [c for c in connections if c["from_id"] == twy["id"] or c["to_id"] == twy["id"]]
            if len(twy_connections) < 2:
                warnings.append(f"Taxiway intersection {twy['name']} has only {len(twy_connections)} connection(s)")

        # Check 5: FBOs and ramps should be connected
        fbos_and_ramps = [n for n in nodes if n["type"] in ["FBO", "Ramp"]]
        for loc in fbos_and_ramps:
            loc_connections = [c for c in connections if c["from_id"] == loc["id"] or c["to_id"] == loc["id"]]
            if len(loc_connections) == 0:
                issues.append(f"{loc['type']} {loc['name']} has no connections")

        # Check 6: Connections referencing non-existent nodes
        for conn in connections:
            if conn["from_id"] not in node_ids:
                issues.append(f"Connection references non-existent node: {conn['from_id']}")
            if conn["to_id"] not in node_ids:
                issues.append(f"Connection references non-existent node: {conn['to_id']}")

        # Check 7: Minimum graph size
        if stats["total_nodes"] < 5:
            warnings.append(f"Graph seems incomplete: only {stats['total_nodes']} nodes")
        if stats["total_connections"] < 5:
            warnings.append(f"Graph seems incomplete: only {stats['total_connections']} connections")

        # Build result
        result_lines = [f"Validation Results for {airport}:"]
        result_lines.append(f"Nodes: {stats['total_nodes']}, Connections: {stats['total_connections']}")
        result_lines.append("")

        if issues:
            result_lines.append(f"## ISSUES ({len(issues)}):")
            for issue in issues:
                result_lines.append(f"  ❌ {issue}")
            result_lines.append("")

        if warnings:
            result_lines.append(f"## WARNINGS ({len(warnings)}):")
            for warning in warnings:
                result_lines.append(f"  ⚠️  {warning}")
            result_lines.append("")

        if not issues and not warnings:
            result_lines.append("✅ No issues or warnings found!")
        elif not issues:
            result_lines.append("✅ No critical issues found (warnings are non-blocking)")

        return {
            "content": [{"type": "text", "text": "\n".join(result_lines)}]
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"Error during validation: {str(e)}"}],
            "is_error": True
        }


@tool(
    "validate_against_diagram",
    "Compare the current graph against the original airport diagram. Returns the diagram for visual comparison along with the current graph state.",
    {
        "type": "object",
        "properties": {
            "airport": {
                "type": "string",
                "description": "ICAO airport code"
            },
            "image_path": {
                "type": "string",
                "description": "Path to the original PNG airport diagram"
            }
        },
        "required": ["airport", "image_path"]
    }
)
async def validate_against_diagram(args: dict[str, Any]) -> dict[str, Any]:
    """Compare the graph against the original diagram for visual validation."""
    airport = args["airport"]
    image_path = args["image_path"]

    try:
        # Load the image
        path = Path(image_path)
        if not path.exists():
            return {
                "content": [{"type": "text", "text": f"Error: Image file not found: {image_path}"}],
                "is_error": True
            }

        # Determine media type
        suffix = path.suffix.lower()
        media_types = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
        media_type = media_types.get(suffix, "image/png")

        with open(path, "rb") as f:
            image_data = base64.standard_b64encode(f.read()).decode("utf-8")

        # Get current graph state
        nodes = get_all_nodes(airport)
        connections = get_all_connections(airport)
        stats = get_graph_stats(airport)

        # Format nodes by type
        nodes_by_type: dict[str, list] = {}
        for node in nodes:
            node_type = node["type"]
            if node_type not in nodes_by_type:
                nodes_by_type[node_type] = []
            nodes_by_type[node_type].append(node)

        # Build summary
        summary_lines = [
            f"## Visual Validation for {airport}",
            "",
            "Compare the diagram below with the extracted graph:",
            "",
            f"**Graph Statistics:** {stats['total_nodes']} nodes, {stats['total_connections']} connections",
            "",
            "### Extracted Elements:",
        ]

        for node_type, type_nodes in nodes_by_type.items():
            summary_lines.append(f"\n**{node_type}s ({len(type_nodes)}):**")
            for n in type_nodes:
                pos = f"({n['x']:.0f}, {n['y']:.0f})"
                summary_lines.append(f"  - {n['name']} at {pos}")

        summary_lines.extend([
            "",
            "### Validation Checklist:",
            "Please verify the following by comparing with the diagram:",
            "- [ ] All runways are captured with both ends",
            "- [ ] All major taxiways are included",
            "- [ ] Taxiway intersections are at correct positions",
            "- [ ] Hold short positions are before each runway crossing",
            "- [ ] FBOs and ramps are in correct locations",
            "- [ ] Connections accurately represent the taxiway layout",
            "",
            "Report any discrepancies found.",
        ])

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
                    "text": "\n".join(summary_lines)
                }
            ]
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"Error during visual validation: {str(e)}"}],
            "is_error": True
        }


@tool(
    "check_path_exists",
    "Check if a valid path exists between two points in the graph. Useful for verifying connectivity.",
    {
        "type": "object",
        "properties": {
            "airport": {
                "type": "string",
                "description": "ICAO airport code"
            },
            "from_id": {
                "type": "string",
                "description": "Starting node ID"
            },
            "to_id": {
                "type": "string",
                "description": "Destination node ID"
            }
        },
        "required": ["airport", "from_id", "to_id"]
    }
)
async def check_path_exists(args: dict[str, Any]) -> dict[str, Any]:
    """Check if a path exists between two nodes."""
    airport = args["airport"]
    from_id = args["from_id"]
    to_id = args["to_id"]

    try:
        from airport_graph_agent.db import find_path

        path = find_path(airport, from_id, to_id)

        if path:
            nodes = " -> ".join(path["node_names"])
            via = ", ".join(path["via_list"])
            holds = sum(1 for h in path["holds"] if h)

            result = f"""Path found from {from_id} to {to_id}:

Route: {nodes}
Via: {via}
Hold short positions: {holds}

✅ Connectivity verified."""
        else:
            result = f"""❌ No path found from {from_id} to {to_id}

This indicates a connectivity issue in the graph. Check that:
1. Both nodes exist in the graph
2. There are connections linking these nodes
3. All intermediate taxiway intersections are connected"""

        return {
            "content": [{"type": "text", "text": result}]
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"Error checking path: {str(e)}"}],
            "is_error": True
        }


# Export all validation tools
VALIDATION_TOOLS = [validate_graph_structure, validate_against_diagram, check_path_exists]
