"""Fonctions partagées par les scripts de l'arrosage automatique.

- chargement de la configuration (config.json, hors du code et hors de git)
- création d'un client MQTT authentifié qui se reconnecte tout seul
- journalisation vers la sortie standard (récupérée par journald, qui gère la rotation)
- noms des topics MQTT
"""

import copy
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

DOSSIER = Path(__file__).resolve().parent

# Ordre de recherche du fichier de configuration
CHEMINS_CONFIG = [
    os.environ.get("ARROSAGE_CONFIG"),
    "/etc/arrosage/config.json",
    str(DOSSIER / "config.json"),
]

DEFAUTS = {
    "mqtt": {"hote": "localhost", "port": 1883, "utilisateur": "", "mot_de_passe": ""},
    "position": {"latitude": None, "longitude": None},
    "web": {"hote": "0.0.0.0", "port": 5000, "utilisateur": "admin", "mot_de_passe": ""},
    "arrosage": {
        "nb_zones": 3,
        "heure_auto": "05:00",
        "duree_defaut_min": 10,
        "duree_max_zone_min": 120,
        "duree_max_manu_min": 60,
        "seuil_pluie_passee_mm": 5.0,
        "seuil_pluie_prevue_mm": 2.0,
        "temperature_min_c": 12.0,
        "prog_suspendre_si_pluie": True,
        "meteo_station_valide_h": 2,
    },
    "serie": {"port": "/dev/ttyUSB0", "vitesse": 115200},
}

# --- Topics MQTT ---------------------------------------------------------------
# Commandes des vannes : NON retenues, sur un topic neuf (arrosage/cmd/) pour qu'un
# ancien ordre "1" retenu sous arrosage/config/vanneN ne puisse jamais être rejoué.
def topic_commande_vanne(i):
    return f"arrosage/cmd/vanne{i}"

# Ancien topic de commande (retenu par l'ancienne version) : effacé au démarrage
def ancien_topic_commande_vanne(i):
    return f"arrosage/config/vanne{i}"

# État réel des vannes, publié par l'ESP32 (retenu)
def topic_etat_vanne(i):
    return f"arrosage/status/vanne{i}"

TOPIC_CONFIG = "arrosage/config/"          # réglages (mode, programme...) : retenus
TOPIC_ACTION = "arrosage/cmd/action"       # "lancer_cycle" / "tout_arreter" : non retenu
TOPIC_ESP = "arrosage/status/esp"          # "online" / "offline" (LWT de l'ESP32)
TOPIC_SECURITE = "arrosage/status/securite"  # coupures de sécurité signalées par l'ESP32
TOPIC_DECISION = "arrosage/info/decision"  # dernière décision lisible par un humain
TOPIC_METEO_WEB = "arrosage/info/meteo"    # cumul de pluie passé / prévu (JSON)
TOPIC_METEO = "arrosage/weather/"          # données de la station météo LoRa

CLES_PROGRAMME = ["StrDuree", "StrDateDebut", "StrDateFin", "StrRecurrence"]


def _fusion(base, ajout):
    for cle, val in ajout.items():
        if isinstance(val, dict) and isinstance(base.get(cle), dict):
            _fusion(base[cle], val)
        else:
            base[cle] = val
    return base


def charger_config():
    """Retourne la configuration fusionnée avec les valeurs par défaut."""
    config = copy.deepcopy(DEFAUTS)
    for chemin in CHEMINS_CONFIG:
        if chemin and Path(chemin).is_file():
            with open(chemin, encoding="utf-8") as f:
                _fusion(config, json.load(f))
            config["_fichier"] = chemin
            break
    else:
        config["_fichier"] = None
    return config


def journal(nom):
    logging.basicConfig(
        stream=sys.stdout,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    return logging.getLogger(nom)


def creer_client_mqtt(nom, config, on_connect=None, on_message=None):
    """Client MQTT authentifié ; attend le broker au démarrage puis se reconnecte seul."""
    import paho.mqtt.client as mqtt

    try:  # paho-mqtt 2.x
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=nom)
    except AttributeError:  # paho-mqtt 1.x
        client = mqtt.Client(client_id=nom)

    m = config["mqtt"]
    if m.get("utilisateur"):
        client.username_pw_set(m["utilisateur"], m.get("mot_de_passe", ""))
    if on_connect:
        client.on_connect = on_connect
    if on_message:
        client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    log = logging.getLogger(nom)
    while True:
        try:
            client.connect(m["hote"], int(m["port"]), 60)
            break
        except OSError as e:
            log.warning("Broker MQTT injoignable (%s), nouvel essai dans 5 s", e)
            time.sleep(5)
    client.loop_start()
    return client


_cache_ntp = {"t": 0.0, "ok": True}


def heure_fiable():
    """Vrai si l'horloge est synchronisée (NTP). Le Raspberry Pi n'a pas d'horloge
    sauvegardée : au démarrage sans réseau, l'heure peut être fausse."""
    maintenant = time.monotonic()
    if maintenant - _cache_ntp["t"] < 300 and _cache_ntp["t"]:
        return _cache_ntp["ok"]
    try:
        sortie = subprocess.run(
            ["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        ok = sortie == "yes"
    except (OSError, subprocess.SubprocessError):
        ok = True  # pas de timedatectl : on ne bloque pas
    _cache_ntp.update(t=maintenant, ok=ok)
    return ok
