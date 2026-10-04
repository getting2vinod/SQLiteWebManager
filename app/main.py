import math
import os
import re
import shutil
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel


# Environment & Route Path Configuration
raw_route = os.getenv("ROUTE_PATH", "").strip("/")
ROUTE_PATH = f"/{raw_route}" if raw_route else ""


class PrefixAndSlashMiddleware:
    """
    Middleware that sanitizes duplicate slashes and automatically strips
    the ROUTE_PATH prefix from incoming request paths if NGINX passes it through.
    """
    def __init__(self, app, prefix: str):
        self.app = app
        self.prefix = prefix.rstrip("/")

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = re.sub(r"/{2,}", "/", scope["path"])
            
            if self.prefix and path.startswith(self.prefix):
                path = path[len(self.prefix):]
                if not path.startswith("/"):
                    path = "/" + path

            scope["path"] = path

        await self.app(scope, receive, send)


# Application Directories
APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent

DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_DIR / "data"))
CURRENT_DIR = Path(os.getenv("CURRENT_DIR", PROJECT_DIR / "current"))
ACTIVE_DB_PATH = CURRENT_DIR / "active.db"
ACTIVE_INFO_FILE = CURRENT_DIR / "active_info.txt"

# Ensure working directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
CURRENT_DIR.mkdir(parents=True, exist_ok=True)

# App Initialization
app = FastAPI(
    title="SQLite Manager",
    root_path=ROUTE_PATH,
)

app.add_middleware(PrefixAndSlashMiddleware, prefix=ROUTE_PATH)

# Templates setup
TEMPLATES_DIR = APP_DIR / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)


# Request Models
class LoadDBRequest(BaseModel):
    folder: str


class CreateDBRequest(BaseModel):
    db_name: str


class DeleteDBRequest(BaseModel):
    folder: str


class QueryRequest(BaseModel):
    query: str


# Helper Functions
def scan_databases() -> List[Dict[str, Any]]:
    """Scans DATA_DIR for subfolders containing SQLite files or symlinks."""
    databases = []
    if not DATA_DIR.exists():
        return databases

    valid_extensions = {".db", ".sqlite", ".sqlite3", ".db3"}

    for entry in sorted(DATA_DIR.iterdir()):
        if entry.is_dir():
            subfolder_name = entry.name
            db_file_found = None
            resolved_target = None

            for file in entry.iterdir():
                if file.suffix.lower() in valid_extensions or file.is_symlink():
                    try:
                        resolved = file.resolve()
                        if resolved.exists() and resolved.is_file():
                            db_file_found = file.name
                            resolved_target = str(resolved)
                            break
                    except Exception:
                        continue

            databases.append({
                "folder": subfolder_name,
                "has_db": db_file_found is not None,
                "filename": db_file_found or "No DB file found",
                "resolved_path": resolved_target or ""
            })

    return databases


def get_active_info() -> Optional[str]:
    """Retrieves the name of the currently loaded subfolder."""
    if ACTIVE_INFO_FILE.exists() and ACTIVE_DB_PATH.exists():
        return ACTIVE_INFO_FILE.read_text().strip()
    return None


def set_active_info(folder_name: str):
    """Saves the name of the currently loaded subfolder."""
    ACTIVE_INFO_FILE.write_text(folder_name)


def clear_active_info():
    """Clears the active database state."""
    if ACTIVE_DB_PATH.exists():
        ACTIVE_DB_PATH.unlink()
    if ACTIVE_INFO_FILE.exists():
        ACTIVE_INFO_FILE.unlink()


def execute_sqlite_query(query: str) -> Dict[str, Any]:
    """Executes a SQL query against current/active.db and returns results."""
    if not ACTIVE_DB_PATH.exists():
        raise HTTPException(status_code=400, detail="No database loaded in current folder.")

    start_time = time.time()
    conn = sqlite3.connect(ACTIVE_DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute(query)
        if cursor.description:
            columns = [col[0] for col in cursor.description]
            rows = [dict(row) for row in cursor.fetchall()]
            conn.commit()
            elapsed = round((time.time() - start_time) * 1000, 2)
            return {
                "type": "select",
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "elapsed_ms": elapsed
            }
        else:
            conn.commit()
            affected = cursor.rowcount
            elapsed = round((time.time() - start_time) * 1000, 2)
            return {
                "type": "dml",
                "message": f"Query executed successfully. Affected rows: {affected}",
                "affected_rows": affected,
                "elapsed_ms": elapsed
            }
    except sqlite3.Error as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


# Routes
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    databases = scan_databases()
    active_db = get_active_info()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "route_path": ROUTE_PATH,
            "databases": databases,
            "active_db": active_db,
        }
    )


@app.get("/api/refresh")
async def refresh_databases():
    databases = scan_databases()
    active_db = get_active_info()
    return {"databases": databases, "active_db": active_db}


