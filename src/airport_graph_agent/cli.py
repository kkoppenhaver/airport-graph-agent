"""Command-line interface for the airport graph agent."""

from typing import Optional

import click

from airport_graph_agent.db import (
    clear_database,
    get_graph_stats,
    init_schema,
    list_airports,
    verify_connection,
)


@click.group()
@click.version_option()
def main():
    """Airport Graph Agent - Convert FAA airport diagrams to Neo4j graphs."""
    pass


@main.command()
@click.argument("diagram", type=click.Path(exists=True))
@click.option("--airport", "-a", required=True, help="ICAO airport code (e.g., KDPA)")
@click.option("--keep-existing", "-k", is_flag=True, help="Don't clear existing data for this airport")
@click.option("--quiet", "-q", is_flag=True, help="Suppress verbose output")
def process(diagram: str, airport: str, keep_existing: bool, quiet: bool):
    """Process an airport diagram and create a graph database.

    DIAGRAM: Path to the PNG airport diagram file.
    """
    from airport_graph_agent.agent import run_process_diagram

    airport = airport.upper()

    if not quiet:
        click.echo(f"Processing diagram: {diagram}")
        click.echo(f"Airport: {airport}")
        if not keep_existing:
            click.echo(f"(Existing data for {airport} will be cleared)")
        click.echo("")

    try:
        results = run_process_diagram(
            image_path=diagram,
            airport=airport,
            clear_existing=not keep_existing,
            verbose=not quiet,
        )

        if results.get("completed"):
            click.echo("")
            click.echo(f"✓ Processing complete for {airport}")
            click.echo(f"  Tool calls: {results['tool_calls']}")

            # Show final stats
            graph_stats = get_graph_stats(airport)
            click.echo(f"  Nodes created: {graph_stats['total_nodes']}")
            click.echo(f"  Connections created: {graph_stats['total_connections']}")
        else:
            click.echo("")
            click.echo(f"✗ Processing incomplete")
            if "error" in results:
                click.echo(f"  Error: {results['error']}")
            raise SystemExit(1)

    except FileNotFoundError as e:
        click.echo(f"✗ {e}")
        raise SystemExit(1)
    except RuntimeError as e:
        click.echo(f"✗ {e}")
        raise SystemExit(1)
    except Exception as e:
        click.echo(f"✗ Unexpected error: {e}")
        raise SystemExit(1)


@main.command()
def check():
    """Check Neo4j connection and configuration."""
    click.echo("Checking Neo4j connection...")
    if verify_connection():
        click.echo("✓ Successfully connected to Neo4j")
    else:
        click.echo("✗ Failed to connect to Neo4j")
        raise SystemExit(1)


@main.command()
def init():
    """Initialize the Neo4j schema (constraints and indexes)."""
    click.echo("Checking connection...")
    if not verify_connection():
        click.echo("✗ Failed to connect to Neo4j")
        raise SystemExit(1)

    click.echo("Initializing schema...")
    init_schema()
    click.echo("✓ Schema initialized")


@main.command()
@click.option("--airport", "-a", default=None, help="Filter by ICAO airport code")
def stats(airport: Optional[str]):
    """Show statistics about the current graph."""
    if not verify_connection():
        click.echo("✗ Failed to connect to Neo4j")
        raise SystemExit(1)

    graph_stats = get_graph_stats(airport)

    if airport:
        click.echo(f"Statistics for {airport}:")
    else:
        click.echo("Statistics for all airports:")

    click.echo(f"  Total nodes: {graph_stats['total_nodes']}")
    click.echo(f"  Total connections: {graph_stats['total_connections']}")

    if graph_stats['nodes_by_type']:
        click.echo("\n  Nodes by type:")
        for node_type, count in graph_stats['nodes_by_type'].items():
            click.echo(f"    {node_type}: {count}")


@main.command()
@click.option("--airport", "-a", default=None, help="Only clear data for this airport")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def clear(airport: Optional[str], yes: bool):
    """Clear nodes and relationships from the database."""
    if not verify_connection():
        click.echo("✗ Failed to connect to Neo4j")
        raise SystemExit(1)

    if airport:
        msg = f"This will delete all data for {airport}. Are you sure?"
    else:
        msg = "This will delete ALL data. Are you sure?"

    if not yes and not click.confirm(msg):
        click.echo("Aborted.")
        return

    clear_database(airport)
    if airport:
        click.echo(f"✓ Data for {airport} cleared")
    else:
        click.echo("✓ Database cleared")


@main.command("airports")
def list_airports_cmd():
    """List all airports in the database."""
    if not verify_connection():
        click.echo("✗ Failed to connect to Neo4j")
        raise SystemExit(1)

    airports = list_airports()
    if airports:
        click.echo("Airports in database:")
        for airport in airports:
            click.echo(f"  {airport}")
    else:
        click.echo("No airports in database.")


if __name__ == "__main__":
    main()
