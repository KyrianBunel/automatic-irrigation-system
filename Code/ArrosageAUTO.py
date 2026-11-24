"""Logique d'arrosage.

- MANU : l'utilisateur commande les vannes ; ce script les referme au bout de
  `duree_max_manu_min` pour éviter un oubli.
- AUTO : chaque jour à `heure_auto`, décision selon la météo (station LoRa + Open-Meteo),
  puis arrosage séquentiel des zones (une à la fois).
- PROG : programme saisi dans l'interface (dates de début/fin, récurrence, heure par zone).

Une seule vanne est ouverte à la fois dans les modes automatiques. La dernière décision
est publiée sur arrosage/info/decision pour être affichée dans l'interface et dans HA.
"""

import json
import threading
import time
from datetime import datetime, timedelta

import commun

MODES = ("MANU", "AUTO", "PROG")
INTERVALLE_RENVOI_S = 10       # renvoi d'un ordre si l'état réel ne suit pas
INTERVALLE_METEO_S = 30 * 60   # mise à jour Open-Meteo


# =============================================================================
# Fonctions pures (sans MQTT ni réseau) : testables isolément
# =============================================================================

def lire_date(texte):
    """'2025-06-19' ou '2025/06/19' -> date ; sinon None."""
    if not texte:
        return None
    try:
        return datetime.strptime(str(texte).strip().replace("/", "-"), "%Y-%m-%d").date()
    except ValueError:
        return None


def lire_heure(texte):
    """'05:30' -> (5, 30) ; sinon None."""
    try:
        h, m = (int(x) for x in str(texte).strip().split(":")[:2])
    except (ValueError, AttributeError):
        return None
    return (h, m) if 0 <= h < 24 and 0 <= m < 60 else None


def lire_entier(texte, defaut=None):
    try:
        return int(float(texte))
    except (TypeError, ValueError):
        return defaut


def lire_reel(texte, defaut=None):
    try:
        return float(texte)
    except (TypeError, ValueError):
        return defaut


def jour_programme(prog, jour):
    """Vrai si `jour` est un jour d'arrosage du programme (début ≤ jour ≤ fin, récurrence)."""
    debut = lire_date(prog.get("StrDateDebut"))
    fin = lire_date(prog.get("StrDateFin"))
    recurrence = lire_entier(prog.get("StrRecurrence"), 0)
    if debut is None or not recurrence or recurrence < 1:
        return False
    if jour < debut or (fin is not None and jour > fin):
        return False
    return (jour - debut).days % recurrence == 0


def zone_prog_active(prog, maintenant, nb_zones, duree_max):
    """Zone à arroser maintenant selon le programme (une seule à la fois), sinon None."""
    if not jour_programme(prog, maintenant.date()):
        return None
    duree = lire_entier(prog.get("StrDuree"), 0)
    if not duree or duree < 1:
        return None
    duree = min(duree, duree_max)
    for i in range(1, nb_zones + 1):
        if str(prog.get(f"StrZone{i}", "off")).lower() != "on":
            continue
        hm = lire_heure(prog.get(f"StrDebut{i}"))
        if hm is None:
            continue
        debut = maintenant.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
        if debut <= maintenant < debut + timedelta(minutes=duree):
            return i
    return None


