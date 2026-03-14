import time
import requests
from datetime import datetime, timedelta
import paho.mqtt.client as mqtt

# --- Configuration MQTT ---
MQTT_BROKER = "localhost"
MQTT_BASE_TOPIC = "arrosage/config/"
LAT = 44.99166  # YOUR_COORDINATES
LON = -0.44167

# Dictionnaire pour stocker les réglages
data_store = {
    "mode": "MANU",
    "StrDuree": "10", 
    "pluie": 0.0,
    "temp_station": 0.0,
    "pluie_2j_passe": 0.0,
    "pluie_2j_futur": 0.0,
    "cycle_auto_actif": False,
    "debut_cycle": None,
    "zone_en_cours": 0,
    "vanne1": "0", "vanne2": "0", "vanne3": "0"
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

# --- Update Météo ---
def update_meteo():
    """Récupère le cumul de pluie passé (2j) et futur (2j) sans clé API"""
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&daily=precipitation_sum&past_days=2&forecast_days=3&timezone=auto"
        res = requests.get(url, timeout=10).json()
        
        # Cumul 2 derniers jours (index 0 et 1)
        pluie_passee = sum(res['daily']['precipitation_sum'][0:2])
        # Cumul 2 jours à venir (index 3 et 4, car 2 est aujourd'hui)
        pluie_future = sum(res['daily']['precipitation_sum'][3:5])
        
        data_store["pluie_2j_passe"] = pluie_passee
        data_store["pluie_2j_futur"] = pluie_future
        print(f"[METEO] Historique 48h: {pluie_passee}mm | Prévisions 48h: {pluie_future}mm")
    except Exception as e:
        print(f"Erreur API Météo: {e}")

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


def executer_cycle_auto():
    """Gère le séquençage temporel des zones"""
    if not data_store["cycle_auto_actif"]:
        return

    now = datetime.now()
    duree_zone = int(data_store.get("StrDuree", 10))
    # Temps écoulé en minutes depuis le début du cycle
    delta_min = (now - data_store["debut_cycle"]).total_seconds() / 60

    if delta_min < duree_zone:
        if data_store["zone_en_cours"] != 1: 
            print("--- AUTO : Zone 1 active ---")
            commander_vanne(1, 1)
            commander_vanne(2, 0)
            commander_vanne(3, 0)
    elif delta_min < (duree_zone * 2):
        if data_store["zone_en_cours"] != 2:
            print("--- AUTO : Zone 2 active ---")
            commander_vanne(1, 0)
            commander_vanne(2, 1)
            commander_vanne(3, 0)
    elif delta_min < (duree_zone * 3):
        if data_store["zone_en_cours"] != 3:
            print("--- AUTO : Zone 3 active ---")
            commander_vanne(1, 0)
            commander_vanne(2, 0)
            commander_vanne(3, 1)
    else:
        print("--- Cycle AUTO terminé ---")
        for i in range(1, 4): commander_vanne(i, 0)
        data_store["cycle_auto_actif"] = False
# --- Boucle Principale ---
print("Logique d'arrosage lancée. En attente de messages...")

try:
    while True:
        now = datetime.now()
        mode_actuel = data_store.get("mode", "MANU")

        if mode_actuel == "PROG":
            gestion_mode_prog(now)

        elif mode_actuel == "AUTO":
            if now.hour == 5 and now.minute == 00:
                pluie_recente = max(float(data_store.get("pluie", 0)), 
                            float(data_store.get("pluie_station", 0)), 
                            data_store["pluie_2j_passe"])
                
                if data_store["pluie_2j_futur"] < 2.0 and pluie_recente < 5.0 and data_store["temp_station"] > 12:
                    print("Conditions optimales. Lancement du cycle séquentiel.")
                    data_store["cycle_auto_actif"] = True
                    data_store["debut_cycle"] = now
        if data_store["cycle_auto_actif"]:
            executer_cycle_auto()

        time.sleep(1)

except KeyboardInterrupt:
    client.loop_stop()
