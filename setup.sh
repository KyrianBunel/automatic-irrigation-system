#!/bin/bash

Color_Off='\033[0m'       # Text Reset
BRed='\033[1;31m'         # Red
BGreen='\033[1;32m'       # Green
BBlue='\033[1;34m'        # Blue
BYellow='\033[1;33m'      # Yellow

# Mise à jour et upgrade du Raspberry Pi
echo -e "${BBlue}[INFO]${Color_Off} Updating Raspberry Pi"
sudo apt update && sudo apt upgrade -y
echo -e "${BGreen}[DONE]${Color_Off} System up to date"

# Installation de Node-RED
echo -e "${BBlue}[INFO]${Color_Off} Installing Node-RED"
bash <(curl -sL https://raw.githubusercontent.com/node-red/linux-installers/master/deb/update-nodejs-and-nodered)
sudo systemctl enable nodered.service
cd ~/.node-red
npm install node-red-dashboard
echo -e "${BGreen}[DONE]${Color_Off} Node-RED Installed"

# Création des répertoires nécessaires
echo -e "${BBlue}[INFO]${Color_Off} Création des répertoires pour ArrosageAUTO"
mkdir -p /home/pi/Documents/ArrosageAUTO

# Téléchargement des fichiers depuis GitHub
echo -e "${BBlue}[INFO]${Color_Off} Téléchargement du fichier ArrosageAUTO.py depuis GitHub..."
curl -L https://raw.githubusercontent.com/KyrianBunel/automatic-irrigation-system/blob/main/Code/ArrosageAUTO.py -o /home/pi/Documents/ArrosageAUTO/ArrosageAUTO.py
echo -e "${BBlue}[INFO]${Color_Off} Téléchargement du fichier ArrosageAUTO_SERVER.py depuis GitHub..."
curl -L https://raw.githubusercontent.com/KyrianBunel/automatic-irrigation-system/blob/main/Code/ArrosageAUTO_SERVER.py -o /home/pi/Documents/ArrosageAUTO/ArrosageAUTO_SERVER.py
echo -e "Téléchargement du fichier gestion_serie.py depuis GitHub..."
curl -L https://raw.githubusercontent.com/KyrianBunel/automatic-irrigation-system/blob/main/Code/gestion_serie.py -o /home/pi/Documents/ArrosageAUTO/gestion_serie.py
echo -e "${BBlue}[INFO]${Color_Off} Téléchargement du fichier data.csv depuis GitHub..."
curl -L https://raw.githubusercontent.com/KyrianBunel/automatic-irrigation-system/blob/main/Code/data.csv -o /home/pi/Documents/ArrosageAUTO/data.csv
echo -e "${BBlue}[INFO]${Color_Off} Téléchargement du fichier flows.json depuis GitHub..."
curl -L https://raw.githubusercontent.com/KyrianBunel/automatic-irrigation-system/blob/main/Code/flows.json -o /home/pi/Documents/ArrosageAUTO/flows.json
echo -e "${BGreen}[DONE]${Color_Off} Fichiers téléchargés"

# Importation du fichier NodeRED
cd ~/.node-red
cp /home/pi/Documents/ArrosageAUTO/flows.json flows_$(hostname).json

# Donner les permissions d'exécution aux fichiers Python
echo "Modification des permissions des fichiers Python..."
chmod +x /home/pi/Documents/ArrosageAUTO/gestion_serie.py
chmod +x /home/pi/Documents/ArrosageAUTO/ArrosageAUTO_SERVER.py
chmod +x /home/pi/Documents/ArrosageAUTO/ArrosageAUTO.py

# Installation de mosquitto et des dépendances Python
echo -e "${BBlue}[INFO]${Color_Off} Installation de mosquitto et des dépendances Python..."
sudo apt install -y mosquitto mosquitto-clients
sudo systemctl enable mosquitto.service
sudo apt install python3
sudo apt install python3-pip -y
sudo apt install python3-flask -y
sudo apt install python3-pyserial
sudo apt install python3-serial
sudo apt install python3-paho-mqtt
sudo apt install python3-numpy -y
sudo apt install python3-scipy -y
sudo apt install python3-matplotlib -y
sudo apt install python3-logging

# Création du fichier de service pour l'arrosage automatique
echo -e "${BBlue}[INFO]${Color_Off} Création du fichier de service pour l'arrosage automatique..."
cat <<EOF > /etc/systemd/system/ArrosageAUTO.service
[Unit]
Description=Démarrage des services de l'arrosage automatique
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /home/pi/Documents/ArrosageAUTO/gestion_serie.py
ExecStartPost=/usr/bin/python3 /home/pi/Documents/ArrosageAUTO/ArrosageAUTO_SERVER.py
ExecStartPost=/usr/bin/python3 /home/pi/Documents/ArrosageAUTO/ArrosageAUTO.py
WorkingDirectory=/home/pi
User=pi
Group=pi
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

# Recharger et activer le service
sudo systemctl daemon-reload
sudo systemctl enable ArrosageAUTO.service

# Redémarrage du Raspberry Pi
echo -e "${BBlue}[INFO]${Color_Off} Le Raspberry Pi va redémarrer..."
sudo reboot now

# Vérifier que tout fonctionne avec htop (optionnel)
echo "Vérification des processus en cours..."
htop