def zone_cycle_auto(debut_cycle, maintenant, duree_min, nb_zones):
    """Zone active d'un cycle séquentiel (1..nb_zones), 0 quand le cycle est terminé."""
    ecoule_min = (maintenant - debut_cycle).total_seconds() / 60
    if ecoule_min < 0 or duree_min < 1:
        return 0
    zone = int(ecoule_min // duree_min) + 1
    return zone if zone <= nb_zones else 0


def pluie_recente(*valeurs):
    connues = [v for v in valeurs if v is not None]
    return max(connues) if connues else None


def decision_auto(temperature, pluie_passee, pluie_prevue, reglages):
    """Retourne (arroser, raison)."""
    seuil_passe = reglages["seuil_pluie_passee_mm"]
    seuil_prevu = reglages["seuil_pluie_prevue_mm"]
    t_min = reglages["temperature_min_c"]
    if temperature is None:
        return False, "pas d'arrosage : température inconnue (station et prévisions indisponibles)"
    if pluie_passee is None or pluie_prevue is None:
        return False, "pas d'arrosage : données de pluie indisponibles"
    if pluie_passee >= seuil_passe:
        return False, f"pas d'arrosage : {pluie_passee:.1f} mm tombés récemment (seuil {seuil_passe} mm)"
    if pluie_prevue >= seuil_prevu:
        return False, f"pas d'arrosage : {pluie_prevue:.1f} mm prévus sous 48 h (seuil {seuil_prevu} mm)"
    if temperature <= t_min:
        return False, f"pas d'arrosage : {temperature:.1f} °C (il faut plus de {t_min} °C)"
    return True, (f"arrosage lancé : {pluie_passee:.1f} mm tombés, {pluie_prevue:.1f} mm prévus, "
                  f"{temperature:.1f} °C")


# =============================================================================
# Contrôleur
# =============================================================================

class Controleur:
    def __init__(self, config):
        self.cfg = config
        self.reglages = config["arrosage"]
        self.nb = int(self.reglages["nb_zones"])
        self.log = commun.journal("arrosage")
        self.verrou = threading.Lock()

        self.config = {"mode": None}            # topics arrosage/config/* (retenus)
        self.vannes = {i: None for i in range(1, self.nb + 1)}   # état réel (ESP)
        self.ouverte_depuis = {i: None for i in range(1, self.nb + 1)}
        self.dernier_envoi = {i: 0.0 for i in range(1, self.nb + 1)}
        self.esp_en_ligne = None
        self.station = {}                       # arrosage/weather/*
        self.meteo_web = {"pluie_passee": None, "pluie_prevue": None, "temperature": None}
        self.actions = []

        self.mode_precedent = None
        self.cycle_debut = None                 # datetime du début du cycle AUTO
        self.derniere_eval_auto = None          # date de la dernière décision AUTO
        self.creneaux_annules = set()           # (date, zone) arrêtés à la main en PROG
        self.zone_prog_precedente = None
        self.derniere_decision = None
        self.client = None

    # --- MQTT ---------------------------------------------------------------
    def on_connect(self, client, userdata, flags, rc):
        self.log.info("Connecté au broker MQTT (code %s)", rc)
        client.subscribe("arrosage/config/#")
        client.subscribe("arrosage/cmd/action")
        client.subscribe("arrosage/status/#")
        client.subscribe(commun.TOPIC_METEO + "#")
        # Efface les anciens ordres de vanne retenus par l'ancienne version
        for i in range(1, self.nb + 1):
            client.publish(commun.ancien_topic_commande_vanne(i), "", retain=True)
        publier_decouverte_ha(client, self.nb)

    def on_message(self, client, userdata, message):
        topic = message.topic
        texte = message.payload.decode("utf-8", errors="ignore").strip()
        with self.verrou:
            if topic == commun.TOPIC_ACTION:
                if texte:
                    self.actions.append(texte)
            elif topic.startswith(commun.TOPIC_CONFIG):
                cle = topic[len(commun.TOPIC_CONFIG):]
                if not cle.startswith("vanne"):
                    self.config[cle] = texte
            elif topic == commun.TOPIC_ESP:
                self.esp_en_ligne = texte == "online"
            elif topic == commun.TOPIC_SECURITE:
                self.log.warning("ESP32 : %s", texte)
                self.publier_decision(f"coupure de sécurité : {texte}")
            elif topic.startswith("arrosage/status/vanne"):
                i = lire_entier(topic[len("arrosage/status/vanne"):])
                if i in self.vannes:
                    ouverte = texte == "1"
                    if ouverte and not self.vannes[i]:
                        self.ouverte_depuis[i] = time.monotonic()
                    if not ouverte:
                        self.ouverte_depuis[i] = None
                    self.vannes[i] = ouverte
            elif topic.startswith(commun.TOPIC_METEO):
                self.station[topic[len(commun.TOPIC_METEO):]] = texte

    def commander(self, i, ouvrir, force=False):
        self.dernier_envoi[i] = time.monotonic()
        self.client.publish(commun.topic_commande_vanne(i), "1" if ouvrir else "0", qos=1, retain=False)
        if force or ouvrir:
            self.log.info("Ordre vanne %d -> %s", i, "OUVRIR" if ouvrir else "fermer")

    def tout_fermer(self):
        for i in range(1, self.nb + 1):
            self.commander(i, False, force=True)

    def synchroniser(self, zone_voulue):
        """Mode automatique : seule `zone_voulue` (ou aucune si 0/None) doit être ouverte."""
        maintenant = time.monotonic()
        for i in range(1, self.nb + 1):
            voulu = i == zone_voulue
            reel = self.vannes[i]
            if reel == voulu or (reel is None and not voulu):
                continue
            if maintenant - self.dernier_envoi[i] >= INTERVALLE_RENVOI_S:
                self.commander(i, voulu)

    def publier_decision(self, texte):
        if texte == self.derniere_decision:
            return
        self.derniere_decision = texte
        horodate = datetime.now().strftime("%d/%m %H:%M")
        self.log.info("Décision : %s", texte)
        if self.client:
            self.client.publish(commun.TOPIC_DECISION, f"{horodate} - {texte}", retain=True)

    # --- Météo --------------------------------------------------------------
    def valeur_station(self, cle):
        """Valeur de la station LoRa si elle est récente, sinon None."""
        horodatage = self.station.get("horodatage")
        try:
            age = datetime.now() - datetime.fromisoformat(horodatage)
        except (TypeError, ValueError):
            return None
        if age > timedelta(hours=self.reglages["meteo_station_valide_h"]):
            return None
        return lire_reel(self.station.get(cle))

    def boucle_meteo(self):
        lat = self.cfg["position"].get("latitude")
        lon = self.cfg["position"].get("longitude")
        if lat is None or lon is None:
            self.log.warning("Position non configurée : prévisions Open-Meteo désactivées")
            return
        import requests
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat, "longitude": lon, "timezone": "auto",
            "daily": "precipitation_sum", "current": "temperature_2m",
            "past_days": 2, "forecast_days": 3,
        }
        while True:
            try:
                res = requests.get(url, params=params, timeout=15)
                res.raise_for_status()
                donnees = res.json()
                pluie = [v or 0.0 for v in donnees["daily"]["precipitation_sum"]]
                # index : 0 = avant-hier, 1 = hier, 2 = aujourd'hui, 3 = demain, 4 = après-demain
                self.meteo_web = {
                    "pluie_passee": round(sum(pluie[0:2]), 1),
                    "pluie_prevue": round(sum(pluie[2:4]), 1),  # aujourd'hui + demain
                    "temperature": donnees.get("current", {}).get("temperature_2m"),
                    "maj": datetime.now().isoformat(timespec="minutes"),
                }
                self.client.publish(commun.TOPIC_METEO_WEB, json.dumps(self.meteo_web), retain=True)
                self.log.info("Météo : %s", self.meteo_web)
            except Exception as e:  # réseau, JSON inattendu...
                self.log.warning("Erreur Open-Meteo : %s", e)
            time.sleep(INTERVALLE_METEO_S)

    def conditions_meteo(self):
        temperature = self.valeur_station("temperature")
        if temperature is None:
            temperature = self.meteo_web.get("temperature")
        pluie_passee = pluie_recente(self.valeur_station("pluie"), self.meteo_web.get("pluie_passee"))
        return temperature, pluie_passee, self.meteo_web.get("pluie_prevue")

    # --- Boucle principale --------------------------------------------------
    def duree_zone(self):
        duree = lire_entier(self.config.get("StrDuree"), self.reglages["duree_defaut_min"])
        return max(1, min(duree, self.reglages["duree_max_zone_min"]))

    def traiter_actions(self, mode, maintenant):
        while self.actions:
            action = self.actions.pop(0)
            if action == "tout_arreter":
                self.cycle_debut = None
                zone = zone_prog_active(self.config, maintenant, self.nb, self.reglages["duree_max_zone_min"])
                if mode == "PROG" and zone:
                    self.creneaux_annules.add((maintenant.date(), zone))
                self.zone_prog_precedente = None
                self.tout_fermer()
                self.publier_decision("arrêt manuel de toutes les vannes")
            elif action == "lancer_cycle":
                if mode == "AUTO":
                    self.cycle_debut = maintenant
                    self.publier_decision("cycle lancé à la main (météo ignorée)")
                else:
                    self.publier_decision("lancement ignoré : passez d'abord en mode AUTO")

    def tour(self, maintenant):
        with self.verrou:
            mode = self.config.get("mode")
            mode = mode if mode in MODES else "MANU"

            # Changement de mode : on repart d'un état propre
            if self.mode_precedent is not None and mode != self.mode_precedent:
                self.log.info("Mode %s -> %s : fermeture des vannes", self.mode_precedent, mode)
                self.cycle_debut = None
                self.zone_prog_precedente = None
                self.tout_fermer()
                self.publier_decision(f"mode {mode} activé")
            self.mode_precedent = mode

            self.traiter_actions(mode, maintenant)

            if mode == "MANU":
                limite = self.reglages["duree_max_manu_min"] * 60
                for i, depuis in self.ouverte_depuis.items():
                    if depuis and time.monotonic() - depuis >= limite \
                            and time.monotonic() - self.dernier_envoi[i] >= INTERVALLE_RENVOI_S:
                        self.commander(i, False, force=True)
                        self.publier_decision(
                            f"vanne {i} refermée automatiquement après "
                            f"{self.reglages['duree_max_manu_min']} min en MANU")
                return

            fiable = commun.heure_fiable()

            if mode == "AUTO":
                heure = lire_heure(self.reglages["heure_auto"])
                if (heure and (maintenant.hour, maintenant.minute) == heure
                        and self.derniere_eval_auto != maintenant.date()):
                    self.derniere_eval_auto = maintenant.date()
                    if not fiable:
                        self.publier_decision("pas d'arrosage : l'heure du Raspberry Pi n'est pas synchronisée")
                    else:
                        arroser, raison = decision_auto(*self.conditions_meteo(), self.reglages)
                        self.publier_decision(raison)
                        if arroser:
                            self.cycle_debut = maintenant
                zone = 0
                if self.cycle_debut:
                    zone = zone_cycle_auto(self.cycle_debut, maintenant, self.duree_zone(), self.nb)
                    if zone == 0:
                        self.cycle_debut = None
                        self.publier_decision("cycle AUTO terminé")
                self.synchroniser(zone)
                return

            # PROG
            zone = zone_prog_active(self.config, maintenant, self.nb, self.reglages["duree_max_zone_min"])
            if zone and (maintenant.date(), zone) in self.creneaux_annules:
                zone = None
            if zone and not fiable:
                self.publier_decision("programme suspendu : l'heure du Raspberry Pi n'est pas synchronisée")
                zone = None
            if zone and self.reglages["prog_suspendre_si_pluie"]:
                _, pluie_passee, _ = self.conditions_meteo()
                seuil = self.reglages["seuil_pluie_passee_mm"]
                if pluie_passee is not None and pluie_passee >= seuil:
                    self.publier_decision(f"programme suspendu : {pluie_passee:.1f} mm tombés récemment")
                    zone = None
            if zone and zone != self.zone_prog_precedente:
                self.publier_decision(f"programme : zone {zone} en cours")
            elif not zone and self.zone_prog_precedente:
                self.publier_decision(f"programme : zone {self.zone_prog_precedente} terminée")
            self.zone_prog_precedente = zone
            self.synchroniser(zone)

    def demarrer(self):
        self.log.info("Configuration : %s", self.cfg.get("_fichier") or "valeurs par défaut")
        self.client = commun.creer_client_mqtt("arrosage-logique", self.cfg,
                                               self.on_connect, self.on_message)
        threading.Thread(target=self.boucle_meteo, daemon=True).start()
        time.sleep(2)  # laisse arriver les messages retenus (mode, programme, états)
        self.log.info("Logique d'arrosage démarrée")
        while True:
            try:
                self.tour(datetime.now())
            except Exception:
                # Une erreur ne doit jamais laisser une vanne ouverte
                self.log.exception("Erreur dans la boucle : fermeture des vannes par sécurité")
                try:
                    self.tout_fermer()
                except Exception:
                    pass
                time.sleep(5)
            time.sleep(1)


