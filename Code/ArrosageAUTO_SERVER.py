"""Interface web (web app iPhone) de l'arrosage automatique.

- connexion par formulaire, session mémorisée 30 jours (pratique depuis l'écran d'accueil) ;
- protection contre les essais de mot de passe en rafale ;
- une page unique qui dialogue en JSON avec /api/... (jeton anti-CSRF dans l'en-tête X-CSRF-Token) ;
- l'affichage reflète l'état RÉEL publié par l'ESP32 ;
- aucune ressource externe (fonctionne sans internet).
"""

import hashlib
import hmac
import json
import secrets
import threading
import time
from datetime import date, datetime, timedelta

from flask import (Flask, Response, jsonify, redirect, render_template, request,
                   send_from_directory, session, url_for)

import commun
from ArrosageAUTO import MODES, jour_programme, lire_date, lire_entier, lire_heure, lire_reel

cfg = commun.charger_config()
log = commun.journal("web")
REGLAGES = cfg["arrosage"]
NB = int(REGLAGES["nb_zones"])
DUREE_MAX = int(REGLAGES["duree_max_zone_min"])
WEB = cfg["web"]


def cle_secrete():
    """Clé des cookies de session : fixe d'un redémarrage à l'autre pour ne pas déconnecter."""
    if WEB.get("cle_secrete"):
        return WEB["cle_secrete"].encode()
    # À défaut, dérivée du mot de passe (changer le mot de passe déconnecte tout le monde)
    return hmac.new(b"arrosage-session", WEB.get("mot_de_passe", "").encode(), hashlib.sha256).digest()


app = Flask(__name__)
app.secret_key = cle_secrete()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_NAME="arrosage",
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
)

verrou = threading.Lock()
etat = {
    "config": {},                                  # arrosage/config/*
    "vannes": {i: None for i in range(1, NB + 1)},  # état réel (ESP32)
    "esp": None,
    "decision": "",
    "en_cours": [],
    "meteo_web": {},
    "station": {},
}
mqtt = None


# =============================================================================
# MQTT
# =============================================================================

def on_connect(client, userdata, flags, rc):
    log.info("Connecté au broker MQTT (code %s)", rc)
    for t in ("arrosage/config/#", "arrosage/status/#", "arrosage/info/#", commun.TOPIC_METEO + "#"):
        client.subscribe(t)


def on_message(client, userdata, message):
    topic = message.topic
    texte = message.payload.decode("utf-8", errors="ignore").strip()
    with verrou:
        if topic.startswith(commun.TOPIC_CONFIG):
            etat["config"][topic[len(commun.TOPIC_CONFIG):]] = texte
        elif topic == commun.TOPIC_ESP:
            etat["esp"] = texte == "online"
        elif topic.startswith("arrosage/status/vanne"):
            i = lire_entier(topic[len("arrosage/status/vanne"):])
            if i in etat["vannes"]:
                etat["vannes"][i] = texte == "1"
        elif topic == commun.TOPIC_DECISION:
            etat["decision"] = texte
        elif topic in (commun.TOPIC_METEO_WEB, commun.TOPIC_EN_COURS):
            try:
                valeur = json.loads(texte) if texte else None
            except ValueError:
                return
            if topic == commun.TOPIC_METEO_WEB:
                etat["meteo_web"] = valeur or {}
            else:
                etat["en_cours"] = valeur or []
        elif topic.startswith(commun.TOPIC_METEO):
            etat["station"][topic[len(commun.TOPIC_METEO):]] = texte


def publier(topic, valeur, retain=False):
    mqtt.publish(topic, str(valeur), qos=1, retain=retain)


def instantane():
    with verrou:
        return json.loads(json.dumps(etat, default=str))  # copie profonde


# =============================================================================
# Sécurité : session, anti-bruteforce, CSRF, en-têtes
# =============================================================================

