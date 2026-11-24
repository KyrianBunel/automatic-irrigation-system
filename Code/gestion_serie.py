"""Passerelle station météo : récepteur LoRa (port série USB) -> MQTT.

Trame attendue (Weather_station_Receive) :
  Temp: 21.30C, Hum: 55.00%, Press: 1013.20Hpa, Lum: 1234.00Lux, Rain 0.00mm, Batt: 3.95V
Chaque mesure est publiée (retenue) sur arrosage/weather/<clé>, avec un horodatage
pour que la logique d'arrosage sache si les données sont récentes.
"""

import re
import time
from datetime import datetime

import serial

import commun

MOTIF = re.compile(
    r"Temp: ([\d.-]+)C, Hum: ([\d.]+)%, Press: ([\d.]+)Hpa, Lum: ([\d.]+)Lux, "
    r"Rain ([\d.]+)mm, Batt: ([\d.]+)V"
)

# Courbe de décharge LiPo : tension (V) pour 0 %, 2 %, ... 100 %
TENSIONS = [3.30, 3.42, 3.54, 3.61, 3.63, 3.65, 3.67, 3.69, 3.70, 3.71, 3.72, 3.72, 3.73,
            3.74, 3.74, 3.75, 3.76, 3.77, 3.77, 3.78, 3.79, 3.80, 3.81, 3.81, 3.82, 3.83,
            3.84, 3.85, 3.85, 3.86, 3.87, 3.88, 3.89, 3.90, 3.91, 3.92, 3.93, 3.94, 3.95,
            3.96, 3.97, 4.00, 4.03, 4.06, 4.08, 4.10, 4.13, 4.16, 4.18, 4.21, 4.24]
POURCENTS = list(range(0, 102, 2))


def pourcentage_batterie(tension):
    """Interpolation linéaire dans la courbe de décharge (remplace numpy.interp)."""
    if tension <= TENSIONS[0]:
        return 0
    if tension >= TENSIONS[-1]:
        return 100
    for k in range(1, len(TENSIONS)):
        v0, v1 = TENSIONS[k - 1], TENSIONS[k]
        if v0 <= tension <= v1:
            if v1 == v0:
                return POURCENTS[k]
            p0, p1 = POURCENTS[k - 1], POURCENTS[k]
            return int(p0 + (tension - v0) * (p1 - p0) / (v1 - v0))
    return 100


def analyser(ligne):
    """Retourne le dictionnaire des mesures, ou None si la trame est invalide."""
    m = MOTIF.search(ligne)
    if not m:
        return None
    temperature, humidite, pression, luminosite, pluie, tension = (float(x) for x in m.groups())
    return {
        "temperature": temperature,
        "humidite": humidite,
        "pression": pression,
        "luminosite": luminosite,
        "pluie": pluie,
        "batterie_tension": tension,
        "batterie_pourcent": pourcentage_batterie(tension),
        "horodatage": datetime.now().isoformat(timespec="seconds"),
    }


def main():
    cfg = commun.charger_config()
    log = commun.journal("meteo")
    port, vitesse = cfg["serie"]["port"], int(cfg["serie"]["vitesse"])
    client = commun.creer_client_mqtt("arrosage-meteo", cfg)

    while True:
        try:
            with serial.Serial(port, vitesse, timeout=2) as ser:
                log.info("Liaison série ouverte sur %s à %d bauds", port, vitesse)
                while True:
                    ligne = ser.readline().decode("utf-8", errors="ignore").strip()
                    if not ligne:
                        continue
                    mesures = analyser(ligne)
                    if mesures is None:
                        log.debug("Trame ignorée : %s", ligne)
                        continue
                    for cle, val in mesures.items():
                        client.publish(commun.TOPIC_METEO + cle, str(val), retain=True)
                    log.info("Station : %.1f °C, %.1f mm, batterie %s %%",
                             mesures["temperature"], mesures["pluie"], mesures["batterie_pourcent"])
        except (serial.SerialException, OSError) as e:
            log.error("Erreur série (%s), nouvel essai dans 5 s", e)
            time.sleep(5)


if __name__ == "__main__":
    main()
