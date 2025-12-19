"""Neo4j schema definitions for airport graph.

Node Types (Labels):
- RunwayEnd: Threshold/end of a runway (e.g., "27L", "09R")
- TaxiwayIntersection: Where taxiways meet or branch
- HoldShort: Position where aircraft must hold before crossing/entering runway
- FBO: Fixed Base Operator location
- Terminal: Terminal building
- Ramp: Parking/ramp area

Relationship Types:
- CONNECTS: General connection between nodes via taxiway or ramp

All nodes have:
- id: Unique identifier (e.g., "KDPA_rwy_27L", "KDPA_twy_A_B")
- airport: ICAO airport code (e.g., "KDPA", "KORD")
- name: Display name (e.g., "27L", "A/B Intersection", "Atlantic Aviation")
- x, y: Relative position on diagram (0-100 scale, for validation)

Relationships have:
- via: What surface connects them (taxiway name, "runway", "ramp")
- distance: Relative distance (1-10 scale)
- direction: Cardinal direction of travel (N, NE, E, SE, S, SW, W, NW)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class NodeType(Enum):
    """Types of nodes in the airport graph."""
    RUNWAY_END = "RunwayEnd"
    TAXIWAY_INTERSECTION = "TaxiwayIntersection"
    HOLD_SHORT = "HoldShort"
    FBO = "FBO"
    TERMINAL = "Terminal"
    RAMP = "Ramp"


class Direction(Enum):
    """Cardinal directions for relationship orientation."""
    N = "N"
    NE = "NE"
    E = "E"
    SE = "SE"
    S = "S"
    SW = "SW"
    W = "W"
    NW = "NW"


@dataclass
class Node:
    """Base class for all airport graph nodes."""
    id: str
    airport: str  # ICAO airport code (e.g., "KDPA")
    name: str
    node_type: NodeType
    x: float  # Relative position 0-100
    y: float  # Relative position 0-100


@dataclass
class RunwayEnd(Node):
    """A runway threshold/end point."""
    heading: int  # Magnetic heading (e.g., 270 for runway 27)
    runway_id: str  # Groups both ends (e.g., "9_27" for 09/27)

    def __init__(self, id: str, airport: str, name: str, x: float, y: float,
                 heading: int, runway_id: str):
        super().__init__(id, airport, name, NodeType.RUNWAY_END, x, y)
        self.heading = heading
        self.runway_id = runway_id


@dataclass
class TaxiwayIntersection(Node):
    """An intersection or waypoint on taxiways."""
    taxiways: list[str]  # List of taxiway names at this point

    def __init__(self, id: str, airport: str, name: str, x: float, y: float,
                 taxiways: list[str]):
        super().__init__(id, airport, name, NodeType.TAXIWAY_INTERSECTION, x, y)
        self.taxiways = taxiways


@dataclass
class HoldShort(Node):
    """A hold short position before a runway."""
    runway: str  # Which runway to hold short of
    taxiway: str  # Which taxiway this hold short is on

    def __init__(self, id: str, airport: str, name: str, x: float, y: float,
                 runway: str, taxiway: str):
        super().__init__(id, airport, name, NodeType.HOLD_SHORT, x, y)
        self.runway = runway
        self.taxiway = taxiway


@dataclass
class FBO(Node):
    """A Fixed Base Operator location."""
    def __init__(self, id: str, airport: str, name: str, x: float, y: float):
        super().__init__(id, airport, name, NodeType.FBO, x, y)


@dataclass
class Terminal(Node):
    """A terminal building."""
    def __init__(self, id: str, airport: str, name: str, x: float, y: float):
        super().__init__(id, airport, name, NodeType.TERMINAL, x, y)


@dataclass
class Ramp(Node):
    """A parking/ramp area."""
    def __init__(self, id: str, airport: str, name: str, x: float, y: float):
        super().__init__(id, airport, name, NodeType.RAMP, x, y)


@dataclass
class Connection:
    """A connection between two nodes."""
    from_id: str
    to_id: str
    via: str  # Taxiway name, "runway", or "ramp"
    distance: int  # Relative distance 1-10
    direction: Direction
    requires_hold: bool = False  # True if crossing a runway


# Cypher queries for schema operations

SCHEMA_CONSTRAINTS = """
// Unique constraints on node IDs
CREATE CONSTRAINT runway_end_id IF NOT EXISTS
FOR (n:RunwayEnd) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT taxiway_intersection_id IF NOT EXISTS
FOR (n:TaxiwayIntersection) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT hold_short_id IF NOT EXISTS
FOR (n:HoldShort) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT fbo_id IF NOT EXISTS
FOR (n:FBO) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT terminal_id IF NOT EXISTS
FOR (n:Terminal) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT ramp_id IF NOT EXISTS
FOR (n:Ramp) REQUIRE n.id IS UNIQUE;
"""

CREATE_NODE_QUERIES = {
    NodeType.RUNWAY_END: """
        CREATE (n:RunwayEnd {
            id: $id, airport: $airport, name: $name, x: $x, y: $y,
            heading: $heading, runway_id: $runway_id
        })
        RETURN n
    """,
    NodeType.TAXIWAY_INTERSECTION: """
        CREATE (n:TaxiwayIntersection {
            id: $id, airport: $airport, name: $name, x: $x, y: $y,
            taxiways: $taxiways
        })
        RETURN n
    """,
    NodeType.HOLD_SHORT: """
        CREATE (n:HoldShort {
            id: $id, airport: $airport, name: $name, x: $x, y: $y,
            runway: $runway, taxiway: $taxiway
        })
        RETURN n
    """,
    NodeType.FBO: """
        CREATE (n:FBO {id: $id, airport: $airport, name: $name, x: $x, y: $y})
        RETURN n
    """,
    NodeType.TERMINAL: """
        CREATE (n:Terminal {id: $id, airport: $airport, name: $name, x: $x, y: $y})
        RETURN n
    """,
    NodeType.RAMP: """
        CREATE (n:Ramp {id: $id, airport: $airport, name: $name, x: $x, y: $y})
        RETURN n
    """,
}

CREATE_CONNECTION_QUERY = """
    MATCH (a), (b)
    WHERE a.id = $from_id AND b.id = $to_id
    CREATE (a)-[r:CONNECTS {
        via: $via,
        distance: $distance,
        direction: $direction,
        requires_hold: $requires_hold
    }]->(b)
    RETURN r
