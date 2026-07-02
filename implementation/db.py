"""SQLite adapter with safe, parameterized query execution."""

import sqlite3
import os


class ValidationError(Exception):
    """Raised when a request cannot be safely executed."""


ALLOWED_METRICS = {"count", "avg", "sum", "min", "max"}
ALLOWED_OPERATORS = {"=", "!=", "<", ">", "<=", ">=", "LIKE", "IN"}


class SQLiteAdapter:
    """Safe wrapper around a SQLite database for use by the MCP server."""

    def __init__(self, db_path=None):
        if db_path is None:
            db_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(db_dir, "lab.db")
        self.db_path = db_path
        self._conn = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self):
        """Open (or reuse) a SQLite connection with row_factory enabled.

        ``check_same_thread=False`` is required because FastMCP may invoke
        tool handlers from a thread pool rather than the main thread.
        """
        if self._conn is None:
            self._conn = sqlite3.connect(
                self.db_path, check_same_thread=False
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Schema introspection
    # ------------------------------------------------------------------

    def list_tables(self):
        """Return the names of all user-created tables."""
        conn = self.connect()
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()
        return [r["name"] for r in rows]

    def get_table_schema(self, table):
        """Return column definitions for a single table.

        Returns a list of dicts, each with keys:
            cid, name, type, notnull, dflt_value, pk
        """
        self._validate_table(table)
        conn = self.connect()
        rows = conn.execute(f"PRAGMA table_info({self._quote_ident(table)})").fetchall()
        return [dict(r) for r in rows]

    def get_full_schema(self):
        """Return the schema of every user table as a dict keyed by table name."""
        tables = self.list_tables()
        return {t: self.get_table_schema(t) for t in tables}

    # ------------------------------------------------------------------
    # Column helpers
    # ------------------------------------------------------------------

    def _get_columns(self, table):
        """Return the list of column names for a table (cached per connection lifetime)."""
        schema = self.get_table_schema(table)
        return [col["name"] for col in schema]

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _validate_table(self, table):
        """Raise ValidationError if *table* is not a known user table."""
        allowed = self.list_tables()
        if table not in allowed:
            raise ValidationError(
                f"Unknown table '{table}'. Available tables: {', '.join(allowed)}"
            )

    def _validate_columns(self, table, columns):
        """Raise ValidationError if any column name is unknown."""
        allowed = self._get_columns(table)
        for col in columns:
            if col not in allowed:
                raise ValidationError(
                    f"Unknown column '{col}' in table '{table}'. "
                    f"Available columns: {', '.join(allowed)}"
                )

    def _validate_metric(self, metric):
        m = metric.lower().strip()
        if m not in ALLOWED_METRICS:
            raise ValidationError(
                f"Unsupported metric '{metric}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_METRICS))}"
            )
        return m

    def _validate_operator(self, operator):
        op = operator.strip()
        if op.upper() == "IN":
            return "IN"
        if op not in ALLOWED_OPERATORS:
            raise ValidationError(
                f"Unsupported operator '{operator}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_OPERATORS))}"
            )
        return op

    # ------------------------------------------------------------------
    # Safe SQL builders
    # ------------------------------------------------------------------

    @staticmethod
    def _quote_ident(identifier):
        """Double-quote an identifier for safe embedding in SQL."""
        # SQLite accepts double-quoted identifiers by default.
        return f'"{identifier}"'

    def _build_where(self, table, filters, params_out):
        """Build a WHERE clause from a list of filter dicts.

        Each filter dict expects: {"column": str, "operator": str, "value": any}
        Returns the WHERE clause string (without the word WHERE).  Appends
        bound values to *params_out* in order.
        """
        if not filters:
            return "1=1"

        clauses = []
        for f in filters:
            col = f["column"]
            op = self._validate_operator(f["operator"]).upper()
            value = f["value"]

            self._validate_columns(table, [col])
            quoted_col = self._quote_ident(col)

            if op == "IN":
                if not isinstance(value, list) or len(value) == 0:
                    raise ValidationError("IN operator requires a non-empty list of values.")
                placeholders = ", ".join("?" for _ in value)
                clauses.append(f"{quoted_col} IN ({placeholders})")
                params_out.extend(value)
            else:
                clauses.append(f"{quoted_col} {op} ?")
                params_out.append(value)

        return " AND ".join(clauses)

    # ------------------------------------------------------------------
    # Public operations
    # ------------------------------------------------------------------

    def search(self, table, columns=None, filters=None, limit=20, offset=0,
               order_by=None, descending=False):
        """Execute a parameterized SELECT and return matching rows.

        Args:
            table:      table name (required)
            columns:    list of column names or None for *
            filters:    list of {"column", "operator", "value"} dicts
            limit:      max rows to return (default 20)
            offset:     number of rows to skip (default 0)
            order_by:   column to sort by (optional)
            descending: True for DESC order

        Returns:
            dict with keys: rows, count, table, limit, offset
        """
        self._validate_table(table)
        cols = columns if columns else self._get_columns(table)
        self._validate_columns(table, cols)

        params = []
        where = self._build_where(table, filters or [], params)
        col_list = ", ".join(self._quote_ident(c) for c in cols)
        order_clause = ""
        if order_by:
            self._validate_columns(table, [order_by])
            direction = "DESC" if descending else "ASC"
            order_clause = f" ORDER BY {self._quote_ident(order_by)} {direction}"

        sql = (
            f"SELECT {col_list} FROM {self._quote_ident(table)} "
            f"WHERE {where}{order_clause} LIMIT ? OFFSET ?"
        )
        params.extend([limit, offset])

        conn = self.connect()
        rows = conn.execute(sql, params).fetchall()

        return {
            "rows": [dict(r) for r in rows],
            "count": len(rows),
            "table": table,
            "limit": limit,
            "offset": offset,
        }

    def insert(self, table, values):
        """Insert a row and return the inserted payload including generated ID.

        Args:
            table:  table name
            values: dict of column -> value

        Returns:
            dict with keys: id (rowid), row, table
        """
        self._validate_table(table)
        if not values:
            raise ValidationError("Insert values must not be empty.")

        columns = list(values.keys())
        self._validate_columns(table, columns)

        placeholders = ", ".join("?" for _ in columns)
        col_list = ", ".join(self._quote_ident(c) for c in columns)

        sql = f"INSERT INTO {self._quote_ident(table)} ({col_list}) VALUES ({placeholders})"
        params = [values[c] for c in columns]

        conn = self.connect()
        cur = conn.execute(sql, params)
        conn.commit()

        rowid = cur.lastrowid
        # Fetch the row we just inserted so the caller can see defaults
        row = conn.execute(
            f"SELECT * FROM {self._quote_ident(table)} WHERE rowid = ?", (rowid,)
        ).fetchone()

        return {
            "id": rowid,
            "row": dict(row) if row else values,
            "table": table,
        }

    def aggregate(self, table, metric, column=None, filters=None, group_by=None):
        """Execute an aggregate query (COUNT / AVG / SUM / MIN / MAX).

        Args:
            table:    table name
            metric:   one of count / avg / sum / min / max
            column:   target column (required for all metrics except count)
            filters:  list of filter dicts (same shape as search)
            group_by: optional column to group by

        Returns:
            dict with keys: rows, metric, table
        """
        self._validate_table(table)
        m = self._validate_metric(metric)

        params = []
        where = self._build_where(table, filters or [], params)

        if m == "count":
            col_expr = "COUNT(*)"
        else:
            if column is None:
                raise ValidationError(
                    f"Metric '{m}' requires a column name."
                )
            self._validate_columns(table, [column])
            col_expr = f"{m.upper()}({self._quote_ident(column)})"

        group_clause = ""
        select_cols = [f"{col_expr} AS value"]
        if group_by:
            self._validate_columns(table, [group_by])
            select_cols.insert(0, f"{self._quote_ident(group_by)} AS grp")
            group_clause = f" GROUP BY {self._quote_ident(group_by)}"

        sql = (
            f"SELECT {', '.join(select_cols)} "
            f"FROM {self._quote_ident(table)} "
            f"WHERE {where}{group_clause}"
        )

        conn = self.connect()
        rows = conn.execute(sql, params).fetchall()

        return {
            "rows": [dict(r) for r in rows],
            "metric": m,
            "table": table,
        }
