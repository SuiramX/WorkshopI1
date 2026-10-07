import os
import psycopg

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
ADMIN_USER = os.getenv("POSTGRES_ADMIN_USER", "postgres")
ADMIN_PASSWORD = os.getenv("POSTGRES_ADMIN_PASSWORD", "postgres")
ADMIN_DB = os.getenv("POSTGRES_ADMIN_DB", "postgres")

APP_USER = os.getenv("POSTGRES_USER", os.getenv("DB_USER", "sentinel"))
APP_PASSWORD = os.getenv("POSTGRES_PASSWORD", os.getenv("DB_PASSWORD", "sentinel_secure_pass"))
APP_DB = os.getenv("POSTGRES_DB", os.getenv("DB_NAME", "sentinel_x"))

conn = psycopg.connect(
    f"host={DB_HOST} port={DB_PORT} user={ADMIN_USER} password={ADMIN_PASSWORD} dbname={ADMIN_DB}",
    autocommit=True
)

with conn.cursor() as cur:
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (APP_USER,))
    if not cur.fetchone():
        cur.execute(f"CREATE ROLE {APP_USER} WITH LOGIN PASSWORD %s NOSUPERUSER NOCREATEDB NOCREATEROLE;", (APP_PASSWORD,))
        print(f"Role {APP_USER} created successfully with secure privileges!")
    else:
        cur.execute(f"ALTER ROLE {APP_USER} WITH PASSWORD %s NOSUPERUSER NOCREATEDB NOCREATEROLE;", (APP_PASSWORD,))
        print(f"Role {APP_USER} altered successfully with secure privileges!")

    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (APP_DB,))
    if not cur.fetchone():
        cur.execute(f"CREATE DATABASE {APP_DB} OWNER {APP_USER};")
        print(f"Database {APP_DB} created successfully!")
    else:
        print(f"Database {APP_DB} already exists!")

conn.close()

