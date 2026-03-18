#!/usr/bin/env python3
"""
Database Schema Extractor
Extracts table names, columns, and types from a SQLite database file.
Output is formatted for easy consumption by LLMs.
"""

import sqlite3
import sys
import argparse
from pathlib import Path


def get_table_info(cursor, table_name):
    """Get column information for a specific table."""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    return columns


def get_sample_rows(cursor, table_name, limit=5, max_col_width=100):
    """Get sample rows from a table with truncation for readability."""
    try:
        cursor.execute(f"SELECT * FROM {table_name} LIMIT {limit}")
        rows = cursor.fetchall()
        column_names = (
            [desc[0] for desc in cursor.description] if cursor.description else []
        )

        # Format rows with truncation
        formatted_rows = []
        for row in rows:
            row_dict = {}
            for col_name, value in zip(column_names, row):
                if value is None:
                    row_dict[col_name] = "NULL"
                elif isinstance(value, str) and len(value) > max_col_width:
                    row_dict[col_name] = value[:max_col_width] + "..."
                else:
                    row_dict[col_name] = value
            formatted_rows.append(row_dict)

        return formatted_rows, column_names
    except sqlite3.Error as e:
        return None, str(e)


def format_schema_for_llm(db_path, sample_limit=5, tables_filter="all"):
    """Extract and format database schema information."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get all table names
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        all_tables = cursor.fetchall()

        if not all_tables:
            return "No tables found in the database."

        # Parse the tables filter
        if tables_filter == "all":
            tables_to_process = [table[0] for table in all_tables]
        else:
            # Split comma-separated list and strip whitespace
            requested_tables = tables_filter.split(",")
            all_table_names = [table[0] for table in all_tables]

            # Filter to only include requested tables that exist in the database
            tables_to_process = [t for t in requested_tables if t in all_table_names]

            # Warn about tables that don't exist
            missing_tables = [t for t in requested_tables if t not in all_table_names]
            if missing_tables:
                print(
                    f"Warning: The following tables were not found: {', '.join(missing_tables)}",
                    file=sys.stderr,
                )

            if not tables_to_process:
                return f"None of the requested tables were found in the database.\nAvailable tables: {', '.join(all_table_names)}"

        output = []
        output.append(f"Database Schema: {Path(db_path).name}")
        output.append("=" * 80)
        output.append("")

        for table_name in tables_to_process:
            output.append(f"Table: {table_name}")
            output.append("-" * 40)

            # Get column information
            columns = get_table_info(cursor, table_name)

            if columns:
                output.append("Columns:")
                for col in columns:
                    cid, name, col_type, not_null, default_val, pk = col
                    constraints = []
                    if pk:
                        constraints.append("PRIMARY KEY")
                    if not_null:
                        constraints.append("NOT NULL")
                    if default_val is not None:
                        constraints.append(f"DEFAULT {default_val}")

                    constraint_str = (
                        f" ({', '.join(constraints)})" if constraints else ""
                    )
                    output.append(f"  - {name}: {col_type}{constraint_str}")
            else:
                output.append("  (No columns)")

            # Get row count
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = cursor.fetchone()[0]
                output.append(f"Row count: {count}")
            except sqlite3.Error:
                output.append("Row count: N/A")

            # Get sample rows
            if sample_limit > 0:
                sample_rows, col_names_or_error = get_sample_rows(
                    cursor, table_name, sample_limit
                )

                if sample_rows is None:
                    output.append(f"Sample data: Error - {col_names_or_error}")
                elif len(sample_rows) == 0:
                    output.append("Sample data: No data available")
                else:
                    output.append(f"Sample data (up to {sample_limit} rows):")
                    for idx, row in enumerate(sample_rows, 1):
                        output.append(f"  Row {idx}:")
                        for col_name, value in row.items():
                            # Format value for display
                            if isinstance(value, str) and len(str(value)) > 80:
                                value_str = repr(value[:80] + "...")
                            else:
                                value_str = repr(value)
                            output.append(f"    {col_name}: {value_str}")

            output.append("")

        conn.close()
        return "\n".join(output)

    except sqlite3.Error as e:
        return f"Error reading database: {e}"
    except Exception as e:
        return f"Unexpected error: {e}"


def main():
    parser = argparse.ArgumentParser(
        description="Extract schema information from a SQLite database file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s my_database.db
  %(prog)s /path/to/data.sqlite
  %(prog)s database.db > schema.txt
        """,
    )

    parser.add_argument("database", help="Path to the SQLite database file")

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Include additional details like foreign keys",
    )

    parser.add_argument(
        "-s",
        "--samples",
        type=int,
        default=5,
        metavar="N",
        help="Number of sample rows to display per table (default: 5, use 0 to disable)",
    )

    parser.add_argument(
        "-t",
        "--tables",
        type=str,
        default="all",
        help="Comma-separated list of tables to extract (default: all)",
    )

    args = parser.parse_args()

    # Check if file exists
    db_path = Path(args.database)
    if not db_path.exists():
        print(f"Error: Database file '{args.database}' not found.", file=sys.stderr)
        sys.exit(1)

    if not db_path.is_file():
        print(f"Error: '{args.database}' is not a file.", file=sys.stderr)
        sys.exit(1)

    # Extract and print schema
    schema_info = format_schema_for_llm(
        str(db_path), sample_limit=args.samples, tables_filter=args.tables
    )
    print(schema_info)


if __name__ == "__main__":
    main()
