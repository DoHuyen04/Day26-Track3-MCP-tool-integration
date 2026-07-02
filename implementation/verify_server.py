"""Comprehensive verification script for the MCP SQLite Lab server.

Run from the project root:
    python implementation/verify_server.py

The script tests:
    1. Database integrity       – tables exist, seed data is present
    2. Adapter operations       – search, insert, aggregate
    3. Server tools             – JSON contract, success payloads
    4. Server resources         – full schema, per-table schema template
    5. Validation & errors      – every rejection path
    6. MCP client connectivity  – stdio handshake (optional)
"""

import json
import os
import subprocess
import sys
import time

# Ensure we can import from the implementation directory.
_IMPL_DIR = os.path.dirname(os.path.abspath(__file__))
if _IMPL_DIR not in sys.path:
    sys.path.insert(0, _IMPL_DIR)

from db import SQLiteAdapter, ValidationError
from init_db import create_database

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

PASS = 0
FAIL = 0


def check(label, condition, detail=""):
    """Assert *condition* is truthy, report PASS or FAIL."""
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        suffix = f"  -- {detail}" if detail else ""
        print(f"  FAIL  {label}{suffix}")


def ok(data):
    """Return True when *data* has ``status: ok``."""
    return data.get("status") == "ok"


def errored(data, fragment=None):
    """Return True when *data* has ``status: error`` and contains *fragment*."""
    if data.get("status") != "error":
        return False
    if fragment and fragment.lower() not in data.get("message", "").lower():
        return False
    return True


# ---------------------------------------------------------------------------
# 1. Database integrity
# ---------------------------------------------------------------------------

def test_database():
    print("\n-- 1. Database integrity --")
    adapter = SQLiteAdapter()

    check("database file exists",
          os.path.isfile(adapter.db_path),
          f"missing {adapter.db_path}")

    check("three user tables: courses, enrollments, students",
          adapter.list_tables() == ["courses", "enrollments", "students"],
          f"got: {adapter.list_tables()}")

    check("students has 8 rows",
          len(adapter.search("students")["rows"]) == 8)

    check("courses has 5 rows",
          len(adapter.search("courses")["rows"]) == 5)

    check("enrollments has 18 rows",
          len(adapter.search("enrollments")["rows"]) == 18)

    names = {r["name"] for r in adapter.search("students")["rows"]}
    check("seed student Alice Nguyen present", "Alice Nguyen" in names)
    check("seed student Carol Le present", "Carol Le" in names)

    adapter.close()


# ---------------------------------------------------------------------------
# 2. Adapter operations
# ---------------------------------------------------------------------------

def test_adapter():
    print("\n-- 2. Adapter operations --")
    db = SQLiteAdapter()

    # -- search --
    r = db.search("students")
    check("search returns expected keys",
          set(r.keys()) == {"rows", "count", "table", "limit", "offset"},
          f"keys: {set(r.keys())}")

    r = db.search("students", filters=[
        {"column": "cohort", "operator": "=", "value": "A1"}
    ])
    check("search filter cohort=A1 returns 3 rows", r["count"] == 3)

    check("search limit=2 returns 2 rows",
          db.search("students", limit=2)["count"] == 2)

    r = db.search("students", columns=["name", "cohort"])
    check("search with columns returns only those columns",
          set(r["rows"][0].keys()) == {"name", "cohort"})

    check("search order_by name ASC first is Alice Nguyen",
          db.search("students", order_by="name")["rows"][0]["name"] == "Alice Nguyen")

    check("search order_by name DESC first is Hank Bui",
          db.search("students", order_by="name", descending=True)["rows"][0]["name"] == "Hank Bui")

    r = db.search("courses", filters=[
        {"column": "name", "operator": "IN", "value": ["Mathematics", "Physics"]}
    ])
    check("search filter IN operator", r["count"] == 2)

    r = db.search("students", filters=[
        {"column": "name", "operator": "LIKE", "value": "Alice%"}
    ])
    check("search LIKE operator", r["count"] == 1)

    # -- insert --
    result = db.insert("students", {"name": "Verify User", "cohort": "V1", "email": "verify@test.com"})
    check("insert returns id > 0", result["id"] > 0)
    check("insert returns row with generated fields",
          "created_at" in result["row"],
          f"row: {result['row']}")
    check("inserted row is queryable",
          db.search("students", filters=[
              {"column": "email", "operator": "=", "value": "verify@test.com"}
          ])["count"] == 1)

    # -- aggregate --
    check("aggregate count students = 9 (8 seed + 1 verify)",
          db.aggregate("students", "count")["rows"][0]["value"] == 9)

    check("aggregate avg score returns float",
          isinstance(db.aggregate("enrollments", "avg", column="score")["rows"][0]["value"], float))

    check("aggregate min score is 4.5",
          db.aggregate("enrollments", "min", column="score")["rows"][0]["value"] == 4.5)

    check("aggregate max score is 9.5",
          db.aggregate("enrollments", "max", column="score")["rows"][0]["value"] == 9.5)

    check("aggregate sum scores > 0",
          db.aggregate("enrollments", "sum", column="score")["rows"][0]["value"] > 0)

    check("aggregate group_by returns 8 rows",
          len(db.aggregate("enrollments", "avg", column="score", group_by="student_id")["rows"]) == 8)

    r = db.aggregate("enrollments", "count", filters=[
        {"column": "score", "operator": ">=", "value": 9.0}
    ])
    check("aggregate with filter (score >= 9.0) returns 4",
          r["rows"][0]["value"] == 4)

    db.close()