"""

# Query to find path between two nodes at a specific airport
FIND_PATH_QUERY = """
    MATCH path = shortestPath((start)-[:CONNECTS*]-(end))
    WHERE start.id = $start_id AND end.id = $end_id
          AND start.airport = $airport AND end.airport = $airport
    RETURN path,
           [node IN nodes(path) | node.name] AS node_names,
           [rel IN relationships(path) | rel.via] AS via_list,
           [rel IN relationships(path) | rel.requires_hold] AS holds
"""

# Query to get all nodes (optionally filtered by airport)
GET_ALL_NODES_QUERY = """
    MATCH (n)
    WHERE (n:RunwayEnd OR n:TaxiwayIntersection OR n:HoldShort
          OR n:FBO OR n:Terminal OR n:Ramp)
          AND ($airport IS NULL OR n.airport = $airport)
    RETURN n.id AS id, n.airport AS airport, n.name AS name,
           labels(n)[0] AS type, n.x AS x, n.y AS y
    ORDER BY airport, type, name
"""

# Query to get all connections (optionally filtered by airport)
GET_ALL_CONNECTIONS_QUERY = """
    MATCH (a)-[r:CONNECTS]->(b)
    WHERE $airport IS NULL OR a.airport = $airport
    RETURN a.id AS from_id, b.id AS to_id,
           r.via AS via, r.distance AS distance,
           r.direction AS direction, r.requires_hold AS requires_hold
"""

# Query to clear an airport's data (or all if airport is NULL)
CLEAR_AIRPORT_QUERY = """
    MATCH (n)
    WHERE $airport IS NULL OR n.airport = $airport
    DETACH DELETE n
"""

# Query to list all airports in the database
LIST_AIRPORTS_QUERY = """
    MATCH (n)
    WHERE n:RunwayEnd OR n:TaxiwayIntersection OR n:HoldShort
          OR n:FBO OR n:Terminal OR n:Ramp
    RETURN DISTINCT n.airport AS airport
    ORDER BY airport
"""


def get_node_to_dict(node: Node) -> dict:
    """Convert a Node object to a dictionary for Cypher parameters."""
    base = {
        "id": node.id,
        "airport": node.airport,
        "name": node.name,
        "x": node.x,
        "y": node.y,
    }

    if isinstance(node, RunwayEnd):
        base["heading"] = node.heading
        base["runway_id"] = node.runway_id
    elif isinstance(node, TaxiwayIntersection):
        base["taxiways"] = node.taxiways
    elif isinstance(node, HoldShort):
        base["runway"] = node.runway
        base["taxiway"] = node.taxiway

    return base


def get_connection_to_dict(conn: Connection) -> dict:
    """Convert a Connection object to a dictionary for Cypher parameters."""
    return {
        "from_id": conn.from_id,
        "to_id": conn.to_id,
        "via": conn.via,
        "distance": conn.distance,
        "direction": conn.direction.value,
        "requires_hold": conn.requires_hold,
    }
