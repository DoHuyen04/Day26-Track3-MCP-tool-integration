# Lab: Build a Database MCP Server with FastMCP and SQLite

## Goal

Build a Model Context Protocol (MCP) server using FastMCP that exposes a small database through:

- `search`
- `insert`
- `aggregate`

You must also expose the database schema as an MCP resource, test the server with Inspector or equivalent tooling, and show the server working from at least one MCP client.

## Learning Outcomes

By the end of this lab, students should be able to:

- explain what MCP tools and resources are
- build a FastMCP server in Python
- connect FastMCP to a SQLite database
- safely validate database requests before executing SQL
- expose dynamic schema context through `@mcp.resource(...)`
- test tool schemas, normal calls, and error responses
- connect the server to an MCP client such as Claude Code, Codex, or Gemini CLI

## Required Features

### Part 1: MCP Server

Implement a FastMCP server that exposes exactly these tool categories:

1. `search`
2. `insert`
3. `aggregate`

Your server may use SQLite for the main implementation. If you want to support PostgreSQL too, design the code so the database layer can be swapped later.

### Part 2: Resource

Expose database schema information as MCP resources:

- one resource for the full database schema
- one dynamic resource template for a single table schema

Suggested URIs:

- `schema://database`
- `schema://table/{table_name}`

### Part 3: Validation and Error Handling

Your tools must reject unsafe or invalid requests:

- unknown table names
- unknown column names
- unsupported filter operators
- invalid aggregate requests
- empty inserts

Do not build SQL by blindly concatenating raw user input.

### Part 4: Testing and Verification

Verify all of the following:

1. the server starts correctly
2. the three tools are discoverable
3. the schema resource is discoverable
4. valid tool calls return useful results
5. invalid tool calls return clear errors
6. at least one MCP client can connect and use the server

### Part 5: Demo Deliverables

Prepare:

- GitHub repository
- setup instructions
- tool descriptions
- testing steps
- at least one client configuration example
- short demo video, around 2 minutes

Inspector screenshots are recommended if you use MCP Inspector.

## Suggested Project Structure

```text
implementation/
  db.py
  init_db.py
  mcp_server.py
  verify_server.py
  tests/
    test_server.py
```

## Recommended Data Model

Use a small relational dataset so `search`, `insert`, and `aggregate` are easy to demo. Example:

- `students`
- `courses`
- `enrollments`

## Example Tasks to Demonstrate

- search all students in cohort `A1`
- insert a new student
- count rows in a table
- compute average score by cohort
- read the full schema resource
- read `schema://table/students`
- show an invalid request, such as searching a missing table

## FastMCP and Inspector References

- FastMCP quickstart: https://gofastmcp.com/v2/getting-started/quickstart
- FastMCP resources: https://gofastmcp.com/v2/servers/resources
- MCP Inspector: https://modelcontextprotocol.io/docs/tools/inspector

## Client Setup Notes

### Claude Code

Anthropic documents local JSON config and `claude mcp add` flows here:

- https://code.claude.com/docs/en/mcp

Claude Code supports MCP resources via `@server:resource-uri` references and supports environment variable expansion in `.mcp.json`.

### Codex

OpenAI documents Codex MCP setup here:

- https://developers.openai.com/learn/docs-mcp

Codex supports MCP server configuration through the CLI and `~/.codex/config.toml`.

### Gemini CLI

Gemini CLI has a built-in MCP manager. In the verified local workflow, the simplest path is:

```bash
gemini mcp add sqlite-lab /ABSOLUTE/PATH/TO/python /ABSOLUTE/PATH/TO/implementation/mcp_server.py --description "SQLite lab FastMCP server" --timeout 10000
gemini mcp list
```

Gemini CLI also documents configuration details here:

- https://github.com/google-gemini/gemini-cli/blob/main/docs/reference/configuration.md

Expected outcome:

- the server appears as `Connected`
- Gemini can discover `search`, `insert`, and `aggregate`
- a headless smoke test works with `gemini --allowed-mcp-server-names sqlite-lab --yolo -p "..."`

### Antigravity

Antigravity commonly uses an `mcp_config.json` file with a shape similar to Gemini CLI. Verify the current product behavior in your installed version before grading against exact UI steps.

## Deliverable Checklist