ECHECS = {}           # ip -> [nombre d'échecs, bloqué jusqu'à (time.time())]
ECHECS_MAX = 5
BLOCAGE_S = 300
PUBLIC = {"connexion", "static", "manifeste", "icone"}


def bloque(ip):
    nb, jusqua = ECHECS.get(ip, (0, 0))
    return jusqua > time.time()


def noter_echec(ip):
    nb, _ = ECHECS.get(ip, (0, 0))
    nb += 1
    ECHECS[ip] = [nb, time.time() + BLOCAGE_S if nb >= ECHECS_MAX else 0]


def identifiants_valides(utilisateur, mot_de_passe):
    attendu = WEB.get("mot_de_passe", "")
    return bool(attendu) and hmac.compare_digest(utilisateur, WEB.get("utilisateur", "admin")) \
        and hmac.compare_digest(mot_de_passe, attendu)


@app.before_request
def controle_acces():
    if request.endpoint in PUBLIC:
        return None
    if not session.get("connecte"):
        if request.path.startswith("/api/"):
            return jsonify(ok=False, message="Session expirée, reconnectez-vous."), 401
        return redirect(url_for("connexion"))
    if request.method == "POST":
        jeton = request.headers.get("X-CSRF-Token") or request.form.get("csrf", "")
        if not jeton or not hmac.compare_digest(jeton, session.get("csrf", "")):
            return jsonify(ok=False, message="Jeton de sécurité invalide : rechargez la page."), 400
    return None


@app.after_request
def entetes(reponse):
    reponse.headers["X-Frame-Options"] = "DENY"
    reponse.headers["X-Content-Type-Options"] = "nosniff"
    reponse.headers["Referrer-Policy"] = "no-referrer"
    reponse.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
        "frame-ancestors 'none'; form-action 'self'")
    if not request.path.startswith("/static/"):
        reponse.headers["Cache-Control"] = "no-store"
    return reponse


@app.route("/connexion", methods=["GET", "POST"])
def connexion():
    if not WEB.get("mot_de_passe"):
        return Response("Mot de passe web non configuré (config.json, section \"web\").", 503)
    erreur = None
    ip = request.remote_addr or "?"
    if request.method == "POST":
        if bloque(ip):
            erreur = "Trop d'essais. Réessayez dans 5 minutes."
        elif identifiants_valides(request.form.get("utilisateur", ""), request.form.get("mot_de_passe", "")):
            ECHECS.pop(ip, None)
            session.clear()
            session.permanent = True
            session["connecte"] = True
            session["csrf"] = secrets.token_urlsafe(32)
            return redirect(url_for("accueil"))
        else:
            noter_echec(ip)
            log.warning("Échec de connexion depuis %s", ip)
            erreur = "Identifiant ou mot de passe incorrect."
    return render_template("connexion.html", erreur=erreur), (401 if erreur else 200)


@app.post("/deconnexion")
def deconnexion():
    session.clear()
    return redirect(url_for("connexion"))


# =============================================================================
# Programme : validation et prochain arrosage
# =============================================================================

