## Architecture du projet

Le projet est composé de plusieurs services communiquant entre eux afin de récupérer, analyser, stocker et afficher les données provenant du boîtier SENTINEL-X.

### Application Web

L'application web permet de :

* Afficher les statistiques et différents graphiques.
* Afficher le flux vidéo en temps réel.
* Afficher les détections valides / invalides.
* Afficher le statut du boîtier.

### Intelligence Artificielle

Le module IA permet de :

* Récupérer le flux vidéo.
* Analyser le flux vidéo.
* Détecter les événements ou anomalies.
* Renvoyer le résultat de l'analyse à l'API.

### Base de données

La base de données permet de :

* Recevoir les données brutes.
* Stocker les données.
* Rendre les données accessibles en lecture par l'API.

### Broker

Le broker assure la communication avec les capteurs du boîtier.

Il permet de :

* Récupérer les données provenant des différents capteurs.
* Envoyer les données à l'API.
* Transmettre les instructions de l'API vers les actionneurs/capteurs.

### API

L'API constitue le point central de communication entre les différents services.

Elle permet de :

* Accéder à la base de données en lecture et en écriture.
* Envoyer les données à l'application web.
* Recevoir les résultats provenant de l'IA.
* Recevoir les messages provenant du broker.
* Envoyer des messages et instructions au broker.

### WebSocket

Le WebSocket permet la communication en temps réel.

Il permet notamment de :

* Envoyer le flux vidéo en temps réel vers l'application web.
* Récupérer et transmettre le flux vidéo.

