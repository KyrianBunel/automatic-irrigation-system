import time
from datetime import datetime, timedelta
import paho.mqtt.client as mqtt

# --- Configuration MQTT ---
MQTT_BROKER = "localhost"
MQTT_BASE_TOPIC = "arrosage/config/"

# Dictionnaire pour stocker les réglages reçus de l'interface Web
data_store = {
    "mode": "MANU",
    "StrDuree": "0",
    "StrRecurrence": "0",
    "StrDateDebut": "2024/01/01",
    "StrZone1": "off", "StrZone2": "off", "StrZone3": "off",
    "StrDebut1": "00:00", "StrDebut2": "00:00", "StrDebut3": "00:00",
    "vanne1": "0", "vanne2": "0", "vanne3": "0",
    "pluie": "1" # 1 = Sec, 0 = Pluie
}

# --- Callbacks MQTT ---
def on_message(client, userdata, message):
    topic = message.topic.replace(MQTT_BASE_TOPIC, "")
    payload = message.payload.decode()
    data_store[topic] = payload

client = mqtt.Client()
client.on_message = on_message
client.connect(MQTT_BROKER, 1883, 60)
client.subscribe(MQTT_BASE_TOPIC + "#")
client.loop_start()

# --- Fonctions utilitaires ---
def commander_vanne(id_vanne, etat):
    """Envoie l'ordre à l'ESP32 via MQTT si l'état change"""
    topic = f"vanne{id_vanne}"
    if data_store.get(topic) != str(etat):
        client.publish(MQTT_BASE_TOPIC + topic, str(etat), retain=True)

def gestion_mode_prog(now):
    try:
        # 1. Calcul de la récurrence
        date_debut = datetime.strptime(data_store["StrDateDebut"], "%Y-%m-%d")
        delta_jours = (now.date() - date_debut.date()).days
        recurrence = int(data_store["StrRecurrence"])
        
        if recurrence > 0 and delta_jours >= 0 and delta_jours % recurrence == 0:
            # 2. Vérification des 3 zones
            for i in range(1, 4):
                if data_store[f"StrZone{i}"] == "on" and data_store["pluie"] == "1":
                    heure_debut = data_store[f"StrDebut{i}"] # format "HH:MM"
                    h, m = map(int, heure_debut.split(':'))
                    
                    debut_arrosage = now.replace(hour=h, minute=m, second=0, microsecond=0)
                    fin_arrosage = debut_arrosage + timedelta(minutes=int(data_store["StrDuree"]))
                    
                    if debut_arrosage <= now < fin_arrosage:
                        commander_vanne(i, 1)
                    else:
                        commander_vanne(i, 0)
                else:
                    commander_vanne(i, 0)
        else:
            # Pas un jour de récurrence
            for i in range(1, 4): commander_vanne(i, 0)
    except Exception as e:
        print(f"Erreur calcul PROG: {e}")

# --- Boucle Principale ---
print("Logique d'arrosage MQTT démarrée...")

try:
    while True:
        current_time = datetime.now()
        mode = data_store["mode"]

        if mode == "MANU":
            # En mode manuel, on ne fait rien : le serveur Flask 
            # publie déjà directement sur les topics vanne1/2/3
            pass

        elif mode == "PROG":
            gestion_mode_prog(current_time)

        elif mode == "AUTO":
            # Ta logique AUTO basée sur les capteurs (humidité, etc.)
            # Exemple simplifié :
            if data_store["pluie"] == "0": # S'il pleut
                for i in range(1, 4): commander_vanne(i, 0)
            pass

        time.sleep(1) # Vérification chaque seconde

except KeyboardInterrupt:
    print("Arrêt du script...")
    client.loop_stop()