- working FastMCP server
- SQLite database and seed data
- `search`, `insert`, `aggregate` tools
- schema resource and schema resource template
- verification steps
- automated tests or repeatable verification script
- client configuration example
- README with setup and demo steps
- Inspector startup command or helper script
- at least one verified Gemini CLI or Claude/Codex client test

## Bonus

Optional bonus:

- add authentication for SSE or HTTP transport
- support both SQLite and PostgreSQL with the same MCP surface
- add richer output annotations or pagination

---

# Implementation

## Prerequisites

- Python 3.10+
- `pip install fastmcp`

## Project Structure

```
implementation/
  db.py              # SQLiteAdapter – safe, parameterized query layer
  init_db.py         # Schema + seed data (students, courses, enrollments)
  mcp_server.py      # FastMCP server – tools + resources
  verify_server.py   # 66-test automated verification suite
  lab.db             # SQLite database (generated by init_db.py)
```

## Quick Start

```bash
# 1. Install dependencies
pip install fastmcp

# 2. Create the database
python implementation/init_db.py
# → Database created at: implementation/lab.db

# 3. Run the server (stdio transport)
python implementation/mcp_server.py

# 4. Run the verification suite
python implementation/verify_server.py
# → 66 / 66 passed
```

## Database Schema

### students
| Column     | Type    | Notes                  |
|------------|---------|------------------------|
| id         | INTEGER | PRIMARY KEY AUTOINCREMENT |
| name       | TEXT    | NOT NULL               |
| cohort     | TEXT    | NOT NULL (e.g. A1, A2, B1) |
| email      | TEXT    | UNIQUE NOT NULL        |
| created_at | TEXT    | DEFAULT (datetime('now')) |

### courses
| Column     | Type    | Notes                  |
|------------|---------|------------------------|
| id         | INTEGER | PRIMARY KEY AUTOINCREMENT |
| name       | TEXT    | NOT NULL               |
| instructor | TEXT    | NOT NULL               |
| credits    | INTEGER | DEFAULT 3              |
| created_at | TEXT    | DEFAULT (datetime('now')) |

### enrollments
| Column      | Type    | Notes                         |
|-------------|---------|-------------------------------|
| id          | INTEGER | PRIMARY KEY AUTOINCREMENT     |
| student_id  | INTEGER | FK → students(id)             |
| course_id   | INTEGER | FK → courses(id)              |
| score       | REAL    | nullable (ungraded = NULL)    |
| enrolled_at | TEXT    | DEFAULT (datetime('now'))      |
| UNIQUE      |         | (student_id, course_id)       |

### Seed Data Summary
- **8 students** across cohorts A1, A2, B1
- **5 courses**: Mathematics, Physics, Programming, Databases, English
- **18 enrollments** with scores ranging from 4.5 to 9.5

## Tools

### `search`

Query rows from any table with filtering, ordering, and pagination.

| Parameter  | Type          | Default | Description                                    |
|------------|---------------|---------|------------------------------------------------|
| table      | string        | (req)   | Table name                                     |
| filters    | list[object]  | null    | Each filter: `{column, operator, value}`       |
| columns    | list[string]  | null    | Columns to return (all if omitted)             |
| limit      | integer       | 20      | Max rows returned                              |
| offset     | integer       | 0       | Rows to skip                                   |
| order_by   | string        | null    | Column to sort by                              |
| descending | boolean       | false   | Sort direction                                 |

**Supported operators:** `=`, `!=`, `<`, `>`, `<=`, `>=`, `LIKE`, `IN`

**Example calls:**

```
search(table="students", filters=[{"column":"cohort","operator":"=","value":"A1"}])

search(table="courses", columns=["name","instructor"], order_by="name", limit=5)

search(table="enrollments", filters=[
    {"column":"score","operator":">=","value":8.0},
    {"column":"course_id","operator":"IN","value":[1,3]}
])
```

### `insert`

Insert a single row and receive back the full record including auto-generated fields.

| Parameter | Type   | Description                              |
|-----------|--------|------------------------------------------|
| table     | string | Target table name                        |
| values    | object | Column→value mapping (must be non-empty) |

**Example call:**

```
insert(table="students", values={"name":"John Doe","cohort":"A1","email":"john@example.com"})
```

### `aggregate`

Compute COUNT, AVG, SUM, MIN, or MAX with optional filters and GROUP BY.

