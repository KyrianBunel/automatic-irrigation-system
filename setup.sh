#!/bin/bash

# --- COULEURS ET GESTION ERREURS ---
Color_Off='\033[0m'
BRed='\033[1;31m'
BGreen='\033[1;32m'
BBlue='\033[1;34m'

handle_error() {
    echo -e "${BRed}[ERROR]${Color_Off} Une erreur est survenue. Arrêt du script."
    exit 1
}

# --- 1. MISE À JOUR SYSTÈME ---
echo -e "${BBlue}[INFO]${Color_Off} Mise à jour du Raspberry Pi..."
sudo apt update && sudo apt upgrade -y || handle_error

# --- 2. RÉPERTOIRES ET TÉLÉCHARGEMENTS ---
echo -e "${BBlue}[INFO]${Color_Off} Création du répertoire ArrosageAUTO..."
mkdir -p /home/pi/Documents/ArrosageAUTO || handle_error

echo -e "${BBlue}[INFO]${Color_Off} Téléchargement des fichiers depuis GitHub..."
URL_BASE="https://raw.githubusercontent.com/KyrianBunel/automatic-irrigation-system/main/Code"
curl -f ${URL_BASE}/ArrosageAUTO.py -o /home/pi/Documents/ArrosageAUTO/ArrosageAUTO.py || handle_error
curl -f ${URL_BASE}/Supervisor.py -o /home/pi/Documents/ArrosageAUTO/Supervisor.py || handle_error
curl -f ${URL_BASE}/ArrosageAUTO_SERVER.py -o /home/pi/Documents/ArrosageAUTO/ArrosageAUTO_SERVER.py || handle_error
curl -f ${URL_BASE}/gestion_serie.py -o /home/pi/Documents/ArrosageAUTO/gestion_serie.py || handle_error

# --- 3. SCRIPTS ET PERMISSIONS ---
echo -e "${BBlue}[INFO]${Color_Off} Création du script de lancement groupé..."
cat <<EOF > /home/pi/Documents/ArrosageAUTO/start_arrosage.sh
#!/bin/bash
/usr/bin/python3 /home/pi/Documents/ArrosageAUTO/gestion_serie.py &
/usr/bin/python3 /home/pi/Documents/ArrosageAUTO/ArrosageAUTO_SERVER.py &
/usr/bin/python3 /home/pi/Documents/ArrosageAUTO/ArrosageAUTO.py
EOF

chmod +x /home/pi/Documents/ArrosageAUTO/*.py
chmod +x /home/pi/Documents/ArrosageAUTO/start_arrosage.sh

# --- 4. INSTALLATION DÉPENDANCES (MQTT + PYTHON) ---
echo -e "${BBlue}[INFO]${Color_Off} Installation des paquets nécessaires..."
sudo apt install -y mosquitto mosquitto-clients python3 python3-pip python3-flask \
python3-serial python3-paho-mqtt python3-numpy python3-scipy \
python3-matplotlib python3-gpiozero python3-requests || handle_error

# Configuration Mosquitto
sudo bash -c 'cat <<EOF > /etc/mosquitto/conf.d/external.conf
listener 1883
allow_anonymous true
EOF'
sudo systemctl restart mosquitto
sudo systemctl enable mosquitto.service

# --- 5. CRÉATION DES SERVICES SYSTEMD ---

# Service principal (Arrosage)
echo -e "${BBlue}[INFO]${Color_Off} Configuration du service ArrosageAUTO..."
sudo tee /etc/systemd/system/ArrosageAUTO.service > /dev/null <<EOF
[Unit]
Description=Service Arrosage Automatique
After=network.target mosquitto.service

[Service]
Type=simple
ExecStart=/bin/bash /home/pi/Documents/ArrosageAUTO/start_arrosage.sh
WorkingDirectory=/home/pi/Documents/ArrosageAUTO
User=pi
Group=pi
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Service secondaire (Telegram / Supervisor)
echo -e "${BBlue}[INFO]${Color_Off} Configuration du service Supervisor (Telegram)..."
sudo tee /etc/systemd/system/Supervisor.service > /dev/null <<EOF
[Unit]
Description=Service de surveillance Telegram
After=network.target mosquitto.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 /home/pi/Documents/ArrosageAUTO/Supervisor.py
WorkingDirectory=/home/pi/Documents/ArrosageAUTO
User=pi
Group=pi
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# --- 6. ACTIVATION ET FINALISATION ---
echo -e "${BBlue}[INFO]${Color_Off} Activation des services..."
sudo systemctl daemon-reload
sudo systemctl enable ArrosageAUTO.service
sudo systemctl enable Supervisor.service

echo -e "${BGreen}[DONE]${Color_Off} Installation terminée avec succès."
echo -e "${BYellow}[REBOOT]${Color_Off} Le Raspberry Pi va redémarrer dans 5 secondes..."
sleep 5
sudo reboot now