# ---------------------------------------------------------------------------
# 3. Server tools (JSON contract)
# ---------------------------------------------------------------------------

def test_server_tools():
    print("\n-- 3. Server tools --")
    from mcp_server import search, insert, aggregate

    r = json.loads(search(table="students"))
    check("search tool returns status=ok", ok(r))
    check("search tool returns rows (at least 8 seed rows)",
          len(r["result"]["rows"]) >= 8)

    r = json.loads(search(table="students", columns=["name", "email"], limit=3))
    check("search tool with columns and limit",
          len(r["result"]["rows"]) == 3 and set(r["result"]["rows"][0].keys()) == {"name", "email"})

    r = json.loads(insert(table="students", values={
        "name": "Tool User", "cohort": "T1", "email": "tool@test.com"
    }))
    check("insert tool returns status=ok", ok(r))
    check("insert tool returns id", r["result"]["id"] is not None)

    r = json.loads(aggregate(table="enrollments", metric="count"))
    check("aggregate tool count = 18", ok(r) and r["result"]["rows"][0]["value"] == 18)

    r = json.loads(aggregate(table="enrollments", metric="avg", column="score"))
    check("aggregate tool avg OK", ok(r))


# ---------------------------------------------------------------------------
# 4. Server resources
# ---------------------------------------------------------------------------

def test_server_resources():
    print("\n-- 4. Server resources --")
    from mcp_server import database_schema, table_schema

    r = json.loads(database_schema())
    check("database_schema has tables key", "tables" in r)
    check("database_schema has resource key", "resource" in r)
    check("database_schema lists 3 tables",
          set(r["tables"].keys()) == {"courses", "enrollments", "students"})
    check("database_schema students has 5 columns",
          len(r["tables"]["students"]) == 5)

    for tbl in ["students", "courses", "enrollments"]:
        r = json.loads(table_schema(table_name=tbl))
        check(f"table_schema({tbl}) correct table name", r.get("table") == tbl)
        check(f"table_schema({tbl}) has columns list",
              isinstance(r.get("columns"), list) and len(r["columns"]) > 0)


# ---------------------------------------------------------------------------
# 5. Validation & error handling
# ---------------------------------------------------------------------------

def test_validation():
    print("\n-- 5. Validation & error handling --")
    from mcp_server import search, insert, aggregate, table_schema

    # Unknown table
    check("reject unknown table in search",
          errored(json.loads(search(table="nope"))))
    check("reject unknown table in insert",
          errored(json.loads(insert(table="nope", values={"x": 1}))))
    check("reject unknown table in aggregate",
          errored(json.loads(aggregate(table="nope", metric="count"))))
    check("reject unknown table in resource",
          errored(json.loads(table_schema(table_name="nope"))))

    # Unknown column
    check("reject unknown column in search columns",
          errored(json.loads(search(table="students", columns=["ghost"]))))
    check("reject unknown column in filter",
          errored(json.loads(search(table="students", filters=[
              {"column": "ghost", "operator": "=", "value": 1}
          ]))))
    check("reject unknown column in insert",
          errored(json.loads(insert(table="students", values={"ghost": 1}))))
    check("reject unknown column in aggregate",
          errored(json.loads(aggregate(table="students", metric="avg", column="ghost"))))
    check("reject unknown column in order_by",
          errored(json.loads(search(table="students", order_by="ghost"))))

    # Bad operator
    check("reject unsupported operator",
          errored(json.loads(search(table="students", filters=[
              {"column": "name", "operator": "DROP TABLE", "value": "x"}
          ]))))

    # Bad metric
    check("reject unsupported metric",
          errored(json.loads(aggregate(table="students", metric="median"))))
    check("require column for avg",
          errored(json.loads(aggregate(table="students", metric="avg"))))

    # Empty insert
    check("reject empty insert values",
          errored(json.loads(insert(table="students", values={}))))

    # IN edge cases
    check("reject IN with scalar value",
          errored(json.loads(search(table="students", filters=[
              {"column": "name", "operator": "IN", "value": "Alice"}
          ]))))
    check("reject IN with empty list",
          errored(json.loads(search(table="students", filters=[
              {"column": "name", "operator": "IN", "value": []}
          ]))))


