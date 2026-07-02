"""FastMCP server exposing search, insert, aggregate tools and schema resources."""

import json
import os
import sys

from fastmcp import FastMCP

# Ensure the implementation directory is on the import path so db can be
# imported regardless of where the server script is invoked from.
_IMPL_DIR = os.path.dirname(os.path.abspath(__file__))
if _IMPL_DIR not in sys.path:
    sys.path.insert(0, _IMPL_DIR)

from db import SQLiteAdapter, ValidationError

# ---------------------------------------------------------------------------
# Server initialisation
# ---------------------------------------------------------------------------

mcp = FastMCP("SQLite Lab MCP Server")

# Point the adapter at the default database file alongside this script.
_db_path = os.path.join(_IMPL_DIR, "lab.db")
adapter = SQLiteAdapter(_db_path)


# ---------------------------------------------------------------------------
# Helper – safe JSON serialisation
# ---------------------------------------------------------------------------

def _json(data):
    """Return a pretty-printed JSON string for the given data."""
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


def _ok(payload):
    """Wrap a successful result."""
    return _json({"status": "ok", **payload})


def _error(message):
    """Wrap an error result."""
    return _json({"status": "error", "message": message})


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool
def search(
    table: str,
    filters: list | None = None,
    columns: list | None = None,
    limit: int = 20,
    offset: int = 0,
    order_by: str | None = None,
    descending: bool = False,
) -> str:
    """Search rows in a database table with optional filtering, ordering, and pagination.

    Args:
        table:      Name of the table to query (e.g. 'students', 'courses', 'enrollments').
        filters:    Optional list of filter objects. Each filter must have:
                      - column   (str)  – column name
                      - operator (str)  – one of =, !=, <, >, <=, >=, LIKE, IN
                      - value    (any)  – the value to compare against (list for IN)
        columns:    Columns to return (list of strings). Returns all columns when omitted.
        limit:      Maximum number of rows to return (default 20).
        offset:     Number of rows to skip before returning results (default 0).
        order_by:   Column name to sort by (optional).
        descending: Set to true for descending sort order (default false).
    """
    try:
        result = adapter.search(
            table=table,
            columns=columns,
            filters=filters,
            limit=limit,
            offset=offset,
            order_by=order_by,
            descending=descending,
        )
        return _ok({"result": result})
    except ValidationError as exc:
        return _error(str(exc))


@mcp.tool
def insert(table: str, values: dict) -> str:
    """Insert a new row into a table.

    Args:
        table:  Name of the target table.
        values: Dictionary of column names to their values (e.g. {"name": "John", "cohort": "A1"}).

    Returns the inserted row including any auto-generated fields such as id and created_at.
    """
    try:
        result = adapter.insert(table=table, values=values)
        return _ok({"result": result})
    except ValidationError as exc:
        return _error(str(exc))


@mcp.tool
def aggregate(
    table: str,
    metric: str,
    column: str | None = None,
    filters: list | None = None,
    group_by: str | None = None,
) -> str:
    """Compute an aggregate metric over a table.

    Args:
        table:    Name of the table to query.
        metric:   Aggregate function – one of count, avg, sum, min, max.
        column:   Target column (required for all metrics except 'count').
        filters:  Optional filter list (same shape as the search tool).
        group_by: Optional column to group results by.
    """
    try:
        result = adapter.aggregate(
            table=table,
            metric=metric,
            column=column,
            filters=filters,
            group_by=group_by,
        )
        return _ok({"result": result})
    except ValidationError as exc:
        return _error(str(exc))


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

@mcp.resource("schema://database")
def database_schema() -> str:
    """Return the full database schema for all tables as JSON.

    Includes table names, column names, data types, nullability, default
    values, and primary-key flags.
    """
    try:
        schema = adapter.get_full_schema()
        return _json({"resource": "schema://database", "tables": schema})
    except Exception as exc:
        return _error(str(exc))


@mcp.resource("schema://table/{table_name}")
def table_schema(table_name: str) -> str:
    """Return the schema for a single table as JSON.

    The table_name path parameter must match one of the existing tables
    (students, courses, or enrollments).
    """
    try:
        columns = adapter.get_table_schema(table_name)
        return _json({
            "resource": f"schema://table/{table_name}",
            "table": table_name,
            "columns": columns,
        })
    except ValidationError as exc:
        return _error(str(exc))
    except Exception as exc:
        return _error(str(exc))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Stdio transport by default – the standard mode for MCP clients.
    # For SSE / HTTP (bonus) pass --transport sse or --transport http.
    import argparse

    parser = argparse.ArgumentParser(description="SQLite Lab MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "http"],
        default="stdio",
        help="Transport protocol (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host for SSE/HTTP transport (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for SSE/HTTP transport (default: 8000)",
    )
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    elif args.transport == "sse":
        mcp.run(transport="sse", host=args.host, port=args.port)
    elif args.transport == "http":
        mcp.run(transport="http", host=args.host, port=args.port)
