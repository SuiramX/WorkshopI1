import sys
import psycopg2
from psycopg2.extras import RealDictCursor


# Affichage UTF-8
if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")


# CONFIGURATION POSTGRESQL

DB_HOST = "localhost"
DB_PORT = 5433
DB_NAME = "sentinel_x"
DB_USER = "sentinel"
DB_PASSWORD = "sentinel"


# CREATION DE LA TABLE ET DES INDEX

SQL_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS sensor_readings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    temperature DOUBLE PRECISION NOT NULL,
    humidity DOUBLE PRECISION NOT NULL,
    gas_level DOUBLE PRECISION NOT NULL,
    presence BOOLEAN NOT NULL DEFAULT false,
    device_id VARCHAR(50)
);

CREATE INDEX IF NOT EXISTS ix_sensor_readings_timestamp
ON sensor_readings(timestamp);
CREATE INDEX IF NOT EXISTS idx_readings_device_time
ON sensor_readings(device_id, timestamp);
"""


# CONNEXION A POSTGRESQL

def connect_db():

    try:

        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )

        print(f"[+] Connexion réussie à '{DB_NAME}'")

        return conn

    except Exception as err:

        print("[-] Erreur de connexion PostgreSQL :", err)

        return None


# CREATION DE LA TABLE

def create_table(conn):

    try:

        with conn.cursor() as cursor:

            cursor.execute(SQL_CREATE_TABLE)

        conn.commit()

        print("[+] Table sensor_readings créée / vérifiée")

    except Exception as err:

        conn.rollback()

        print("[-] Erreur création table :", err)


# AFFICHER LES 10 DERNIERES DONNEES

def show_last_readings(conn):

    try:

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:

            cursor.execute("""
                SELECT
                    id,
                    timestamp,
                    temperature,
                    humidity,
                    gas_level,
                    presence,
                    device_id
                FROM sensor_readings
                ORDER BY timestamp DESC
                LIMIT 10;
            """)

            rows = cursor.fetchall()

        if not rows:

            print("Aucune donnée dans la table.")

        else:

            for row in rows:

                print()

                print("Date        :", row["timestamp"])
                print("Temperature :", row["temperature"], "°C")
                print("Humidite    :", row["humidity"], "%")
                print("Gaz         :", row["gas_level"], "ppm")
                print(
                    "Presence    :",
                    "Oui" if row["presence"] else "Non"
                )
                print("Capteur     :", row["device_id"])

    except Exception as err:

        print("[-] Erreur lecture données :", err)


# PROGRAMME PRINCIPAL

def main():

    conn = connect_db()

    if conn is None:
        return

    create_table(conn)

    show_last_readings(conn)

    conn.close()


if __name__ == "__main__":
    main()