import sqlite3
from pathlib import Path

def create_demo_environment():
    BASE_DIR = Path(__file__).resolve().parent.parent
    data_dir = BASE_DIR / "data"
    sample_dbs_dir = BASE_DIR / "sample_dbs_store"
    
    data_dir.mkdir(exist_ok=True)
    sample_dbs_dir.mkdir(exist_ok=True)

    # 1. Sales database
    sales_db = sample_dbs_dir / "sales_real.db"
    conn = sqlite3.connect(sales_db)
    conn.execute("CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, name TEXT, price REAL);")
    conn.execute("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, product_id INTEGER, quantity INTEGER);")
    conn.execute("INSERT OR REPLACE INTO products VALUES (1, 'Laptop', 1200.50), (2, 'Mouse', 25.00);")
    conn.commit()
    conn.close()

    # 2. Users database
    users_db = sample_dbs_dir / "users_real.sqlite"
    conn = sqlite3.connect(users_db)
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, email TEXT);")
    conn.execute("INSERT OR REPLACE INTO users VALUES (1, 'alice', 'alice@example.com'), (2, 'bob', 'bob@example.com');")
    conn.commit()
    conn.close()

    # 3. Create subfolder 1 with symlink
    app_sales_dir = data_dir / "app_sales"
    app_sales_dir.mkdir(exist_ok=True)
    symlink_sales = app_sales_dir / "sales.db"
    if symlink_sales.exists() or symlink_sales.is_symlink():
        symlink_sales.unlink()
    symlink_sales.symlink_to(sales_db.resolve())

    # 4. Create subfolder 2 with symlink
    app_users_dir = data_dir / "app_users"
    app_users_dir.mkdir(exist_ok=True)
    symlink_users = app_users_dir / "users.sqlite"
    if symlink_users.exists() or symlink_users.is_symlink():
        symlink_users.unlink()
    symlink_users.symlink_to(users_db.resolve())

    print("✅ Demo environment setup complete inside 'data/'!")

if __name__ == "__main__":
    create_demo_environment()