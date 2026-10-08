#Bibliothèques
import pandas as pd  #Bibliothèque pour la manipulation de données
import psycopg2  #Bibliothèque pour se connecter à PostgreSQL
from sklearn.ensemble import IsolationForest
import time  #Bibliothèque pour gérer le temps

# Étape 1 : La connexion à PostgreSQL (à modifier avec nos propres paramètres)

conn = psycopg2.connect(database = "xxxxxx", 
                        user = "xxxxxx", 
                        host= 'localhost',
                        password = "xxxxxx",
                        port = 5432)

cur = conn.cursor()

cur.execute("""
    SELECT temperature, humidite, gaz, fumees, mouvement, timestamp
    FROM data_camp_sensors
    ORDER BY timestamp DESC
    LIMIT 300;
""")

historique_donnees = cur.fetchall()

df = pd.DataFrame(
    historique_donnees,
    columns=['temperature', 'humidite', 'gaz', 'fumees', 'mouvement', 'timestamp']
)


# Étape 2 : L'entraînement initial de l'IA (.fit())

    #a) On selectionne nos variables

X = df[['temperature', 'humidite', 'gaz', 'fumees']]

    #b) On instancie le modèle Isolation Forest]]
isolation_forest = IsolationForest(contamination=0.02, random_state=42)

    #c) On entraîne le modèle sur les données historiques
isolation_forest.fit(X)


# Étape 3 : La boucle de surveillance en temps réel

timestamp_dernier_traite = None

while True:
    cur.execute("""
    SELECT temperature, humidite, gaz, fumees, mouvement, timestamp
    FROM data_camp_sensors
    ORDER BY timestamp DESC
    LIMIT 1;
""")
    derniere_mesure = cur.fetchone()

    if derniere_mesure is not None:
        timestamp_actuel = derniere_mesure[5] # On récupère la timestamp de la dernière mesure 5élèments dans ma requête SQL
        derniere_mesure_df = pd.DataFrame([derniere_mesure], columns=['temperature', 'humidite', 'gaz', 'fumees', 'mouvement', 'timestamp'])
        derniere_mesure_X = derniere_mesure_df[['temperature', 'humidite', 'gaz', 'fumees']]


# Étape 4 : La prédiction (.predict())
  
        if timestamp_actuel != timestamp_dernier_traite:
            timestamp_dernier_traite = timestamp_actuel  # On mémorise qu'on a traité cette timestamp
            prediction = isolation_forest.predict(derniere_mesure_X)

            if prediction[0] == -1:
                print(f"⚠️ Anomalie détectée à {derniere_mesure_df['timestamp'].values[0]} : {derniere_mesure_df[['temperature', 'humidite', 'gaz', 'fumees']].values[0]}")
            else:
                print(f"✅ Mesure normale à {derniere_mesure_df['timestamp'].values[0]} : {derniere_mesure_df[['temperature', 'humidite', 'gaz', 'fumees']].values[0]}")



# Étape 5 : L'écriture du résultat dans PostgreSQL

            anomalie = (prediction[0] == -1)  # Vrai si -1 (Anomalie), Faux si 1 (Normal)

            cur.execute("""
                    UPDATE data_camp_sensors
                    SET anomalie = %s
                    WHERE timestamp = %s;
                    """, (anomalie, timestamp_actuel))

            conn.commit()

    time.sleep(5)  # On attend 5 secondes avant de vérifier à nouveau les nouvelles mesures