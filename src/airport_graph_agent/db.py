"""Neo4j database connection and utilities."""

import os
from contextlib import contextmanager
from typing import Optional

from dotenv import load_dotenv
from neo4j import GraphDatabase

from airport_graph_agent.schema import (
    CLEAR_AIRPORT_QUERY,
    CREATE_CONNECTION_QUERY,
    CREATE_NODE_QUERIES,
    FIND_PATH_QUERY,
    GET_ALL_CONNECTIONS_QUERY,
    GET_ALL_NODES_QUERY,
    LIST_AIRPORTS_QUERY,
    SCHEMA_CONSTRAINTS,
    Connection,
    Node,
    NodeType,
    get_connection_to_dict,
    get_node_to_dict,
)

load_dotenv()

# Module-level driver instance for reuse
_driver = None


def get_driver():
    """Get or create a Neo4j driver instance from environment variables."""
    global _driver
    if _driver is None:
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "airport-graph-password")
        _driver = GraphDatabase.driver(uri, auth=(user, password))
    return _driver


def close_driver():
    """Close the driver connection."""
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


@contextmanager
def get_session():
    """Context manager for Neo4j sessions."""
    driver = get_driver()
    with driver.session() as session:
        yield session


def verify_connection() -> bool:
    """Verify that we can connect to Neo4j."""
    try:
        driver = get_driver()
        driver.verify_connectivity()
        return True
    except Exception as e:
        print(f"Failed to connect to Neo4j: {e}")
        return False


def init_schema():
    """Initialize the database schema with constraints."""
    with get_session() as session:
        # Execute each constraint separately
        for line in SCHEMA_CONSTRAINTS.strip().split(";"):
            line = line.strip()
            if line and not line.startswith("//"):
                session.run(line)


def clear_database(airport: Optional[str] = None):
    """Clear nodes and relationships from the database.

    Args:
        airport: If provided, only clear data for this airport.
                 If None, clears all data.
    """
    with get_session() as session:
        session.run(CLEAR_AIRPORT_QUERY, airport=airport)


def create_node(node: Node) -> dict:
    """Create a node in the database."""
    query = CREATE_NODE_QUERIES[node.node_type]
    params = get_node_to_dict(node)
    with get_session() as session:
        result = session.run(query, params)
        record = result.single()
        return dict(record["n"]) if record else {}


def create_connection(connection: Connection) -> bool:
    """Create a connection between two nodes."""
    params = get_connection_to_dict(connection)
    with get_session() as session:
        result = session.run(CREATE_CONNECTION_QUERY, params)
        return result.single() is not None


def get_all_nodes(airport: Optional[str] = None) -> list[dict]:
    """Get all nodes from the database.

    Args:
        airport: If provided, only return nodes for this airport.
    """
    with get_session() as session:
        result = session.run(GET_ALL_NODES_QUERY, airport=airport)
        return [dict(record) for record in result]


def get_all_connections(airport: Optional[str] = None) -> list[dict]:
    """Get all connections from the database.

    Args:
        airport: If provided, only return connections for this airport.
    """
    with get_session() as session:
        result = session.run(GET_ALL_CONNECTIONS_QUERY, airport=airport)
        return [dict(record) for record in result]


def find_path(airport: str, start_id: str, end_id: str) -> Optional[dict]:
    """Find the shortest path between two nodes at an airport.

    Args:
        airport: The ICAO airport code.
        start_id: The ID of the starting node.
        end_id: The ID of the ending node.
    """
    with get_session() as session:
        result = session.run(
            FIND_PATH_QUERY,
            airport=airport,
            start_id=start_id,
            end_id=end_id
        )
        record = result.single()
        if record:
            return {
                "node_names": record["node_names"],
                "via_list": record["via_list"],
                "holds": record["holds"],
            }
        return None


def list_airports() -> list[str]:
    """List all airports in the database."""
    with get_session() as session:
        result = session.run(LIST_AIRPORTS_QUERY)
        return [record["airport"] for record in result]


def get_graph_stats(airport: Optional[str] = None) -> dict:
    """Get statistics about the current graph.

    Args:
        airport: If provided, only count nodes/connections for this airport.
    """
    with get_session() as session:
        if airport:
            node_count = session.run(
                "MATCH (n) WHERE n.airport = $airport RETURN count(n) AS count",
                airport=airport
            ).single()["count"]
            rel_count = session.run(
                "MATCH (a)-[r]->(b) WHERE a.airport = $airport RETURN count(r) AS count",
                airport=airport
            ).single()["count"]
        else:
            node_count = session.run("MATCH (n) RETURN count(n) AS count").single()["count"]
            rel_count = session.run("MATCH ()-[r]->() RETURN count(r) AS count").single()["count"]

        # Count by type
        type_counts = {}
        for node_type in NodeType:
            label = node_type.value
            if airport:
                count = session.run(
                    f"MATCH (n:{label}) WHERE n.airport = $airport RETURN count(n) AS count",
                    airport=airport
                ).single()["count"]
            else:
                count = session.run(
                    f"MATCH (n:{label}) RETURN count(n) AS count"
                ).single()["count"]
            if count > 0:
                type_counts[label] = count

        return {
            "total_nodes": node_count,
            "total_connections": rel_count,
            "nodes_by_type": type_counts,
        }
