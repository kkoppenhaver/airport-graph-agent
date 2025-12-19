"""Graph manipulation tools for the airport agent.

These tools allow the agent to create nodes and connections in the Neo4j database.
"""

from typing import Any

from claude_agent_sdk import tool

from airport_graph_agent.db import (
    create_connection as db_create_connection,
    create_node as db_create_node,
    get_all_connections,
    get_all_nodes,
    get_graph_stats,
)
from airport_graph_agent.schema import (
    Connection,
    Direction,
    FBO,
    HoldShort,
    NodeType,
    Ramp,
    RunwayEnd,
    TaxiwayIntersection,
    Terminal,
)


@tool(
    "create_node",
    "Create a node in the airport graph. Use this to add runways, taxiways, FBOs, terminals, ramps, or hold short positions.",
    {
        "type": "object",
        "properties": {
            "node_type": {
                "type": "string",
                "enum": ["runway_end", "taxiway_intersection", "hold_short", "fbo", "terminal", "ramp"],
                "description": "The type of node to create"
            },
            "airport": {
                "type": "string",
                "description": "ICAO airport code (e.g., KDPA)"
            },
            "id": {
                "type": "string",
                "description": "Unique identifier for the node (e.g., KDPA_rwy_27L)"
            },
            "name": {
                "type": "string",
                "description": "Display name (e.g., 27L, Atlantic Aviation)"
            },
            "x": {
                "type": "number",
                "description": "Relative X position on diagram (0-100)"
            },
            "y": {
                "type": "number",
                "description": "Relative Y position on diagram (0-100)"
            },
            "heading": {
                "type": "integer",
                "description": "Magnetic heading (required for runway_end, e.g., 270 for runway 27)"
            },
            "runway_id": {
                "type": "string",
                "description": "Runway identifier grouping both ends (required for runway_end, e.g., 9_27)"
            },
            "taxiways": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of taxiway names at this intersection (required for taxiway_intersection)"
            },
            "runway": {
                "type": "string",
                "description": "Runway to hold short of (required for hold_short)"
            },
            "taxiway": {
                "type": "string",
                "description": "Taxiway this hold short is on (required for hold_short)"
            }
        },
        "required": ["node_type", "airport", "id", "name", "x", "y"]
    }
)
async def create_node(args: dict[str, Any]) -> dict[str, Any]:
    """Create a node in the airport graph."""
    node_type = args["node_type"]
    airport = args["airport"]
    node_id = args["id"]
    name = args["name"]
    x = args["x"]
    y = args["y"]

    try:
        if node_type == "runway_end":
            if "heading" not in args or "runway_id" not in args:
                return {
                    "content": [{"type": "text", "text": "Error: runway_end requires 'heading' and 'runway_id'"}],
                    "is_error": True
                }
            node = RunwayEnd(
                id=node_id, airport=airport, name=name, x=x, y=y,
                heading=args["heading"], runway_id=args["runway_id"]
            )
        elif node_type == "taxiway_intersection":
            if "taxiways" not in args:
                return {
                    "content": [{"type": "text", "text": "Error: taxiway_intersection requires 'taxiways' array"}],
                    "is_error": True
                }
            node = TaxiwayIntersection(
                id=node_id, airport=airport, name=name, x=x, y=y,
                taxiways=args["taxiways"]
            )
        elif node_type == "hold_short":
            if "runway" not in args or "taxiway" not in args:
                return {
                    "content": [{"type": "text", "text": "Error: hold_short requires 'runway' and 'taxiway'"}],
                    "is_error": True
                }
            node = HoldShort(
                id=node_id, airport=airport, name=name, x=x, y=y,
                runway=args["runway"], taxiway=args["taxiway"]
            )
        elif node_type == "fbo":
            node = FBO(id=node_id, airport=airport, name=name, x=x, y=y)
        elif node_type == "terminal":
            node = Terminal(id=node_id, airport=airport, name=name, x=x, y=y)
        elif node_type == "ramp":
            node = Ramp(id=node_id, airport=airport, name=name, x=x, y=y)
        else:
            return {
                "content": [{"type": "text", "text": f"Error: Unknown node type '{node_type}'"}],
                "is_error": True
            }

        result = db_create_node(node)
        return {
            "content": [{
                "type": "text",
                "text": f"Created {node_type} node: {name} (id: {node_id})"
            }]
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"Error creating node: {str(e)}"}],
            "is_error": True
        }


