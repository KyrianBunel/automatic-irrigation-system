import serial
from datetime import datetime
import time
import re
import paho.mqtt.client as mqtt

import logging

import numpy as np
import scipy.interpolate as si
from scipy.optimize import brentq
import matplotlib.pyplot as plt

USB_PORT = "/dev/ttyUSB0"
BAUD_RATE = 115200

logger = logging.getLogger(__name__)
logging.basicConfig(filename='WeatherStation.log', encoding='utf-8', level=logging.DEBUG)

# --- Configuration MQTT ---
MQTT_BROKER = "localhost"
MQTT_BASE_TOPIC = "arrosage/weather/"

data_store = {
    "temperature": "0",
    "humidite": "0",
    "pression": "0",
    "luminosite": "0",
    "pluie": "0",
    "battery voltage": "0",
    "battery %": "0"
}

# --- Client MQTT ---
def on_message(client, userdata, message):
    """Met à jour le store local quand une valeur change sur MQTT"""
    topic = message.topic.replace(MQTT_BASE_TOPIC, "")
    payload = message.payload.decode()
    if topic in data_store:
        data_store[topic] = payload

mqtt_client = mqtt.Client()
mqtt_client.on_message = on_message
mqtt_client.connect(MQTT_BROKER, 1883, 60)
mqtt_client.subscribe(MQTT_BASE_TOPIC + "#") # S'abonne à tous les paramètres
mqtt_client.loop_start()

def mqtt_publish(param, value):
    """Fonction utilitaire pour publier et garder en mémoire (retain)"""
    data_store[param] = str(value) # Update local
    mqtt_client.publish(MQTT_BASE_TOPIC + param, str(value), retain=True)

def main():
    global debug
    # Modèle pour extraire les valeurs
    pattern = r"Temp: ([\d.-]+)C, Hum: ([\d.]+)%, Press: ([\d.]+)Hpa, Lum: ([\d.]+)Lux, Rain ([\d.]+)mm, Batt: ([\d.]+)V(?:,.*)?"
    while True:
        try:
            # Initialisation du port série
            with serial.Serial(USB_PORT, BAUD_RATE, timeout=1) as ser:
                logger.info(f"{datetime.now()}: Liaison série ouverte sur {USB_PORT} à {BAUD_RATE} bauds.")
                while True:
                    if ser.in_waiting > 0:  # Vérifie si des données sont disponibles
                        ligne = ser.readline().decode('utf-8', errors='ignore').strip()
                        # Rechercher dans la chaîne
                        match = re.search(pattern, ligne)

                        if match:
                            # Extraire les valeurs correspondantes et les convertir en float
                            temperature = float(match.group(1))
                            humidite = float(match.group(2))
                            pression = float(match.group(3))
                            luminosite = float(match.group(4))
                            rain = float(match.group(5))
                            Vbatt = float(match.group(6))

                            # Estimation du pourcentage batterie
                            v_points = [3.30, 3.42, 3.54, 3.61, 3.63, 3.65, 3.67, 3.69, 3.70, 3.71, 3.72, 3.72, 3.73, 3.74, 3.74, 3.75, 3.76, 3.77, 3.77, 3.78, 3.79, 3.80, 3.81, 3.81, 3.82, 3.83, 3.84, 3.85, 3.85, 3.86, 3.87, 3.88, 3.89, 3.90, 3.91, 3.92, 3.93, 3.94, 3.95, 3.96, 3.97, 4.00, 4.03, 4.06, 4.08, 4.10, 4.13, 4.16, 4.18, 4.21, 4.24]
                            p_points = list(range(0, 102, 2))

                            # np.interp(valeur_cherchée, liste_tensions, liste_pourcentages)
                            Pbatt = int(np.interp(Vbatt, v_points, p_points))

                            # Afficher les résultats
                            logger.debug(f"{datetime.now()}: Données envoyées avec succes")
                            #logger.debug(f"Température : {temperature} °C")
                            #logger.debug(f"Humidité : {humidite} %")
                            #logger.debug(f"Pression : {pression} hPa")
                            #logger.debug(f"Luminosité : {luminosite} Lux")
                            logger.debug(f"Batterie : {Vbatt}V ({Pbatt})%")

                            # Créer un client MQTT et publier les variables
                            params = {
                                "temperature": temperature,
                                "humidite": humidite,
                                "pression": pression,
                                "luminosite": luminosite,
                                "pluie": rain,
                                "battery voltage": Vbatt,
                                "battery %": Pbatt
                            }
                                
                            for key, val in params.items():
                                mqtt_client.publish(MQTT_BASE_TOPIC + key, str(val), retain=True)


                    time.sleep(0.1)
        except serial.SerialException as e:
            logger.critical(f"{datetime.now()}: Erreur série : {e}")
            logger.critical("Réinitialisation du port série...")
            time.sleep(2)  # Attendre avant de réessayer
        except OSError as e:
            logger.critical(f"{datetime.now()}: Erreur d'entrée/sortie : {e}")
            logger.critical("Redémarrage du périphérique...")
            time.sleep(2)
        except KeyboardInterrupt:
            logger.warning(f"{datetime.now()}: Arrêt demandé par l'utilisateur")
            break

if __name__ == "__main__":
    main()