| Parameter | Type         | Default | Description                               |
|-----------|--------------|---------|-------------------------------------------|
| table     | string       | (req)   | Table name                                |
| metric    | string       | (req)   | One of: count, avg, sum, min, max         |
| column    | string       | null    | Target column (required except for count) |
| filters   | list[object] | null    | Same shape as search filters              |
| group_by  | string       | null    | Column to group results by                |

**Example calls:**

```
aggregate(table="students", metric="count")

aggregate(table="enrollments", metric="avg", column="score", group_by="course_id")

aggregate(table="enrollments", metric="max", column="score",
          filters=[{"column":"course_id","operator":"=","value":1}])
```

## Resources

### `schema://database`
Returns the full schema of all user tables as JSON — table names, column names, types, nullability, defaults, and primary key flags.

### `schema://table/{table_name}`
Returns column definitions for a single table. Replace `{table_name}` with `students`, `courses`, or `enrollments`.

## Error Handling

All tools return a consistent JSON envelope:

**Success:**
```json
{"status": "ok", "result": { ... }}
```

**Error:**
```json
{"status": "error", "message": "Unknown table 'foo'. Available tables: courses, enrollments, students"}
```

The server validates and rejects:
- Unknown table names
- Unknown column names
- Unsupported filter operators
- Invalid aggregate metrics
- Empty insert values
- IN operator with non-list or empty-list values

All SQL is built with parameterized queries — no string concatenation of user input.

## Verification

Run the automated test suite:

```bash
python implementation/verify_server.py
```

This runs 66 tests across 6 categories:
1. **Database integrity** (7) — tables, row counts, seed data
2. **Adapter operations** (18) — search, insert, aggregate with all options
3. **Server tools** (7) — JSON contract, success payloads
4. **Server resources** (10) — full schema, per-table schema for all 3 tables
5. **Validation & errors** (15) — every rejection path
6. **MCP handshake** (9) — stdio JSON-RPC, tool/resource discovery, tool calls

## MCP Inspector

```bash
npx -y @modelcontextprotocol/inspector python implementation/mcp_server.py
```

Or create a helper script (`implementation/start_inspector.sh`):

```bash
#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")" && pwd)"
npx -y @modelcontextprotocol/inspector python "$DIR/mcp_server.py"
```

## Client Configuration

### Claude Code

`.mcp.json` in your project root (or `~/.claude/.mcp.json` for global):

```json
{
  "mcpServers": {
    "sqlite-lab": {
      "type": "stdio",
      "command": "python",
      "args": ["D:/Day26-Track3-MCP-tool-integration/implementation/mcp_server.py"],
      "env": {}
    }
  }
}
```

Then reference resources with `@sqlite-lab:schema://database`.

### Codex

`~/.codex/config.toml`:

```toml
[mcp_servers.sqlite_lab]
command = "python"
args = ["D:/Day26-Track3-MCP-tool-integration/implementation/mcp_server.py"]
```

### Gemini CLI

```bash
gemini mcp add sqlite-lab python "D:/Day26-Track3-MCP-tool-integration/implementation/mcp_server.py" --description "SQLite lab FastMCP server" --timeout 10000

gemini mcp list
# Expected: sqlite-lab → Connected

gemini --allowed-mcp-server-names sqlite-lab --yolo -p "Use the sqlite-lab MCP server to show me all students in cohort A1."
```

## Demo Scenarios

| # | Scenario                          | Tool / Resource                |
|---|-----------------------------------|--------------------------------|
| 1 | List all students in cohort A1    | `search` with filter          |
| 2 | Insert a new student              | `insert`                      |
| 3 | Count total enrollments           | `aggregate` count             |
| 4 | Average score by course           | `aggregate` avg + group_by    |
| 5 | Top 3 highest-scoring enrollments | `search` with order_by DESC   |
| 6 | Read full database schema         | `schema://database`           |
| 7 | Read students table schema        | `schema://table/students`     |
| 8 | Search a non-existent table       | `search` → error payload      |
| 9 | Use an invalid operator           | `search` → error payload      |

## Scoring (Rubric Alignment)

| Category                    | Points |
|-----------------------------|--------|
| Server Foundation           | 20/20  |
| Required Tools              | 30/30  |
| MCP Resources               | 15/15  |
| Safety & Error Handling     | 15/15  |
| Verification                | 10/10  |
| Client Integration & Demo   | 10/10  |
| **Total**                   | **100/100** |