def valider_programme(form, nb_zones, duree_max, aujourd_hui):
    """Retourne (parametres_mqtt, erreurs)."""
    erreurs = []
    duree = lire_entier(form.get("duree"))
    if duree is None or not 1 <= duree <= duree_max:
        erreurs.append(f"La durée par zone doit être comprise entre 1 et {duree_max} minutes.")
        duree = None
    recurrence = lire_entier(form.get("recurrence"))
    if recurrence is None or not 1 <= recurrence <= 365:
        erreurs.append("Choisissez un arrosage tous les 1 à 365 jours.")
    debut, fin = lire_date(form.get("dateDebut")), lire_date(form.get("dateFin"))
    if debut is None:
        erreurs.append("Indiquez une date de début.")
    if fin is None:
        erreurs.append("Indiquez une date de fin.")
    if debut and fin and fin < debut:
        erreurs.append("La date de fin doit être après la date de début.")
    elif fin and fin < aujourd_hui:
        erreurs.append("La date de fin est déjà passée : le programme ne se déclencherait jamais.")

    zones, creneaux = {}, []
    for i in range(1, nb_zones + 1):
        active = str(form.get(f"zone{i}", "")).lower() in ("on", "1", "true")
        heure_txt = str(form.get(f"heureDebut{i}", "")).strip()
        zones[i] = (active, heure_txt)
        if not active:
            continue
        hm = lire_heure(heure_txt)
        if hm is None:
            erreurs.append(f"Zone {i} : indiquez une heure de début.")
            continue
        debut_min = hm[0] * 60 + hm[1]
        if duree and debut_min + duree > 24 * 60:
            erreurs.append(f"Zone {i} : l'arrosage doit se terminer avant minuit.")
        creneaux.append((debut_min, i))
    if not any(a for a, _ in zones.values()):
        erreurs.append("Choisissez au moins une zone.")

    if duree:
        creneaux.sort()
        for (s1, z1), (s2, z2) in zip(creneaux, creneaux[1:]):
            if s2 < s1 + duree:
                erreurs.append(f"Les zones {z1} et {z2} se chevauchent : une seule vanne s'ouvre à la fois. "
                               f"Décalez la zone {z2} d'au moins {s1 + duree - s2} min.")

    if erreurs:
        return {}, erreurs
    params = {
        "StrDuree": duree,
        "StrRecurrence": recurrence,
        "StrDateDebut": debut.isoformat(),
        "StrDateFin": fin.isoformat(),
    }
    for i, (active, heure_txt) in zones.items():
        params[f"StrZone{i}"] = "on" if active else "off"
        params[f"StrDebut{i}"] = heure_txt if active else ""
    return params, []


JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def nom_jour(jour, aujourd_hui):
    ecart = (jour - aujourd_hui).days
    if ecart == 0:
        return "aujourd'hui"
    if ecart == 1:
        return "demain"
    return f"{JOURS[jour.weekday()]} {jour:%d/%m}"


def prochain_arrosage(config, maintenant):
    """{"quand": "jeudi 26/11", "creneaux": [{"zone": 1, "heure": "06:00"}, ...]} ou None."""
    duree = lire_entier(config.get("StrDuree"), 0) or 0
    for decalage in range(0, 366):
        jour = maintenant.date() + timedelta(days=decalage)
        if not jour_programme(config, jour):
            continue
        creneaux = []
        for i in range(1, NB + 1):
            hm = lire_heure(config.get(f"StrDebut{i}"))
            if str(config.get(f"StrZone{i}", "off")).lower() == "on" and hm:
                fin = datetime.combine(jour, datetime.min.time()).replace(hour=hm[0], minute=hm[1]) \
                    + timedelta(minutes=duree)
                if fin > maintenant:
                    creneaux.append({"zone": i, "heure": f"{hm[0]:02d}:{hm[1]:02d}"})
        if creneaux:
            return {"quand": nom_jour(jour, maintenant.date()),
                    "creneaux": sorted(creneaux, key=lambda c: c["heure"])}
    return None


def prochaine_verification(maintenant):
    hm = lire_heure(REGLAGES["heure_auto"]) or (5, 0)
    prochaine = maintenant.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
    if prochaine <= maintenant:
        prochaine += timedelta(days=1)
    return f"{nom_jour(prochaine.date(), maintenant.date())} à {hm[0]:02d}:{hm[1]:02d}"


