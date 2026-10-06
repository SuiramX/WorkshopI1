import psycopg

conn = psycopg.connect("host=127.0.0.1 port=5432 user=postgres dbname=postgres", autocommit=True)
with conn.cursor() as cur:
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = 'sentinel'")
    if not cur.fetchone():
        cur.execute("CREATE ROLE sentinel WITH LOGIN PASSWORD 'sentinel' SUPERUSER CREATEDB CREATEROLE;")
        print("Role sentinel created successfully!")
    else:
        cur.execute("ALTER ROLE sentinel WITH PASSWORD 'sentinel' SUPERUSER CREATEDB CREATEROLE;")
        print("Role sentinel altered successfully!")

    cur.execute("SELECT 1 FROM pg_database WHERE datname = 'sentinel_x'")
    if not cur.fetchone():
        cur.execute("CREATE DATABASE sentinel_x OWNER sentinel;")
        print("Database sentinel_x created successfully!")
    else:
        print("Database sentinel_x already exists!")
conn.close()
