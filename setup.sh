#!/usr/bin/env bash
# Installation de l'arrosage automatique sur un Raspberry Pi.
#
# Usage (avec votre utilisateur habituel, PAS avec sudo) :
#   git clone https://github.com/KyrianBunel/automatic-irrigation-system.git
#   cd automatic-irrigation-system && ./setup.sh
#
# Options (variables d'environnement) :
#   LATITUDE=45.0 LONGITUDE=-0.4   position du jardin (sinon demandée)
#   INSTALL_DIR=...                dossier d'installation (défaut : ~/Documents/ArrosageAUTO)
#   INSTALL_NODERED=1              installe aussi Node-RED (facultatif)
#
# Le script peut être relancé : la configuration et les mots de passe existants sont conservés.

set -Eeuo pipefail

Off='\033[0m'; Rouge='\033[1;31m'; Vert='\033[1;32m'; Bleu='\033[1;34m'; Jaune='\033[1;33m'
info() { echo -e "${Bleu}[INFO]${Off} $*"; }
ok()   { echo -e "${Vert}[OK]${Off} $*"; }
warn() { echo -e "${Jaune}[ATTENTION]${Off} $*"; }
trap 'echo -e "${Rouge}[ERREUR]${Off} ligne $LINENO : $BASH_COMMAND"; exit 1' ERR

if [[ $EUID -eq 0 ]]; then
    echo "Lancez ce script avec votre utilisateur normal (sans sudo) : il demandera sudo au besoin."
    exit 1
fi

UTILISATEUR="$(id -un)"
GROUPE="$(id -gn)"
SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/Code"
INSTALL_DIR="${INSTALL_DIR:-$HOME/Documents/ArrosageAUTO}"
CONF_DIR=/etc/arrosage
CONF="$CONF_DIR/config.json"
IDENT="$CONF_DIR/identifiants_mqtt.txt"

[[ -f "$SOURCE/ArrosageAUTO.py" ]] || { echo "Dossier Code/ introuvable à côté de setup.sh"; exit 1; }

# --- Système et paquets -----------------------------------------------------------
info "Mise à jour du système"
sudo apt-get update
sudo apt-get upgrade -y

info "Installation des paquets"
sudo apt-get install -y mosquitto mosquitto-clients python3 python3-flask python3-serial \
    python3-paho-mqtt python3-requests python3-waitress

info "Activation de la synchronisation de l'heure (NTP)"
sudo timedatectl set-ntp true || warn "impossible d'activer NTP : vérifiez l'heure du Raspberry Pi"

