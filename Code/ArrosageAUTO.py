import time
from datetime import datetime, timedelta
import paho.mqtt.client as mqtt

# --- Configuration MQTT ---
MQTT_BROKER = "localhost"
MQTT_BASE_TOPIC = "arrosage/config/"

# Dictionnaire pour stocker les réglages
data_store = {
    "mode": "MANU",
    "StrDuree": "0",
    "StrRecurrence": "0",
    "StrDateDebut": "2024/01/01",
    "StrZone1": "off", "StrZone2": "off", "StrZone3": "off",
    "StrDebut1": "00:00", "StrDebut2": "00:00", "StrDebut3": "00:00",
    "vanne1": "0", "vanne2": "0", "vanne3": "0",
    "pluie": "1" 
}

# --- Callbacks MQTT ---
def on_connect(client, userdata, flags, rc):
    print(f"Connecté au Broker MQTT avec le code : {rc}")
    client.subscribe(MQTT_BASE_TOPIC + "#")

def on_message(client, userdata, message):
    topic = message.topic.replace(MQTT_BASE_TOPIC, "")
    payload = message.payload.decode()
    data_store[topic] = payload
    # Log pour voir les messages arriver
    print(f"   -> MQTT Réception: [{topic}] = {payload}")

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect(MQTT_BROKER, 1883, 60)
client.loop_start()

def commander_vanne(id_vanne, etat):
    topic = f"vanne{id_vanne}"
    val_voulue = str(etat)
    # On ne publie que si l'état actuel est différent pour ne pas saturer le réseau
    if data_store.get(topic) != val_voulue:
        print(f"!!! ORDRE VANNE {id_vanne} -> {val_voulue} !!!")
        client.publish(MQTT_BASE_TOPIC + topic, val_voulue, retain=True)

def gestion_mode_prog(now):
    try:
        # Nettoyage de la date (sécurité slash/tiret)
        date_propre = data_store["StrDateDebut"].replace("-", "/")
        date_debut = datetime.strptime(date_propre, "%Y/%m/%d")
        delta_jours = (now.date() - date_debut.date()).days
        recurrence = int(data_store["StrRecurrence"])
        
        # Le déclenchement
        if recurrence > 0 and delta_jours >= 0 and delta_jours % recurrence == 0:
            for i in range(1, 4):
                if data_store[f"StrZone{i}"] == "on" and data_store["pluie"] == "1":
                    h, m = map(int, data_store[f"StrDebut{i}"].split(':'))
                    debut = now.replace(hour=h, minute=m, second=0, microsecond=0)
                    fin = debut + timedelta(minutes=int(data_store["StrDuree"]))
                    
                    if debut <= now < fin:
                        commander_vanne(i, 1)
                    else:
                        commander_vanne(i, 0)
                else:
                    commander_vanne(i, 0)
        else:
            for i in range(1, 4): commander_vanne(i, 0)
    except Exception as e:
        print(f"Erreur calcul PROG: {e}")

# --- Boucle Principale ---
print("Logique d'arrosage lancée. En attente de messages...")

try:
    last_print = 0
    while True:
        now = datetime.now()
        mode_actuel = data_store.get("mode", "MANU")

        # Affichage d'état toutes les 5 secondes pour debug
        if time.time() - last_print > 5:
            print(f"[STATUS] Mode: {mode_actuel} | Pluie: {data_store['pluie']} | Vannes: {data_store['vanne1']}{data_store['vanne2']}{data_store['vanne3']}")
            last_print = time.time()

        if mode_actuel == "PROG":
            gestion_mode_prog(now)
        elif mode_actuel == "AUTO":
            # Test Forcé : On allume tout en mode AUTO
            for i in range(1, 4): commander_vanne(i, 1)
        
        time.sleep(1)

except KeyboardInterrupt:
    client.loop_stop()