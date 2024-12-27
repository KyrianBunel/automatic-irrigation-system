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

# Définir le broker et le topic
broker = "localhost"
port = 1883
#topic = "mon/variable"

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
                            x_data = np.array([0, 5, 15, 30, 40, 50, 60, 70, 80, 90, 100])
                            y_data = np.array([3.3, 3.6, 3.7, 3.75, 3.79, 3.83, 3.87, 3.92, 3.97, 4.1, 4.24])
                            spline = si.CubicSpline(x_data, y_data)

                            def g(x):
                                return spline(x) - Vbatt

                            x_min, x_max = 0, 100

                            solution = brentq(g, x_min, x_max)
                            Pbatt = int(solution)  # Convertir en pourcentage entier

                            # Afficher les résultats
                            logger.debug(f"{datetime.now()}: Données envoyées avec succes")
                            #logger.debug(f"Température : {temperature} °C")
                            #logger.debug(f"Humidité : {humidite} %")
                            #logger.debug(f"Pression : {pression} hPa")
                            #logger.debug(f"Luminosité : {luminosite} Lux")
                            logger.debug(f"Batterie : {Vbatt}V ({Pbatt})%")

                            # Créer un client MQTT et publier les variables
                            client = mqtt.Client()
                            client.connect(broker, port, 60)
                            client.publish("Temp", temperature)
                            time.sleep(0.2)
                            client.publish("Hum", humidite)
                            time.sleep(0.2)
                            client.publish("Press", pression)
                            time.sleep(0.2)
                            client.publish("Lum", luminosite)
                            time.sleep(0.2)
                            client.publish("Rain", rain)
                            time.sleep(0.2)
                            client.publish("Batt", Vbatt)
                            time.sleep(0.2)
                            client.publish("BattP", Pbatt)
                            client.disconnect()
                        else:
                            logger.error(f"{datetime.now()}: Impossible d'extraire les données")
                            logger.error(ligne)

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