def criteres_meteo(s):
    """Les trois conditions du mode Météo, avec la valeur actuelle et le verdict."""
    station, web = s["station"], s["meteo_web"]
    temp = lire_reel(station.get("temperature"))
    if temp is None:
        temp = lire_reel(web.get("temperature"))
    connues = [p for p in (lire_reel(station.get("pluie")), lire_reel(web.get("pluie_passee"))) if p is not None]
    pluie_passee = max(connues) if connues else None
    pluie_prevue = lire_reel(web.get("pluie_prevue"))

    def critere(nom, condition, valeur, ok, unite):
        return {"nom": nom, "condition": condition,
                "valeur": None if valeur is None else f"{valeur:.1f} {unite}".replace(".", ","),
                "ok": None if valeur is None else ok(valeur)}

    sp, sf, tm = REGLAGES["seuil_pluie_passee_mm"], REGLAGES["seuil_pluie_prevue_mm"], REGLAGES["temperature_min_c"]
    return [
        critere("Pluie des 2 derniers jours", f"moins de {sp:g} mm", pluie_passee, lambda x: x < sp, "mm"),
        critere("Pluie prévue sur 2 jours", f"moins de {sf:g} mm", pluie_prevue, lambda x: x < sf, "mm"),
        critere("Température", f"plus de {tm:g} °C", temp, lambda x: x > tm, "°C"),
    ]


def programme_actuel(config):
    p = {
        "duree": lire_entier(config.get("StrDuree"), REGLAGES["duree_defaut_min"]),
        "recurrence": lire_entier(config.get("StrRecurrence"), 1) or 1,
        "dateDebut": str(lire_date(config.get("StrDateDebut")) or ""),
        "dateFin": str(lire_date(config.get("StrDateFin")) or ""),
        "zones": [],
    }
    for i in range(1, NB + 1):
        active = str(config.get(f"StrZone{i}", "off")).lower() == "on"
        p["zones"].append({"zone": i, "active": active,
                           "heure": config.get(f"StrDebut{i}", "") if active else ""})
    return p


def mode_actuel(s):
    m = s["config"].get("mode")
    return m if m in MODES else "MANU"


# =============================================================================
# Pages et API
# =============================================================================

@app.get("/")
def accueil():
    return render_template("index.html", csrf=session["csrf"], nb=NB)


@app.get("/dashboard")
@app.get("/accueil")
def anciennes_pages():
    return redirect(url_for("accueil"))


@app.get("/manifest.webmanifest")
def manifeste():
    return send_from_directory(app.static_folder, "manifest.webmanifest",
                               mimetype="application/manifest+json")


@app.get("/apple-touch-icon.png")
def icone():
    return send_from_directory(app.static_folder, "icones/apple-touch-icon.png")


@app.get("/api/etat")
def api_etat():
    s = instantane()
    maintenant = datetime.now()
    fins = {e.get("zone"): e for e in s["en_cours"] if isinstance(e, dict)}
    zones = []
    for i in range(1, NB + 1):
        ouverte = s["vannes"].get(str(i))
        info = fins.get(i) if ouverte else None
        reste = None
        if info and info.get("fin"):
            try:
                reste = max(0, int((datetime.fromisoformat(info["fin"]) - maintenant).total_seconds()))
            except ValueError:
                pass
        source = info.get("source") if info else None
        if source == "MANU":
            total = REGLAGES["duree_max_manu_min"] * 60
        elif source:
            total = lire_entier(s["config"].get("StrDuree"), REGLAGES["duree_defaut_min"]) * 60
        else:
            total = None
        zones.append({"zone": i, "ouverte": ouverte, "reste_s": reste, "total_s": total, "source": source})
    return jsonify({
        "mode": mode_actuel(s),
        "esp": s["esp"],
        "zones": zones,
        "decision": s["decision"],
        "heure": maintenant.strftime("%H:%M"),
        "auto": {
            "heure": REGLAGES["heure_auto"],
            "prochaine": prochaine_verification(maintenant),
            "duree": lire_entier(s["config"].get("StrDuree"), REGLAGES["duree_defaut_min"]),
            "criteres": criteres_meteo(s),
        },
        "programme": programme_actuel(s["config"]),
        "prochain": prochain_arrosage(s["config"], maintenant),
        "station": {
            "temperature": lire_reel(s["station"].get("temperature")),
            "humidite": lire_reel(s["station"].get("humidite")),
            "pluie": lire_reel(s["station"].get("pluie")),
            "batterie": lire_entier(s["station"].get("batterie_pourcent")),
            "horodatage": s["station"].get("horodatage"),
        },
        "limites": {"duree_max": DUREE_MAX, "manu_min": REGLAGES["duree_max_manu_min"],
                    "pluie_prog": REGLAGES["prog_suspendre_si_pluie"],
                    "seuil_pluie": REGLAGES["seuil_pluie_passee_mm"]},
    })


