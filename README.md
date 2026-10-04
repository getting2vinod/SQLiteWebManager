# SQLite Web Manager

A lightweight, high-performance web-based SQLite database management tool built with **FastAPI**, managed with **`uv`**, styled with **Bootstrap 5**, and designed for reverse-proxy compatibility.

SQLite Web Manager allows you to discover, inspect, query, and modify SQLite databases stored across subfolders (including symlinks) with a non-destructive working-copy workflow.

---

## Key Features

* **Subfolder & Symlink Discovery**: Scans subdirectories in the `data/` folder for SQLite files (`.db`, `.sqlite`, `.sqlite3`, `.db3`) or symlinks pointing to external databases.
* **Safe Working-Copy Workflow**:
  * **Load**: Copies the target database into `current/active.db` so queries and modifications run on an isolated working copy.
  * **Commit**: Overwrites the source database with the active working copy after automatically generating a timestamped backup (e.g., `sales_20261004_143022.db`).
* **Interactive SQL Editor & History**:
  * Freeform SQL query execution with DDL/DML support and timing statistics.
  * **Query History**: Automatically stores the last 20 successful queries in browser local storage with a one-click copy back to the editor.
* **Tabular Data View & Pagination**:
  * Server-side pagination with configurable page limits (`25`, `50`, `100`, `250`).
  * Instant schema viewer inspecting column names, types, default values, primary keys, and `NOT NULL` constraints.
* **Database Management**:
  * **New DB**: Create a new subfolder and SQLite file initialized with a primary table in a single step.
  * **Delete DB**: Safely remove local database folders directly from the web UI.
  * **Download**: Export the active working database instantly for local inspection.
* **Reverse Proxy Ready**: Built-in middleware sanitizes duplicate slashes and handles subpath routing dynamically using the `ROUTE_PATH` environment variable.

---

## Directory Structure

```text
SQLLiteMan/
├── app/
│   ├── main.py              # FastAPI application, middleware, and API routes
│   ├── setup_demo.py        # Demo database and symlink generator
│   └── templates/
│       └── index.html       # Single-page Bootstrap 5 user interface
├── data/                    # Storage volume for database subfolders/symlinks
│   ├── app_sales/
│   │   └── database.db      # SQLite file or symlink
│   └── app_users/
│       └── database.sqlite  # SQLite file or symlink
├── current/                 # Working volume for active database session
│   ├── active.db            # Working copy of the loaded database
│   └── active_info.txt      # Text marker storing active folder name
├── pyproject.toml           # Package configuration using Astral uv
├── Dockerfile               # Container build file using uv
├── docker-compose.yml       # Production/development container setup
└── README.md