# ---------------------------------------------------------------------------
# 6. MCP client connectivity (stdio smoke test)
# ---------------------------------------------------------------------------

def test_mcp_handshake():
    print("\n-- 6. MCP client connectivity --")
    server_script = os.path.join(_IMPL_DIR, "mcp_server.py")
    python_exe = sys.executable

    try:
        proc = subprocess.Popen(
            [python_exe, server_script],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Send an initialize request (JSON-RPC 2.0 over stdio).
        init_request = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "verify_server", "version": "1.0.0"},
            },
        }) + "\n"

        proc.stdin.write(init_request)
        proc.stdin.flush()

        line = proc.stdout.readline()
        response = json.loads(line)

        check("MCP initialize handshake succeeded",
              "result" in response,
              f"unexpected: {response}")

        server_name = response.get("result", {}).get("serverInfo", {}).get("name", "")
        check("server reports correct name",
              server_name == "SQLite Lab MCP Server",
              f"name: {server_name}")

        # Send initialized notification.
        initialized = json.dumps({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        }) + "\n"
        proc.stdin.write(initialized)
        proc.stdin.flush()
        time.sleep(0.1)

        # List tools.
        list_tools_req = json.dumps({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        }) + "\n"
        proc.stdin.write(list_tools_req)
        proc.stdin.flush()
        line = proc.stdout.readline()
        tools_resp = json.loads(line)

        tool_names = [t["name"] for t in tools_resp.get("result", {}).get("tools", [])]
        check("tools/list includes search", "search" in tool_names)
        check("tools/list includes insert", "insert" in tool_names)
        check("tools/list includes aggregate", "aggregate" in tool_names)

        # List resources.
        list_res_req = json.dumps({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "resources/list",
            "params": {},
        }) + "\n"
        proc.stdin.write(list_res_req)
        proc.stdin.flush()
        line = proc.stdout.readline()
        res_resp = json.loads(line)

        resource_uris = [r["uri"] for r in res_resp.get("result", {}).get("resources", [])]
        check("resources/list includes schema://database",
              "schema://database" in resource_uris)

        # Resource templates are in a separate endpoint in FastMCP v3.
        list_tmpl_req = json.dumps({
            "jsonrpc": "2.0",
            "id": 31,
            "method": "resources/templates/list",
            "params": {},
        }) + "\n"
        proc.stdin.write(list_tmpl_req)
        proc.stdin.flush()
        line = proc.stdout.readline()
        tmpl_resp = json.loads(line)

        tmpl_uris = [t["uriTemplate"] for t in tmpl_resp.get("result", {}).get("resourceTemplates", [])]
        check("resource templates includes schema://table/{table_name}",
              any("schema://table/" in u for u in tmpl_uris))

        # Call a tool with valid arguments.
        call_tool_req = json.dumps({
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "search",
                "arguments": {"table": "students", "limit": 2},
            },
        }) + "\n"
        proc.stdin.write(call_tool_req)
        proc.stdin.flush()
        line = proc.stdout.readline()
        call_resp = json.loads(line)
        check("tools/call search succeeded",
              "result" in call_resp,
              f"unexpected: {call_resp}")

        # Call a tool with invalid table (still succeeds at MCP level;
        # the error is inside the tool's return payload).
        call_bad_req = json.dumps({
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "search",
                "arguments": {"table": "nonexistent"},
            },
        }) + "\n"
        proc.stdin.write(call_bad_req)
        proc.stdin.flush()
        line = proc.stdout.readline()
        bad_resp = json.loads(line)

        content = bad_resp.get("result", {}).get("content", [{}])
        text = content[0].get("text", "") if content else ""
        check("invalid tool call returns error payload",
              "error" in text.lower(),
              f"got: {text[:100]}")

        proc.terminate()
        proc.wait(timeout=5)

    except FileNotFoundError:
        check("MCP handshake spawn", False, "could not spawn mcp_server.py")
    except Exception as exc:
        check(f"MCP handshake", False, str(exc))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  MCP SQLite Lab - Verification Suite")
    print("=" * 60)

    # Always start from a clean database.
    create_database()
    print("  (database reset)")

    test_database()
    test_adapter()
    test_server_tools()
    test_server_resources()
    test_validation()
    test_mcp_handshake()

    total = PASS + FAIL
    print(f"\n{'=' * 60}")
    print(f"  Results: {PASS} / {total} passed")
    if FAIL:
        print(f"           {FAIL} FAILURES")
        print(f"{'=' * 60}")
        return False
    else:
        print(f"  All tests passed!")
        print(f"{'=' * 60}")
        return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
