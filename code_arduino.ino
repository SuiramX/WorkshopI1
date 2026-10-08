#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include "DHT.h" //Importation de la librairie DHT.h pour la température / humidité.

#define DHTPIN D7
#define DHTTYPE DHT11
#define pinSensorMotion D5
#define pinSensorGas A0
#define pinBuzzer D2

const char *ssid = "TP-Link_272A";
const char *password = "cembek-zinXoh-wersu1";
const char *mqtt_server = "192.168.1.9";

WiFiClient espClient;
PubSubClient client(espClient);
DHT dht(DHTPIN, DHTTYPE);

struct SensorData
{ // Structure qui prend en composant l'ensemble des différents valeurs des capteurs
  float temperature;
  float humidite;
  int gaz;
  bool mouvement;
};

float getTemperature()
{ // Méthode pour récupérer la température
  return dht.readTemperature();
}

float getHumidite()
{ // Méthode pour l'humidité
  return dht.readHumidity();
}

int getGaz()
{ // Méthode pour le gaz
  return analogRead(pinSensorGas);
}

bool getMouvement()
{ // Méthode pour le mouvement
  return digitalRead(pinSensorMotion) == HIGH;
}

SensorData getToutesLesDonnees()
{ // Méthodes permettant de retourner l'ensemble des données des différents capteursde type retour : SensorData
  SensorData data;
  data.temperature = getTemperature();
  data.humidite = getHumidite();
  data.gaz = getGaz();
  data.mouvement = getMouvement();
  return data;
}

void jouerNote(int frequence, int dureeMs)
{ // Méthode pour lancer des sons sur une fréqueence et une durée en ms
  tone(pinBuzzer, frequence, dureeMs);
  delay(dureeMs * 1.3);
  noTone(pinBuzzer);
}

void bipBuzzer(int dureeMs)
{
  jouerNote(1000, 1000);
  jouerNote(700, 1000);
  jouerNote(350, 1000);
  tone(pinBuzzer, 2400);
  digitalWrite(pinBuzzer, HIGH);
  delay(dureeMs);
  digitalWrite(pinBuzzer, LOW);
}

void callback(char *topic, byte *payload, unsigned int length)
{
  char message[length + 1];
  memcpy(message, payload, length);
  message[length] = '\0';

  String commande = String(message);
  commande.trim();

  Serial.print("Commande brute recue : [");
  Serial.print(commande);
  Serial.println("]");

  if (commande.equalsIgnoreCase("buzzer"))
  {
    Serial.println("Action: buzzer");
    bipBuzzer(200);
    client.publish("esp8266/status", "Buzzer active");
  }
  else if (commande.equalsIgnoreCase("get_all"))
  {
    Serial.println("Action: get_all");
    SensorData mesures = getToutesLesDonnees();
    char buffer[256];
    snprintf(buffer, sizeof(buffer),
             "{\"temperature\":%.1f,\"humidite\":%.1f,\"gaz\":%d,\"mouvement\":%s}",
             isnan(mesures.temperature) ? 0.0 : mesures.temperature,
             isnan(mesures.humidite) ? 0.0 : mesures.humidite,
             mesures.gaz,
             mesures.mouvement ? "true" : "false");
    bool pubOk = client.publish("esp8266/data", buffer);
    Serial.print("Publication get_all reussie ? ");
    Serial.println(pubOk ? "OUI" : "NON (buffer trop petit)");
  }
  else if (commande.equalsIgnoreCase("temp"))
  {
    char val[16];
    snprintf(val, sizeof(val), "%.1f", getTemperature());
    client.publish("esp8266/data/temperature", val);
  }
  else if (commande.equalsIgnoreCase("hum"))
  {
    char val[16];
    snprintf(val, sizeof(val), "%.1f", getHumidite());
    client.publish("esp8266/data/humidite", val);
  }
  else if (commande.equalsIgnoreCase("gaz"))
  {
    char val[16];
    snprintf(val, sizeof(val), "%d", getGaz());
    client.publish("esp8266/data/gaz", val);
  }
  else if (commande.equalsIgnoreCase("mouv"))
  {
    client.publish("esp8266/data/mouvement", getMouvement() ? "true" : "false");
  }
  else
  {
    Serial.println("Commande non reconnue !");
  }
}

void reconnect()
{
  while (!client.connected())
  {
    if (client.connect("ESP8266_Node"))
    {
      client.subscribe("esp8266/cmd");
    }
    else
    {
      delay(3000);
    }
  }
}

void setup()
{
  Serial.begin(115200);
  Serial.println("Demarrage...");
  pinMode(pinSensorMotion, INPUT);
  pinMode(pinBuzzer, OUTPUT);
  dht.begin();

  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED)
  {
    delay(500);
  }

  client.setServer(mqtt_server, 1883);
  client.setBufferSize(512);
  client.setCallback(callback);
}

void loop()
{
  if (!client.connected())
  {
    reconnect();
  }
  client.loop();
}