def donnees():
    return request.get_json(silent=True) or request.form


def reponse(ok, message, code=200, **extra):
    return jsonify(ok=ok, message=message, **extra), code


@app.post("/api/mode")
def api_mode():
    mode = donnees().get("mode")
    if mode not in MODES:
        return reponse(False, "Mode inconnu.", 400)
    publier(commun.TOPIC_CONFIG + "mode", mode, retain=True)
    return reponse(True, "Mode changé. Les vannes ont été fermées.")


@app.post("/api/vanne/<int:i>")
def api_vanne(i):
    s = instantane()
    voulu = str(donnees().get("ouvrir", "")).lower() in ("1", "true", "on")
    if not 1 <= i <= NB:
        return reponse(False, "Zone inconnue.", 404)
    if voulu and mode_actuel(s) != "MANU":
        return reponse(False, "Passez en mode Manuel pour ouvrir une zone.", 409)
    if voulu and not s["esp"]:
        return reponse(False, "Le boîtier des vannes ne répond pas.", 503)
    publier(commun.topic_commande_vanne(i), "1" if voulu else "0")
    return reponse(True, f"Zone {i} {'ouverte' if voulu else 'fermée'}.")


@app.post("/api/arreter")
def api_arreter():
    publier(commun.TOPIC_ACTION, "tout_arreter")
    for i in range(1, NB + 1):
        publier(commun.topic_commande_vanne(i), "0")
    return reponse(True, "Tout est arrêté.")


@app.post("/api/cycle")
def api_cycle():
    if mode_actuel(instantane()) != "AUTO":
        return reponse(False, "Passez en mode Météo pour arroser toutes les zones.", 409)
    publier(commun.TOPIC_ACTION, "lancer_cycle")
    return reponse(True, "Arrosage lancé : les zones vont s'arroser l'une après l'autre.")


@app.post("/api/duree")
def api_duree():
    duree = lire_entier(donnees().get("duree"))
    if duree is None or not 1 <= duree <= DUREE_MAX:
        return reponse(False, f"Choisissez une durée entre 1 et {DUREE_MAX} minutes.", 400)
    publier(commun.TOPIC_CONFIG + "StrDuree", duree, retain=True)
    return reponse(True, f"{duree} min par zone.")


@app.post("/api/programme")
def api_programme():
    params, erreurs = valider_programme(donnees(), NB, DUREE_MAX, date.today())
    if erreurs:
        return reponse(False, "Programme non enregistré.", 400, erreurs=erreurs)
    for cle, val in params.items():
        publier(commun.TOPIC_CONFIG + cle, val, retain=True)
    log.info("Nouveau programme : %s", params)
    return reponse(True, "Programme enregistré.")


def main():
    global mqtt
    if not WEB.get("mot_de_passe"):
        log.error("Aucun mot de passe web dans config.json : l'interface refusera les connexions.")
    mqtt = commun.creer_client_mqtt("arrosage-web", cfg, on_connect, on_message)
    hote, port = WEB.get("hote", "0.0.0.0"), int(WEB.get("port", 5000))
    try:
        from waitress import serve
        log.info("Interface web sur http://%s:%s (waitress)", hote, port)
        serve(app, host=hote, port=port, threads=4)
    except ImportError:
        log.warning("waitress absent : serveur de développement Flask utilisé")
        app.run(host=hote, port=port, threaded=True)


if __name__ == "__main__":
    main()
