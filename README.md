# airport-graph-agent

An AI agent that converts FAA airport diagrams (PNG) into Neo4j graph databases for taxi route planning. The generated graph can be queried to find realistic taxi paths between any two points on an airport, complete with hold short instructions.

## Overview

This tool uses the Claude Agent SDK to iteratively:
1. Analyze an FAA airport diagram using vision
2. Extract key points (runways, taxiways, FBOs, etc.)
3. Build a graph of connections between points
4. Validate the graph against the source diagram
5. Store the result in Neo4j for pathfinding queries

The database supports multiple airports, allowing you to build a comprehensive graph of many airports and query routes at any of them.

## Setup

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- Anthropic API key

### Installation

1. Clone the repository and create a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

2. Copy the environment template and add your API key:

```bash
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

3. Start Neo4j:

```bash
docker compose up -d
```

4. Initialize the schema and verify setup:

```bash
airport-graph init
airport-graph check
```

## Usage

### Processing a Diagram

Place your FAA airport diagram PNG in the `diagrams/` directory, then run:

```bash
airport-graph process diagrams/KDPA.png --airport KDPA
```

The `--airport` flag specifies the ICAO code for the airport being processed.

### CLI Commands

| Command | Description |
|---------|-------------|
| `airport-graph process <diagram> -a <ICAO>` | Process a diagram and build the graph |
| `airport-graph check` | Verify Neo4j connection |
| `airport-graph init` | Initialize database schema |
| `airport-graph stats [-a <ICAO>]` | Show graph statistics (optionally for one airport) |
| `airport-graph airports` | List all airports in the database |
| `airport-graph clear [-a <ICAO>] [-y]` | Clear data (optionally for one airport) |

### Querying Routes (Python)

```python
from airport_graph_agent.db import find_path, get_all_nodes

# Find a taxi route at KDPA
path = find_path("KDPA", "KDPA_fbo_atlantic", "KDPA_rwy_27L")
print(path["node_names"])  # ['Atlantic Aviation', 'A', 'B', 'Hold Short 27L', '27L']
print(path["holds"])       # [False, False, False, True, False]

# List all nodes at an airport
nodes = get_all_nodes("KDPA")
```

## Graph Schema

### Node Types

| Label | Description | Properties |
|-------|-------------|------------|
| `RunwayEnd` | Runway threshold (e.g., "27L", "09R") | `heading`, `runway_id` |
| `TaxiwayIntersection` | Where taxiways meet or branch | `taxiways[]` |
| `HoldShort` | Hold position before a runway | `runway`, `taxiway` |
| `FBO` | Fixed Base Operator location | - |
| `Terminal` | Terminal building | - |
| `Ramp` | Parking/ramp area | - |

All nodes have these common properties:
- `id`: Unique identifier (e.g., `KDPA_rwy_27L`)
- `airport`: ICAO airport code (e.g., `KDPA`)
- `name`: Display name (e.g., `27L`)
- `x`, `y`: Relative position on diagram (0-100 scale)

### Relationships

**`:CONNECTS`** - A connection between two points

| Property | Description |
|----------|-------------|
| `via` | Surface name (taxiway name, "runway", or "ramp") |
| `distance` | Relative distance (1-10 scale) |
| `direction` | Cardinal direction (N, NE, E, SE, S, SW, W, NW) |
| `requires_hold` | Boolean - true if crossing a runway |

### Example Graph Structure

```
[FBO: Atlantic Aviation]
        |
        | via: "ramp"
        v
[TaxiwayIntersection: A/Ramp]
        |
        | via: "A"
        v
[HoldShort: A at 27L] --requires_hold--> [RunwayEnd: 27L]
```

## Architecture

```
src/airport_graph_agent/
├── __init__.py
├── cli.py              # Click CLI commands
├── db.py               # Neo4j connection and CRUD operations
├── schema.py           # Node/relationship definitions and Cypher queries
└── tools/              # Agent tools (analyze, create, validate)
```

### Agent Tools (In Progress)

| Tool | Purpose |
|------|---------|
| `analyze_diagram` | Use Claude vision to identify elements in the diagram |
| `create_node` | Add a node to the Neo4j graph |
| `create_relationship` | Connect two nodes |
| `validate_graph` | Programmatic checks (connectivity, etc.) |
| `visual_validate` | Compare graph against source diagram |

## Development

Run tests:

```bash
pytest
```

Lint code:

```bash
ruff check src tests
```

### Neo4j Browser

Access the Neo4j browser at http://localhost:7474 (credentials: `neo4j` / `airport-graph-password`)

Useful Cypher queries:

```cypher
// View all nodes at an airport
MATCH (n) WHERE n.airport = "KDPA" RETURN n

// Find shortest path
MATCH path = shortestPath((a)-[:CONNECTS*]-(b))
WHERE a.id = "KDPA_fbo_atlantic" AND b.id = "KDPA_rwy_27L"
RETURN path

// View graph structure
MATCH (n)-[r]->(m) WHERE n.airport = "KDPA" RETURN n, r, m
```