# =============================================================================
# Découverte automatique Home Assistant
# =============================================================================

def publier_decouverte_ha(client, nb_zones):
    appareil = {
        "identifiers": ["arrosage_jardin_esp32"],
        "name": "Contrôleur Arrosage Automatique",
        "manufacturer": "DIY",
        "model": "ESP32 + RPi",
    }
    dispo = {
        "availability_topic": commun.TOPIC_ESP,
        "payload_available": "online",
        "payload_not_available": "offline",
    }

    def envoyer(composant, objet, contenu):
        client.publish(f"homeassistant/{composant}/arrosage/{objet}/config",
                       json.dumps(contenu), retain=True)

    for i in range(1, nb_zones + 1):
        envoyer("switch", f"vanne{i}", {
            "name": f"Vanne {i}",
            "command_topic": commun.topic_commande_vanne(i),
            "state_topic": commun.topic_etat_vanne(i),
            "payload_on": "1", "payload_off": "0",
            "retain": False,
            "unique_id": f"arrosage_vanne_{i}",
            "device": appareil, **dispo,
        })

    envoyer("select", "mode", {
        "name": "Mode d'arrosage",
        "command_topic": "arrosage/config/mode", "state_topic": "arrosage/config/mode",
        "options": list(MODES), "retain": True,
        "unique_id": "arrosage_mode", "device": appareil,
    })
    envoyer("number", "duree", {
        "name": "Durée par zone",
        "command_topic": "arrosage/config/StrDuree", "state_topic": "arrosage/config/StrDuree",
        "min": 1, "max": 120, "step": 1, "mode": "box", "retain": True,
        "unit_of_measurement": "min",
        "unique_id": "arrosage_duree", "device": appareil,
    })
    envoyer("button", "lancer_cycle", {
        "name": "Lancer un cycle maintenant (AUTO)",
        "command_topic": commun.TOPIC_ACTION, "payload_press": "lancer_cycle",
        "unique_id": "arrosage_lancer_cycle", "device": appareil,
    })
    envoyer("button", "tout_arreter", {
        "name": "Tout arrêter",
        "command_topic": commun.TOPIC_ACTION, "payload_press": "tout_arreter",
        "unique_id": "arrosage_tout_arreter", "device": appareil,
    })
    envoyer("sensor", "decision", {
        "name": "Dernière décision",
        "state_topic": commun.TOPIC_DECISION, "icon": "mdi:sprinkler-variant",
        "unique_id": "arrosage_decision", "device": appareil,
    })
    envoyer("binary_sensor", "esp", {
        "name": "ESP32 vannes en ligne",
        "state_topic": commun.TOPIC_ESP, "payload_on": "online", "payload_off": "offline",
        "device_class": "connectivity",
        "unique_id": "arrosage_esp_en_ligne", "device": appareil,
    })

    station = {
        "identifiers": ["weather_station_lora_jardin"],
        "name": "Station Météo LoRa",
        "manufacturer": "DIY",
        "model": "CubeCell ASR650x",
    }
    capteurs = {
        # identifiant HA : (topic, nom, unité, classe)
        "temperature": ("temperature", "Température extérieure", "°C", "temperature"),
        "humidite": ("humidite", "Humidité extérieure", "%", "humidity"),
        "pression": ("pression", "Pression atmosphérique", "hPa", "atmospheric_pressure"),
        "luminosite": ("luminosite", "Luminosité", "lx", "illuminance"),
        "pluie": ("pluie", "Pluie (dernière heure)", "mm", "precipitation"),
        "battery_voltage": ("batterie_tension", "Tension batterie météo", "V", "voltage"),
        "battery_percent": ("batterie_pourcent", "Batterie météo", "%", "battery"),
    }
    for cle, (topic, nom, unite, classe) in capteurs.items():
        client.publish(f"homeassistant/sensor/arrosage_meteo/{cle}/config", json.dumps({
            "name": nom,
            "state_topic": commun.TOPIC_METEO + topic,
            "unit_of_measurement": unite,
            "device_class": classe,
            "expire_after": 3 * 3600,  # « indisponible » si la station se tait 3 h
            "unique_id": f"station_meteo_{cle}",
            "device": station,
        }), retain=True)


if __name__ == "__main__":
    Controleur(commun.charger_config()).demarrer()