# --- Fichiers -----------------------------------------------------------------------
info "Copie des fichiers dans $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
cp "$SOURCE"/*.py "$INSTALL_DIR/"
cp -r "$SOURCE/templates" "$SOURCE/static" "$INSTALL_DIR/"
rm -f "$INSTALL_DIR/Supervisor.py"   # ancien bot Telegram, supprimé
ok "Fichiers copiés"

# --- Configuration et mots de passe ---------------------------------------------------
gen_mdp() { python3 -c 'import secrets; print(secrets.token_urlsafe(18))'; }

sudo mkdir -p "$CONF_DIR"
if sudo test -f "$CONF"; then
    ok "Configuration existante conservée ($CONF)"
    NOUVELLE_CONF=0
else
    info "Création de la configuration"
    LAT="${LATITUDE:-}"; LON="${LONGITUDE:-}"
    if [[ -z "$LAT" ]]; then read -rp "Latitude du jardin (ex : 45.12 ; vide = pas de prévisions météo) : " LAT; fi
    if [[ -n "$LAT" && -z "$LON" ]]; then read -rp "Longitude du jardin : " LON; fi

    export MDP_PI="$(gen_mdp)" MDP_ESP="$(gen_mdp)" MDP_HA="$(gen_mdp)" MDP_WEB="$(gen_mdp)"
    export LAT LON
    TMP="$(mktemp)"
    python3 - "$SOURCE/config.example.json" > "$TMP" <<'EOF'
import json, os, sys
c = json.load(open(sys.argv[1], encoding="utf-8"))
def reel(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None
c["mqtt"]["mot_de_passe"] = os.environ["MDP_PI"]
c["web"]["mot_de_passe"] = os.environ["MDP_WEB"]
import secrets
c["web"]["cle_secrete"] = secrets.token_hex(32)   # garde les sessions de la web app après un redémarrage
c["position"] = {"latitude": reel(os.environ.get("LAT")), "longitude": reel(os.environ.get("LON"))}
print(json.dumps(c, indent=2, ensure_ascii=False))
EOF
    sudo install -m 640 -o root -g "$GROUPE" "$TMP" "$CONF"
    rm -f "$TMP"

    TMP="$(mktemp)"
    cat > "$TMP" <<EOF
Identifiants générés le $(date '+%d/%m/%Y %H:%M') - à garder secret

Broker MQTT : $(hostname -I | awk '{print $1}'):1883
  Scripts du Raspberry Pi : arrosage / $MDP_PI
  ESP32 (secrets.h)       : esp32 / $MDP_ESP
  Home Assistant          : homeassistant / $MDP_HA

Interface web : http://$(hostname -I | awk '{print $1}'):5000
  identifiant : admin
  mot de passe : $MDP_WEB
EOF
    sudo install -m 600 -o "$UTILISATEUR" -g "$GROUPE" "$TMP" "$IDENT"
    rm -f "$TMP"

    info "Comptes Mosquitto"
    sudo rm -f /etc/mosquitto/passwd
    sudo touch /etc/mosquitto/passwd
    sudo mosquitto_passwd -b /etc/mosquitto/passwd arrosage "$MDP_PI"
    sudo mosquitto_passwd -b /etc/mosquitto/passwd esp32 "$MDP_ESP"
    sudo mosquitto_passwd -b /etc/mosquitto/passwd homeassistant "$MDP_HA"
    sudo chown root:mosquitto /etc/mosquitto/passwd
    sudo chmod 640 /etc/mosquitto/passwd
    NOUVELLE_CONF=1
fi

# --- Mosquitto : authentification obligatoire -------------------------------------------
info "Configuration de Mosquitto (accès anonyme interdit)"
sudo rm -f /etc/mosquitto/conf.d/external.conf   # ancienne config : allow_anonymous true
sudo tee /etc/mosquitto/conf.d/arrosage.conf > /dev/null <<EOF
listener 1883
allow_anonymous false
password_file /etc/mosquitto/passwd
EOF
sudo systemctl enable mosquitto.service
sudo systemctl restart mosquitto.service
ok "Mosquitto protégé par mot de passe"

# --- Services systemd : un par script ---------------------------------------------------
info "Création des services systemd"
for ancien in ArrosageAUTO Supervisor; do   # anciens services (Supervisor = bot Telegram)
    if [[ -f "/etc/systemd/system/$ancien.service" ]]; then
        sudo systemctl disable --now "$ancien.service" || true
        sudo rm -f "/etc/systemd/system/$ancien.service"
        ok "Ancien service $ancien.service supprimé"
    fi
done
rm -f "$INSTALL_DIR/start_arrosage.sh"

creer_service() {  # nom, description, script, lignes supplémentaires
    sudo tee "/etc/systemd/system/arrosage-$1.service" > /dev/null <<EOF
[Unit]
Description=Arrosage automatique - $2
After=network-online.target mosquitto.service
Wants=network-online.target mosquitto.service

[Service]
Type=simple
User=$UTILISATEUR
Group=$GROUPE
$4
WorkingDirectory=$INSTALL_DIR
Environment=ARROSAGE_CONFIG=$CONF
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/bin/python3 $INSTALL_DIR/$3
Restart=always
RestartSec=5
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF
}

creer_service meteo  "passerelle station météo"  gestion_serie.py        "SupplementaryGroups=dialout"
creer_service logique "logique d'arrosage"       ArrosageAUTO.py         ""
creer_service web    "interface web"             ArrosageAUTO_SERVER.py  ""

sudo systemctl daemon-reload
for s in meteo logique web; do
    sudo systemctl enable "arrosage-$s.service"
    sudo systemctl restart "arrosage-$s.service"
done
ok "Services arrosage-meteo, arrosage-logique et arrosage-web démarrés"

# --- Node-RED (facultatif) --------------------------------------------------------------
if [[ "${INSTALL_NODERED:-0}" == "1" ]]; then
    info "Installation de Node-RED"
    bash <(curl -fsSL https://raw.githubusercontent.com/node-red/linux-installers/master/deb/update-nodejs-and-nodered) --confirm-install --confirm-pi
    sudo systemctl enable --now nodered.service
fi

# --- Résumé ---------------------------------------------------------------------------
echo
ok "Installation terminée."
echo "  État des services : systemctl status 'arrosage-*'"
echo "  Journaux          : journalctl -u arrosage-logique -f"
echo "  Identifiants      : $IDENT"
if [[ "$NOUVELLE_CONF" == "1" ]]; then
    echo
    warn "À faire maintenant :"
    echo "  1. Copier le mot de passe 'esp32' dans CODE_ESP_CLIENT/secrets.h puis reflasher l'ESP32."
    echo "  2. Dans Home Assistant, intégration MQTT : utilisateur 'homeassistant' et son mot de passe."
    echo "  3. Ouvrir l'interface web avec l'identifiant 'admin' (mot de passe dans $IDENT)."
fi
