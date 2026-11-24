"""Interface web de l'arrosage automatique.

- accès protégé par identifiant / mot de passe (config.json, section "web") ;
- toutes les actions passent par des formulaires POST avec jeton anti-CSRF ;
- l'affichage reflète l'état RÉEL publié par l'ESP32 (arrosage/status/vanneN),
  rafraîchi automatiquement toutes les 3 s ;
- aucune ressource externe (fonctionne sans internet).
"""

import hmac
import secrets
import threading
from datetime import date, datetime, timedelta

from flask import (Flask, Response, flash, jsonify, redirect, render_template,
                   request, session, url_for)

import commun
from ArrosageAUTO import MODES, jour_programme, lire_date, lire_entier, lire_heure, lire_reel

cfg = commun.charger_config()
log = commun.journal("web")
REGLAGES = cfg["arrosage"]
NB = int(REGLAGES["nb_zones"])
DUREE_MAX = int(REGLAGES["duree_max_zone_min"])

app = Flask(__name__)
app.secret_key = secrets.token_bytes(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict")

verrou = threading.Lock()
etat = {
    "config": {},                                  # arrosage/config/*
    "vannes": {i: None for i in range(1, NB + 1)},  # état réel (ESP32)
    "esp": None,
    "decision": "",
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
    import json
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
        elif topic == commun.TOPIC_METEO_WEB:
            try:
                etat["meteo_web"] = json.loads(texte)
            except ValueError:
                pass
        elif topic.startswith(commun.TOPIC_METEO):
            etat["station"][topic[len(commun.TOPIC_METEO):]] = texte


def publier(topic, valeur, retain=False):
    mqtt.publish(topic, str(valeur), qos=1, retain=retain)


def instantane():
    with verrou:
        return {
            "config": dict(etat["config"]),
            "vannes": dict(etat["vannes"]),
            "esp": etat["esp"],
            "decision": etat["decision"],
            "meteo_web": dict(etat["meteo_web"]),
            "station": dict(etat["station"]),
        }


# =============================================================================
# Sécurité : authentification + CSRF
# =============================================================================

@app.before_request
def controle_acces():
    attendu_user = cfg["web"].get("utilisateur", "admin")
    attendu_mdp = cfg["web"].get("mot_de_passe", "")
    if not attendu_mdp:
        return Response("Mot de passe web non configuré (config.json, section \"web\").", 503)
    auth = request.authorization
    if not auth or not (hmac.compare_digest(auth.username or "", attendu_user)
                        and hmac.compare_digest(auth.password or "", attendu_mdp)):
        return Response("Authentification requise", 401,
                        {"WWW-Authenticate": 'Basic realm="Arrosage", charset="UTF-8"'})
    if request.method == "POST":
        jeton = request.form.get("csrf", "")
        if not jeton or not hmac.compare_digest(jeton, session.get("csrf", "")):
            return Response("Jeton de sécurité invalide : rechargez la page.", 400)


def jeton_csrf():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


@app.after_request
def entetes(reponse):
    reponse.headers["X-Frame-Options"] = "DENY"
    reponse.headers["X-Content-Type-Options"] = "nosniff"
    reponse.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'")
    reponse.headers["Cache-Control"] = "no-store"
    return reponse


# =============================================================================
# Programme : validation et prochain arrosage
# =============================================================================

def valider_programme(form, nb_zones, duree_max, aujourd_hui):
    """Retourne (parametres_mqtt, erreurs, valeurs_saisies)."""
    erreurs = []
    v = {
        "duree": form.get("duree", "").strip(),
        "recurrence": form.get("recurrence", "").strip(),
        "dateDebut": form.get("dateDebut", "").strip(),
        "dateFin": form.get("dateFin", "").strip(),
    }
    duree = lire_entier(v["duree"])
    if duree is None or not 1 <= duree <= duree_max:
        erreurs.append(f"La durée par zone doit être comprise entre 1 et {duree_max} minutes.")
    recurrence = lire_entier(v["recurrence"])
    if recurrence is None or not 1 <= recurrence <= 365:
        erreurs.append("La récurrence doit être comprise entre 1 et 365 jours (1 = tous les jours).")
    debut, fin = lire_date(v["dateDebut"]), lire_date(v["dateFin"])
    if debut is None:
        erreurs.append("Indiquez une date de début.")
    if fin is None:
        erreurs.append("Indiquez une date de fin.")
    if debut and fin and fin < debut:
        erreurs.append("La date de fin doit être après la date de début.")
    if fin and fin < aujourd_hui:
        erreurs.append("La date de fin est déjà passée : le programme ne se déclencherait jamais.")

    creneaux = []
    for i in range(1, nb_zones + 1):
        active = bool(form.get(f"zone{i}"))
        heure_txt = form.get(f"heureDebut{i}", "").strip()
        v[f"zone{i}"], v[f"heureDebut{i}"] = active, heure_txt
        if not active:
            continue
        hm = lire_heure(heure_txt)
        if hm is None:
            erreurs.append(f"Zone {i} : indiquez une heure de début.")
            continue
        start = hm[0] * 60 + hm[1]
        if duree and start + duree > 24 * 60:
            erreurs.append(f"Zone {i} : l'arrosage doit se terminer avant minuit.")
        creneaux.append((start, i))
    if not any(v[f"zone{i}"] for i in range(1, nb_zones + 1)):
        erreurs.append("Cochez au moins une zone.")

    if duree:
        creneaux.sort()
        for (s1, z1), (s2, z2) in zip(creneaux, creneaux[1:]):
            if s2 < s1 + duree:
                erreurs.append(f"Les zones {z1} et {z2} se chevauchent : une seule vanne s'ouvre à la fois. "
                               f"Décalez la zone {z2} d'au moins {s1 + duree - s2} min.")

    params = {}
    if not erreurs:
        params = {
            "StrDuree": duree,
            "StrRecurrence": recurrence,
            "StrDateDebut": debut.isoformat(),
            "StrDateFin": fin.isoformat(),
        }
        for i in range(1, nb_zones + 1):
            params[f"StrZone{i}"] = "on" if v[f"zone{i}"] else "off"
            params[f"StrDebut{i}"] = v[f"heureDebut{i}"] if v[f"zone{i}"] else ""
    return params, erreurs, v


def valeurs_depuis_config(config):
    v = {
        "duree": config.get("StrDuree", ""),
        "recurrence": config.get("StrRecurrence", ""),
        "dateDebut": (lire_date(config.get("StrDateDebut")) or ""),
        "dateFin": (lire_date(config.get("StrDateFin")) or ""),
    }
    v["dateDebut"] = str(v["dateDebut"])
    v["dateFin"] = str(v["dateFin"])
    for i in range(1, NB + 1):
        v[f"zone{i}"] = str(config.get(f"StrZone{i}", "off")).lower() == "on"
        v[f"heureDebut{i}"] = config.get(f"StrDebut{i}", "") if v[f"zone{i}"] else ""
    return v


JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def prochain_arrosage(config, maintenant):
    """Texte du prochain créneau programmé, ou None."""
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
                    creneaux.append(f"zone {i} à {hm[0]:02d}:{hm[1]:02d}")
        if creneaux:
            quand = "aujourd'hui" if decalage == 0 else ("demain" if decalage == 1 else
                                                          f"{JOURS[jour.weekday()]} {jour:%d/%m}")
            return f"{quand} : " + ", ".join(sorted(creneaux, key=lambda c: c[-5:]))
    return None


def resume_meteo(s):
    """Valeurs météo utiles à l'écran AUTO + verdict par critère."""
    station = s["station"]
    web = s["meteo_web"]
    temp = lire_reel(station.get("temperature"))
    if temp is None:
        temp = lire_reel(web.get("temperature"))
    pluie_station = lire_reel(station.get("pluie"))
    pluie_passee_web = lire_reel(web.get("pluie_passee"))
    connues = [p for p in (pluie_station, pluie_passee_web) if p is not None]
    pluie_passee = max(connues) if connues else None
    pluie_prevue = lire_reel(web.get("pluie_prevue"))

    def critere(valeur, ok, texte):
        return {"valeur": texte.format(valeur) if valeur is not None else "inconnu",
                "ok": None if valeur is None else ok(valeur)}

    return [
        ("Pluie tombée récemment", f"moins de {REGLAGES['seuil_pluie_passee_mm']} mm",
         critere(pluie_passee, lambda x: x < REGLAGES["seuil_pluie_passee_mm"], "{:.1f} mm")),
        ("Pluie prévue (48 h)", f"moins de {REGLAGES['seuil_pluie_prevue_mm']} mm",
         critere(pluie_prevue, lambda x: x < REGLAGES["seuil_pluie_prevue_mm"], "{:.1f} mm")),
        ("Température", f"plus de {REGLAGES['temperature_min_c']} °C",
         critere(temp, lambda x: x > REGLAGES["temperature_min_c"], "{:.1f} °C")),
    ]


# =============================================================================
# Pages
# =============================================================================

def mode_actuel(s):
    m = s["config"].get("mode")
    return m if m in MODES else "MANU"


def page(valeurs=None, erreurs=None, code=200):
    s = instantane()
    maintenant = datetime.now()
    contexte = {
        "s": s,
        "mode": mode_actuel(s),
        "nb": NB,
        "reglages": REGLAGES,
        "csrf": jeton_csrf(),
        "valeurs": valeurs or valeurs_depuis_config(s["config"]),
        "erreurs": erreurs or [],
        "prochain": prochain_arrosage(s["config"], maintenant),
        "criteres": resume_meteo(s),
        "duree_zone": lire_entier(s["config"].get("StrDuree"), REGLAGES["duree_defaut_min"]),
        "duree_max": DUREE_MAX,
        "aujourdhui": date.today().isoformat(),
    }
    return render_template("index.html", **contexte), code


@app.get("/")
def accueil():
    return page()


@app.get("/dashboard")
@app.get("/accueil")
def anciennes_pages():
    return redirect(url_for("accueil"))


@app.get("/api/etat")
def api_etat():
    s = instantane()
    return jsonify({
        "mode": mode_actuel(s),
        "vannes": {str(k): v for k, v in s["vannes"].items()},
        "esp": s["esp"],
        "decision": s["decision"],
        "heure": datetime.now().strftime("%H:%M"),
    })


@app.post("/mode")
def changer_mode():
    mode = request.form.get("mode")
    if mode not in MODES:
        flash("Mode inconnu.", "erreur")
    else:
        publier(commun.TOPIC_CONFIG + "mode", mode, retain=True)
        flash(f"Mode {mode} activé. Les vannes ont été refermées.", "ok")
    return redirect(url_for("accueil"))


@app.post("/vanne/<int:i>")
def commander_vanne(i):
    s = instantane()
    voulu = request.form.get("etat")
    if i not in s["vannes"] or voulu not in ("0", "1"):
        flash("Commande invalide.", "erreur")
    elif voulu == "1" and mode_actuel(s) != "MANU":
        flash("Passez en mode MANU pour ouvrir une vanne à la main.", "erreur")
    elif voulu == "1" and not s["esp"]:
        flash("Le boîtier des vannes (ESP32) est hors ligne.", "erreur")
    else:
        publier(commun.topic_commande_vanne(i), voulu)
        flash(f"Vanne {i} : ordre {'d’ouverture' if voulu == '1' else 'de fermeture'} envoyé.", "ok")
    return redirect(url_for("accueil"))


@app.post("/arreter")
def tout_arreter():
    publier(commun.TOPIC_ACTION, "tout_arreter")
    for i in range(1, NB + 1):
        publier(commun.topic_commande_vanne(i), "0")
    flash("Toutes les vannes ont reçu l'ordre de fermeture.", "ok")
    return redirect(url_for("accueil"))


@app.post("/cycle")
def lancer_cycle():
    if mode_actuel(instantane()) != "AUTO":
        flash("Le lancement d'un cycle n'est possible qu'en mode AUTO.", "erreur")
    else:
        publier(commun.TOPIC_ACTION, "lancer_cycle")
        flash("Cycle lancé : les zones vont s'arroser l'une après l'autre.", "ok")
    return redirect(url_for("accueil"))


@app.post("/duree")
def changer_duree():
    duree = lire_entier(request.form.get("duree"))
    if duree is None or not 1 <= duree <= DUREE_MAX:
        flash(f"La durée doit être comprise entre 1 et {DUREE_MAX} minutes.", "erreur")
    else:
        publier(commun.TOPIC_CONFIG + "StrDuree", duree, retain=True)
        flash(f"Durée par zone : {duree} min.", "ok")
    return redirect(url_for("accueil"))


@app.post("/programme")
def enregistrer_programme():
    params, erreurs, valeurs = valider_programme(request.form, NB, DUREE_MAX, date.today())
    if erreurs:
        return page(valeurs=valeurs, erreurs=erreurs, code=400)
    for cle, val in params.items():
        publier(commun.TOPIC_CONFIG + cle, val, retain=True)
    log.info("Nouveau programme : %s", params)
    flash("Programme enregistré.", "ok")
    return redirect(url_for("accueil") + "#programme")


def main():
    global mqtt
    if not cfg["web"].get("mot_de_passe"):
        log.error("Aucun mot de passe web dans config.json : l'interface refusera les connexions.")
    mqtt = commun.creer_client_mqtt("arrosage-web", cfg, on_connect, on_message)
    hote, port = cfg["web"].get("hote", "0.0.0.0"), int(cfg["web"].get("port", 5000))
    try:
        from waitress import serve
        log.info("Interface web sur http://%s:%s (waitress)", hote, port)
        serve(app, host=hote, port=port, threads=4)
    except ImportError:
        log.warning("waitress absent : serveur de développement Flask utilisé")
        app.run(host=hote, port=port, threaded=True)


if __name__ == "__main__":
    main()
