#include "DHT.h" //Importation de la librairie DHT.h pour la température / humidité.

#define DHTPIN D4
#define DHTTYPE DHT11
#define pinSensorMotion D7
#define pinSensorGas A0
#define pinBuzzer D1

DHT dht(DHTPIN, DHTTYPE);

struct SensorData { //Structure qui prend en composant l'ensemble des différents valeurs des capteurs
  float temperature;
  float humidite;
  int gaz;
  bool mouvement;
};

float getTemperature() { //Méthode pour récupérer la température
  return dht.readTemperature();
}

float getHumidite() { //Méthode pour l'humidité
  return dht.readHumidity();
}

int getGaz() { //Méthode pour le gaz
  return analogRead(pinSensorGas);
}

bool getMouvement() { //Méthode pour le mouvement 
  return digitalRead(pinSensorMotion) == HIGH;
}

SensorData getToutesLesDonnees() { //Méthodes permettant de retourner l'ensemble des données des différents capteursde type retour : SensorData
  SensorData data;
  data.temperature = getTemperature();
  data.humidite = getHumidite();
  data.gaz = getGaz();
  data.mouvement = getMouvement();
  return data;
}

void jouerNote(int frequence, int dureeMs) { //Méthode pour lancer des sons sur une fréqueence et une durée en ms
  tone(pinBuzzer, frequence, dureeMs);
  delay(dureeMs * 1.3);
  noTone(pinBuzzer);
}

void bipBuzzer(int dureeMs) {
  jouerNote(1000, 1000);
  jouerNote(700, 1000);
  jouerNote(350, 1000);
  tone(pinBuzzer, 2400);
  digitalWrite(pinBuzzer, HIGH);
  delay(dureeMs);
  digitalWrite(pinBuzzer, LOW);
}

void setup() {
  Serial.begin(115200);
  Serial.println("Demarrage...");
  pinMode(pinSensorMotion, INPUT);
  pinMode(pinBuzzer, OUTPUT);
  dht.begin();
}

void loop() {
  bipBuzzer(200);

  SensorData mesures = getToutesLesDonnees();

  if (isnan(mesures.temperature) || isnan(mesures.humidite)) {
    Serial.println("Erreur de lecture du sensor de temperature");
  } else {
    Serial.print("Temperature : ");
    Serial.print(mesures.temperature);
    Serial.print(" °C | Humidite : ");
    Serial.print(mesures.humidite);
    Serial.println(" %");
  }

  Serial.print("Niveau de gaz (A0) : ");
  Serial.println(mesures.gaz);

  if (mesures.mouvement) {
    Serial.println("Mouvement detecte !");
  }

  delay(2000);
}