@tool(
    "create_connection",
    "Create a connection between two nodes in the airport graph. Use this to link taxiways, runways, ramps, etc.",
    {
        "type": "object",
        "properties": {
            "from_id": {
                "type": "string",
                "description": "ID of the source node"
            },
            "to_id": {
                "type": "string",
                "description": "ID of the destination node"
            },
            "via": {
                "type": "string",
                "description": "Surface name connecting them (taxiway name like 'A', or 'runway', 'ramp')"
            },
            "distance": {
                "type": "integer",
                "description": "Relative distance (1-10 scale)",
                "minimum": 1,
                "maximum": 10
            },
            "direction": {
                "type": "string",
                "enum": ["N", "NE", "E", "SE", "S", "SW", "W", "NW"],
                "description": "Cardinal direction of travel from source to destination"
            },
            "requires_hold": {
                "type": "boolean",
                "description": "True if this connection crosses a runway (requires hold short)",
                "default": False
            },
            "bidirectional": {
                "type": "boolean",
                "description": "If true, create connection in both directions",
                "default": True
            }
        },
        "required": ["from_id", "to_id", "via", "distance", "direction"]
    }
)
async def create_connection(args: dict[str, Any]) -> dict[str, Any]:
    """Create a connection between two nodes."""
    from_id = args["from_id"]
    to_id = args["to_id"]
    via = args["via"]
    distance = args["distance"]
    direction_str = args["direction"]
    requires_hold = args.get("requires_hold", False)
    bidirectional = args.get("bidirectional", True)

    try:
        direction = Direction[direction_str]

        # Create forward connection
        conn = Connection(
            from_id=from_id,
            to_id=to_id,
            via=via,
            distance=distance,
            direction=direction,
            requires_hold=requires_hold
        )
        db_create_connection(conn)

        result_text = f"Created connection: {from_id} -> {to_id} via {via}"

        # Create reverse connection if bidirectional
        if bidirectional:
            # Calculate opposite direction
            opposite_directions = {
                Direction.N: Direction.S,
                Direction.NE: Direction.SW,
                Direction.E: Direction.W,
                Direction.SE: Direction.NW,
                Direction.S: Direction.N,
                Direction.SW: Direction.NE,
                Direction.W: Direction.E,
                Direction.NW: Direction.SE,
            }
            reverse_conn = Connection(
                from_id=to_id,
                to_id=from_id,
                via=via,
                distance=distance,
                direction=opposite_directions[direction],
                requires_hold=requires_hold
            )
            db_create_connection(reverse_conn)
            result_text += f" (bidirectional)"

        return {
            "content": [{"type": "text", "text": result_text}]
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"Error creating connection: {str(e)}"}],
            "is_error": True
        }


@tool(
    "get_current_graph",
    "Get the current state of the graph for an airport. Use this to see what nodes and connections exist.",
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
async def get_current_graph(args: dict[str, Any]) -> dict[str, Any]:
    """Get the current graph state for an airport."""
    airport = args["airport"]

    try:
        nodes = get_all_nodes(airport)
        connections = get_all_connections(airport)
        stats = get_graph_stats(airport)

        # Format nodes by type
        nodes_by_type: dict[str, list] = {}
        for node in nodes:
            node_type = node["type"]
            if node_type not in nodes_by_type:
                nodes_by_type[node_type] = []
            nodes_by_type[node_type].append(f"{node['name']} (id: {node['id']}, pos: {node['x']:.0f},{node['y']:.0f})")

        # Format output
        lines = [f"Graph for {airport}:"]
        lines.append(f"Total: {stats['total_nodes']} nodes, {stats['total_connections']} connections")
        lines.append("")

        for node_type, node_list in nodes_by_type.items():
            lines.append(f"{node_type}s:")
            for n in node_list:
                lines.append(f"  - {n}")
            lines.append("")

        if connections:
            lines.append("Connections:")
            for conn in connections[:20]:  # Limit to first 20
                hold_marker = " [HOLD]" if conn["requires_hold"] else ""
                lines.append(f"  - {conn['from_id']} -> {conn['to_id']} via {conn['via']}{hold_marker}")
            if len(connections) > 20:
                lines.append(f"  ... and {len(connections) - 20} more")

        return {
            "content": [{"type": "text", "text": "\n".join(lines)}]
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"Error getting graph: {str(e)}"}],
            "is_error": True
        }


# Export all tools
GRAPH_TOOLS = [create_node, create_connection, get_current_graph]
