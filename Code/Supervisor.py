import requests
import time
import logging
import paho.mqtt.client as mqtt
import json
from ping3 import ping

# --- CONFIGURATION ---
TOKEN = "8778005076:AAHEqaWUZz7aFPEaTOAL_p6ty5IFzFWLR1Q"
CHAT_ID = "8768214507"
MQTT_BROKER = "192.168.1.30"
MQTT_TOPICS = [
    "arrosage/config/vanne1",
    "arrosage/config/vanne2",
    "arrosage/config/vanne3",
    "arrosage/config/mode"
]

# --- PALIERS D'ALERTES (en minutes) ---
SEUILS_ALERTE_MINUTES = [1, 5, 15, 30, 60] 

# Configuration du logging
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Variables globales d'état
vannes_status = {1: 0, 2: 0, 3: 0}
dernier_seuil_atteint = {1: 0, 2: 0, 3: 0}
last_update_id = 0
current_mode = "MANU"

alerte_reseau_envoyee = False

# --- LOGIQUE MQTT ---

def on_connect(client, userdata, flags, rc):
    logger.info(f"Connecté au Broker MQTT avec le code : {rc}")
    for topic in MQTT_TOPICS:
        client.subscribe(topic)

def on_message(client, userdata, msg):
    global current_mode # Permet de modifier la variable globale
    try:
        topic = msg.topic
        payload = msg.payload.decode().strip() # .strip() enlève les espaces invisibles potentiels

        #Gestion du changement de mode
        if topic == "arrosage/config/mode":
            current_mode = payload
            logger.info(f"Changement de mode détecté : {current_mode}")
            return # On sort de la fonction, pas besoin de vérifier les vannes

        #Gestion des vannes
        num_vanne = int(topic[-1])
        valeur = int(payload)

        if valeur == 1:
            if vannes_status[num_vanne] == 0:
                vannes_status[num_vanne] = time.time()
                logger.info(f"Vanne {num_vanne} allumée détectée via MQTT")
        else:
            vannes_status[num_vanne] = 0
            dernier_seuil_atteint[num_vanne] = 0
            logger.info(f"Vanne {num_vanne} éteinte détectée via MQTT")
            
    except Exception as e:
        logger.error(f"Erreur traitement message MQTT : {e}")

# --- LOGIQUE TELEGRAM ---
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.post(url, json=payload, timeout=5)
        logger.info(f"Message simple envoyé : {message}")
    except Exception as e:
        logger.error(f"Erreur envoi Telegram simple : {e}")

def send_telegram_question(num_vanne, duree_minutes):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Oui, éteindre", "callback_data": f"stop_vanne_{num_vanne}"},
            {"text": "❌ Non, laisser", "callback_data": f"keep_vanne_{num_vanne}"}
        ]]
    }
    
    if duree_minutes >= 60:
        texte_temps = f"{duree_minutes // 60} heure(s) et {duree_minutes % 60} minute(s)"
    else:
        texte_temps = f"{duree_minutes} minute(s)"

    payload = {
        "chat_id": CHAT_ID,
        "text": f"🚨 *Niveau d'Alerte : {duree_minutes} min*\nLa vanne {num_vanne} est allumée en mode MANU depuis {texte_temps} !\nVoulez-vous l'éteindre ?",
        "parse_mode": "Markdown",
        "reply_markup": keyboard
    }
    try:
        requests.post(url, json=payload, timeout=10)
        logger.info(f"Alerte envoyée pour la vanne {num_vanne} ({duree_minutes} min)")
    except Exception as e:
        logger.error(f"Erreur envoi Telegram : {e}")

def handle_callback(callback_query, mqtt_client):
    data = callback_query.get("data")
    chat_id = callback_query.get("message", {}).get("chat", {}).get("id")
    message_id = callback_query.get("message", {}).get("message_id")

    if str(chat_id) != CHAT_ID: return

    if data.startswith("stop_vanne_"):
        num = data.split("_")[-1]
        mqtt_client.publish(f"arrosage/config/vanne{num}", "0", retain=True)
        texte_reponse = f"✅ Ordre d'extinction envoyé pour la vanne {num} via Telegram."
    else:
        num = data.split("_")[-1]
        texte_reponse = f"⚠️ Vous avez choisi de laisser la vanne {num} allumée."

    requests.post(f"https://api.telegram.org/bot{TOKEN}/editMessageText", 
                  json={"chat_id": CHAT_ID, "message_id": message_id, "text": texte_reponse})

def check_telegram_updates(mqtt_client):
    global last_update_id
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    try:
        response = requests.get(url, params={"offset": last_update_id + 1, "timeout": 5}, timeout=10).json()
        if "result" in response:
            for update in response["result"]:
                last_update_id = update["update_id"]
                if "callback_query" in update:
                    handle_callback(update["callback_query"], mqtt_client)
    except:
        pass


# --- PING RÉSEAU ---
def online(ip):
    try:
            reponse = ping(ip, timeout=1)
            if reponse is None or reponse is False:
                return False
            return True
    except OSError:
            # Capture l'erreur "No route to host" sans faire planter le script
            return False
    except Exception as e:
            logger.error(f"Erreur inattendue lors du ping : {e}")
            return False


# --- INITIALISATION ET BOUCLE ---

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect(MQTT_BROKER, 1883, 60)
client.loop_start()

logger.info("Contrôleur Telegram + MQTT démarré...")

try:
    while True:
        maintenant = time.time()
        
        # --- VÉRIFICATION RÉSEAU ---
        if not online("192.168.1.15"):
            if not alerte_reseau_envoyee:
                print("⚠️ [ALERTE] Le serveur 192.168.1.15 est injoignable !")
                send_telegram("🚨 Alerte : L'appareil 192.168.1.15 est hors ligne !")
                alerte_reseau_envoyee = True
        else:
            if alerte_reseau_envoyee:
                print("✅ [INFO] Le serveur 192.168.1.15 est de nouveau en ligne.")
                send_telegram("✅ L'appareil 192.168.1.15 est de nouveau en ligne.")
                alerte_reseau_envoyee = False
        
        # Vérification des alertes en mode "MANU"
        if current_mode == "MANU":
            for num, debut in vannes_status.items():
                if debut > 0: 
                    duree_secondes = maintenant - debut
                    duree_minutes = int(duree_secondes / 60)
                    
                    for seuil in sorted(SEUILS_ALERTE_MINUTES, reverse=True):
                        if duree_minutes >= seuil and dernier_seuil_atteint[num] < seuil:
                            send_telegram_question(num, duree_minutes)
                            dernier_seuil_atteint[num] = seuil
                            break
                            
        #update Telegram
        check_telegram_updates(client)
        time.sleep(1)
        
except KeyboardInterrupt:
    client.loop_stop()