@app.post("/api/create-db")
async def create_database(payload: CreateDBRequest):
    """Creates a new subfolder and SQLite DB file initialized with a first table matching db_name."""
    db_name = payload.db_name.strip()
    if not db_name or not re.match(r"^[a-zA-Z0-9_-]+$", db_name):
        raise HTTPException(status_code=400, detail="Invalid database name. Use only letters, numbers, underscores, or hyphens.")

    target_dir = DATA_DIR / db_name
    if target_dir.exists():
        raise HTTPException(status_code=400, detail=f"Database or subfolder '{db_name}' already exists.")

    target_dir.mkdir(parents=True, exist_ok=True)
    new_db_file = target_dir / f"{db_name}.db"

    clean_table_name = db_name.replace("-", "_")
    conn = sqlite3.connect(new_db_file)
    cursor = conn.cursor()
    cursor.execute(f'CREATE TABLE IF NOT EXISTS "{clean_table_name}" (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);')
    conn.commit()
    conn.close()

    try:
        shutil.copyfile(new_db_file, ACTIVE_DB_PATH)
        set_active_info(db_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set active DB: {str(e)}")

    tables_result = execute_sqlite_query(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;"
    )
    tables = [row["name"] for row in tables_result.get("rows", [])]

    return {
        "status": "success",
        "message": f"Successfully created database '{db_name}' with initial table '{clean_table_name}'.",
        "active_db": db_name,
        "tables": tables
    }


@app.post("/api/delete-db")
async def delete_database(payload: DeleteDBRequest):
    """Deletes a database subfolder from data/ and resets active state if loaded."""
    folder_name = payload.folder.strip()
    if not folder_name:
        raise HTTPException(status_code=400, detail="Folder name is required.")

    target_dir = DATA_DIR / folder_name
    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Database folder '{folder_name}' not found.")

    active_folder = get_active_info()
    is_active = (active_folder == folder_name)

    try:
        shutil.rmtree(target_dir)
        if is_active:
            clear_active_info()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete database: {str(e)}")

    databases = scan_databases()
    new_active = get_active_info()

    return {
        "status": "success",
        "message": f"Successfully deleted database folder '{folder_name}'.",
        "active_db": new_active,
        "databases": databases
    }


@app.post("/api/load")
async def load_database(payload: LoadDBRequest):
    target_dir = DATA_DIR / payload.folder
    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=404, detail="Subfolder not found.")

    valid_extensions = {".db", ".sqlite", ".sqlite3", ".db3"}
    target_file: Optional[Path] = None

    for file in target_dir.iterdir():
        if file.suffix.lower() in valid_extensions or file.is_symlink():
            resolved = file.resolve()
            if resolved.exists() and resolved.is_file():
                target_file = resolved
                break

    if not target_file:
        raise HTTPException(status_code=404, detail="No valid SQLite DB file found in subfolder.")

    try:
        shutil.copyfile(target_file, ACTIVE_DB_PATH)
        set_active_info(payload.folder)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to copy DB file: {str(e)}")

    tables_result = execute_sqlite_query(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;"
    )
    tables = [row["name"] for row in tables_result.get("rows", [])]

    return {
        "status": "success",
        "message": f"Successfully loaded database from subfolder '{payload.folder}'.",
        "active_db": payload.folder,
        "tables": tables
    }


@app.post("/api/commit")
async def commit_database():
    active_folder = get_active_info()
    if not active_folder or not ACTIVE_DB_PATH.exists():
        raise HTTPException(status_code=400, detail="No active database loaded to commit.")

    target_dir = DATA_DIR / active_folder
    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Source folder '{active_folder}' not found.")

    valid_extensions = {".db", ".sqlite", ".sqlite3", ".db3"}
    target_file: Optional[Path] = None

    for file in target_dir.iterdir():
        if file.suffix.lower() in valid_extensions or file.is_symlink():
            resolved = file.resolve()
            if resolved.exists() and resolved.is_file():
                target_file = resolved
                break

    if not target_file:
        raise HTTPException(status_code=404, detail="No valid source SQLite database file found.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"{target_file.stem}_{timestamp}{target_file.suffix}"
    backup_path = target_file.parent / backup_filename

    try:
        shutil.copyfile(target_file, backup_path)
        shutil.copyfile(ACTIVE_DB_PATH, target_file)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to commit database: {str(e)}")

    return {
        "status": "success",
        "message": f"Successfully committed changes to '{target_file.name}'. Timestamped backup created: '{backup_filename}'.",
        "backup_filename": backup_filename
    }


@app.get("/api/download")
async def download_database():
    if not ACTIVE_DB_PATH.exists():
        raise HTTPException(status_code=400, detail="No active database loaded to download.")

    active_folder = get_active_info() or "database"
    download_filename = f"{active_folder}_active.db"

    return FileResponse(
        path=ACTIVE_DB_PATH,
        filename=download_filename,
        media_type="application/x-sqlite3"
    )


@app.get("/api/tables")
async def get_tables():
    if not ACTIVE_DB_PATH.exists():
        return {"tables": []}
    
    tables_result = execute_sqlite_query(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;"
    )
    tables = [row["name"] for row in tables_result.get("rows", [])]
    return {"tables": tables}


@app.get("/api/table/{table_name}")
async def get_table_details(
    table_name: str,
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=1000)
):
    clean_table_name = table_name.replace('"', '""')
    
    count_info = execute_sqlite_query(f'SELECT COUNT(*) AS total FROM "{clean_table_name}";')
    total_rows = count_info["rows"][0]["total"] if count_info.get("rows") else 0

    schema_info = execute_sqlite_query(f'PRAGMA table_info("{clean_table_name}");')
    
    offset = (page - 1) * limit
    data_info = execute_sqlite_query(f'SELECT * FROM "{clean_table_name}" LIMIT {limit} OFFSET {offset};')

    total_pages = math.ceil(total_rows / limit) if total_rows > 0 else 1

    return {
        "table": table_name,
        "columns": schema_info["rows"],
        "data": data_info,
        "pagination": {
            "total_rows": total_rows,
            "page": page,
            "limit": limit,
            "total_pages": total_pages
        }
    }


@app.post("/api/query")
async def run_query(payload: QueryRequest):
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    
    return execute_sqlite_query(payload.query)