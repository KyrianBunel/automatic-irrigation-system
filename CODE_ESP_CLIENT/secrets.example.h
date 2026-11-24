// Copie ce fichier en "secrets.h" (même dossier) puis remplis les valeurs.
// secrets.h est ignoré par git : il ne doit jamais être publié.
#pragma once

#define WIFI_SSID      "nom_du_wifi"
#define WIFI_PASSWORD  "mot_de_passe_wifi"

#define MQTT_SERVER    "192.168.1.30"   // IP du Raspberry Pi
#define MQTT_PORT      1883
#define MQTT_USER      "esp32"
#define MQTT_PASSWORD  "voir /etc/arrosage/identifiants_mqtt.txt sur le Raspberry Pi"
