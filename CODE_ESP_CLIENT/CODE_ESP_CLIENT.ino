/*
 * Arrosage automatique - ESP32 de commande des vannes
 *
 * Sécurités :
 *  - vannes fermées au démarrage et dès que la liaison MQTT est perdue ;
 *  - coupure automatique d'une vanne ouverte depuis plus de DUREE_MAX_MIN,
 *    même si le Raspberry Pi a planté ;
 *  - ordres reçus sur arrosage/cmd/vanneN (jamais retenus) ; vides ou inconnus : ignorés ;
 *  - l'état réel de chaque vanne est publié (arrosage/status/vanneN, retenu) ;
 *  - "arrosage/status/esp" passe à "offline" automatiquement (LWT) si l'ESP disparaît.
 *
 * Identifiants Wi-Fi / MQTT : dans secrets.h (voir secrets.example.h), jamais dans ce fichier.
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <Adafruit_NeoPixel.h>
#include "secrets.h"

// --- Réglages ---
const unsigned long DUREE_MAX_MIN = 125;  // coupure de sécurité (doit dépasser la durée max d'une zone : 120 min)
const bool RELAIS_ACTIF_BAS = false;      // mettre true si le module relais colle quand la broche est à LOW
const unsigned long INTERVALLE_RECONNEXION_MS = 5000;
const unsigned long INTERVALLE_STATUT_MS = 60000;

// --- Vannes ---
const int NB_VANNES = 3;
const int pinsVannes[NB_VANNES] = {32, 33, 25};
const int pinVanne4 = 26;  // câblée mais non utilisée : maintenue fermée

bool vanneOuverte[NB_VANNES] = {false, false, false};
unsigned long debutOuverture[NB_VANNES] = {0, 0, 0};

// --- MQTT ---
const char* CLIENT_ID = "arrosage-esp32";
const char* TOPIC_ESP = "arrosage/status/esp";
const char* TOPIC_SECURITE = "arrosage/status/securite";

WiFiClient espClient;
PubSubClient client(espClient);
unsigned long dernierEssai = 0;
unsigned long dernierStatut = 0;

// --- LED d'état ---
const int LED_PIN_DATA = 22;
const int LED_PIN_PWR = 23;
const uint8_t LUMINOSITE = 80;  // 0..255
Adafruit_NeoPixel led(1, LED_PIN_DATA, NEO_GRB + NEO_KHZ800);

uint32_t couleurActuelle = 0xFFFFFFFF;

void couleur(uint8_t rouge, uint8_t vert, uint8_t bleu) {
  uint32_t c = led.Color(rouge, vert, bleu);
  if (c == couleurActuelle) return;  // évite de rafraîchir la LED en boucle
  couleurActuelle = c;
  led.setPixelColor(0, c);
  led.show();
}

// ------------------------------------------------------------------------------

// Commandes sur arrosage/cmd/ (jamais retenues) ; l'ancien arrosage/config/vanneN n'est plus écouté
String topicCommande(int i) { return "arrosage/cmd/vanne" + String(i + 1); }
String topicEtat(int i) { return "arrosage/status/vanne" + String(i + 1); }

void ecrireRelais(int pin, bool ouvert) {
  bool niveau = RELAIS_ACTIF_BAS ? !ouvert : ouvert;
  digitalWrite(pin, niveau ? HIGH : LOW);
}

void publierEtat(int i) {
  if (client.connected()) {
    client.publish(topicEtat(i).c_str(), vanneOuverte[i] ? "1" : "0", true);
  }
}

void commanderVanne(int i, bool ouvrir) {
  if (ouvrir && !vanneOuverte[i]) debutOuverture[i] = millis();
  vanneOuverte[i] = ouvrir;
  ecrireRelais(pinsVannes[i], ouvrir);
  Serial.printf("Vanne %d -> %s\n", i + 1, ouvrir ? "OUVERTE" : "fermee");
  publierEtat(i);
}

void fermerTout() {
  for (int i = 0; i < NB_VANNES; i++) {
    if (vanneOuverte[i]) commanderVanne(i, false);
    else ecrireRelais(pinsVannes[i], false);
  }
  ecrireRelais(pinVanne4, false);
}

void callback(char* topic, byte* payload, unsigned int length) {
  if (length == 0) return;  // message vide (effacement d'un ancien message retenu)

  String message;
  for (unsigned int k = 0; k < length; k++) message += (char)payload[k];
  message.trim();

  bool ouvrir;
  if (message == "1") ouvrir = true;
  else if (message == "0") ouvrir = false;
  else return;  // valeur inattendue : on ignore

  String t(topic);
  for (int i = 0; i < NB_VANNES; i++) {
    if (t == topicCommande(i)) {
      commanderVanne(i, ouvrir);
      return;
    }
  }
}

bool connecterMqtt() {
  Serial.print("Connexion MQTT... ");
  // Le LWT passe "arrosage/status/esp" à "offline" si l'ESP disparaît sans prévenir
  if (client.connect(CLIENT_ID, MQTT_USER, MQTT_PASSWORD, TOPIC_ESP, 1, true, "offline")) {
    Serial.println("OK");
    client.publish(TOPIC_ESP, "online", true);
    for (int i = 0; i < NB_VANNES; i++) {
      client.subscribe(topicCommande(i).c_str(), 1);
      publierEtat(i);
    }
    return true;
  }
  Serial.printf("echec, rc=%d\n", client.state());
  return false;
}

void surveillerDureeMax() {
  const unsigned long dureeMaxMs = DUREE_MAX_MIN * 60UL * 1000UL;
  for (int i = 0; i < NB_VANNES; i++) {
    if (vanneOuverte[i] && millis() - debutOuverture[i] >= dureeMaxMs) {
      Serial.printf("SECURITE : vanne %d ouverte depuis plus de %lu min, fermeture\n", i + 1, DUREE_MAX_MIN);
      commanderVanne(i, false);
      if (client.connected()) {
        String msg = "vanne" + String(i + 1) + " fermee apres " + String(DUREE_MAX_MIN) + " min (duree max)";
        client.publish(TOPIC_SECURITE, msg.c_str(), false);
      }
    }
  }
}

void setup() {
  // Vannes fermées avant toute autre chose
  for (int i = 0; i < NB_VANNES; i++) {
    pinMode(pinsVannes[i], OUTPUT);
    ecrireRelais(pinsVannes[i], false);
  }
  pinMode(pinVanne4, OUTPUT);
  ecrireRelais(pinVanne4, false);

  Serial.begin(115200);

  pinMode(LED_PIN_PWR, OUTPUT);
  digitalWrite(LED_PIN_PWR, HIGH);
  led.begin();
  led.setBrightness(LUMINOSITE);
  couleur(0, 0, 255);  // bleu : connexion Wi-Fi en cours

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  client.setServer(MQTT_SERVER, MQTT_PORT);
  client.setCallback(callback);
  client.setKeepAlive(15);
}

void loop() {
  // La surveillance tourne en permanence, même sans réseau
  surveillerDureeMax();

  if (WiFi.status() != WL_CONNECTED || !client.connected()) {
    // Sécurité : sans liaison avec le Raspberry Pi, tout reste fermé
    fermerTout();
    couleur(WiFi.status() != WL_CONNECTED ? 0 : 255, 0, WiFi.status() != WL_CONNECTED ? 255 : 0);
    // bleu = pas de Wi-Fi, rouge = Wi-Fi OK mais pas de MQTT

    if (WiFi.status() == WL_CONNECTED && millis() - dernierEssai >= INTERVALLE_RECONNEXION_MS) {
      dernierEssai = millis();
      connecterMqtt();
    }
    delay(10);
    return;
  }

  client.loop();

  bool uneOuverte = false;
  for (int i = 0; i < NB_VANNES; i++) uneOuverte |= vanneOuverte[i];
  if (uneOuverte) couleur(0, 120, 255);  // bleu clair : arrosage en cours
  else couleur(0, 255, 0);               // vert : tout va bien

  // Republication périodique de l'état (au cas où un message aurait été perdu)
  if (millis() - dernierStatut >= INTERVALLE_STATUT_MS) {
    dernierStatut = millis();
    for (int i = 0; i < NB_VANNES; i++) publierEtat(i);
  }
}
