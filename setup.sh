#!/bin/bash

Color_Off='\033[0m'       # Text Reset
BRed='\033[1;31m'         # Red
BGreen='\033[1;32m'       # Green
BBlue='\033[1;34m'        # Blue
BYellow='\033[1;33m'      # Yellow

# Fonction pour gérer les erreurs
handle_error() {
    echo -e "${BRed}[ERROR]${Color_Off} Une erreur est survenue lors de l'exécution du script."
    exit 1
}

# Mise à jour et upgrade du Raspberry Pi
echo -e "${BBlue}[INFO]${Color_Off} Updating Raspberry Pi"
sudo apt update && sudo apt upgrade -y || handle_error
echo -e "${BGreen}[DONE]${Color_Off} System up to date"

# Création des répertoires nécessaires
echo -e "${BBlue}[INFO]${Color_Off} Création des répertoires pour ArrosageAUTO"
mkdir -p /home/pi/Documents/ArrosageAUTO || handle_error

# Téléchargement des fichiers depuis GitHub
echo -e "${BBlue}[INFO]${Color_Off} Téléchargement du fichier ArrosageAUTO.py depuis GitHub..."
curl -f https://raw.githubusercontent.com/KyrianBunel/automatic-irrigation-system/main/Code/ArrosageAUTO.py -o /home/pi/Documents/ArrosageAUTO/ArrosageAUTO.py || handle_error
echo -e "${BBlue}[INFO]${Color_Off} Téléchargement du fichier ArrosageAUTO_SERVER.py depuis GitHub..."
curl -f https://raw.githubusercontent.com/KyrianBunel/automatic-irrigation-system/main/Code/ArrosageAUTO_SERVER.py -o /home/pi/Documents/ArrosageAUTO/ArrosageAUTO_SERVER.py || handle_error
echo -e "Téléchargement du fichier gestion_serie.py depuis GitHub..."
curl -f https://raw.githubusercontent.com/KyrianBunel/automatic-irrigation-system/main/Code/gestion_serie.py -o /home/pi/Documents/ArrosageAUTO/gestion_serie.py || handle_error
echo -e "${BGreen}[DONE]${Color_Off} Fichiers Python téléchargés"

# Création dynamique du script de démarrage start_arrosage.sh
echo -e "${BBlue}[INFO]${Color_Off} Création du script start_arrosage.sh..."
cat <<EOF > /home/pi/Documents/ArrosageAUTO/start_arrosage.sh
#!/bin/bash
/usr/bin/python3 /home/pi/Documents/ArrosageAUTO/gestion_serie.py &
/usr/bin/python3 /home/pi/Documents/ArrosageAUTO/ArrosageAUTO_SERVER.py &
/usr/bin/python3 /home/pi/Documents/ArrosageAUTO/ArrosageAUTO.py
EOF

# Donner les permissions d'exécution aux fichiers
echo "Modification des permissions des fichiers..."
chmod +x /home/pi/Documents/ArrosageAUTO/gestion_serie.py || handle_error
chmod +x /home/pi/Documents/ArrosageAUTO/ArrosageAUTO_SERVER.py || handle_error
chmod +x /home/pi/Documents/ArrosageAUTO/ArrosageAUTO.py || handle_error
chmod +x /home/pi/Documents/ArrosageAUTO/start_arrosage.sh || handle_error

# Installation de mosquitto et des dépendances Python
echo -e "${BBlue}[INFO]${Color_Off} Installation de mosquitto et des dépendances Python..."
sudo apt install -y mosquitto mosquitto-clients || handle_error
echo -e "${BBlue}[INFO]${Color_Off} Configuration de Mosquitto pour accès externe..."
sudo bash -c 'cat <<EOF > /etc/mosquitto/conf.d/external.conf
listener 1883
allow_anonymous true
EOF'
sudo systemctl restart mosquitto || handle_error
sudo systemctl enable mosquitto.service || handle_error

# Installation des paquets Python
sudo apt install python3 -y || handle_error
sudo apt install python3-pip -y || handle_error
sudo apt install python3-flask -y || handle_error
sudo apt install python3-serial -y || handle_error
sudo apt install python3-paho-mqtt -y || handle_error
sudo apt install python3-numpy -y || handle_error
sudo apt install python3-scipy -y || handle_error
sudo apt install python3-matplotlib -y || handle_error
sudo apt install python3-gpiozero -y || handle_error

# Création du fichier de service
echo -e "${BBlue}[INFO]${Color_Off} Création du fichier de service..."
sudo tee /etc/systemd/system/ArrosageAUTO.service > /dev/null <<'EOF'
[Unit]
Description=Démarrage des services de l'arrosage automatique
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

# Recharger et activer le service
sudo systemctl daemon-reload || handle_error
sudo systemctl enable ArrosageAUTO.service || handle_error

# Redémarrage du Raspberry Pi
echo -e "${BBlue}[INFO]${Color_Off} Le Raspberry Pi va redémarrer..."
sudo reboot now || handle_errorsudo apt install python3-flask -y || handle_error
#sudo apt install python3-pyserial || handle_error
sudo apt install python3-serial || handle_error
sudo apt install python3-paho-mqtt || handle_error
sudo apt install python3-numpy -y || handle_error
sudo apt install python3-scipy -y || handle_error
sudo apt install python3-matplotlib -y || handle_error
sudo apt install python3-gpiozero -y || handle_error
#sudo apt install python3-logging || handle_error

# Création du fichier de service pour l'arrosage automatique
echo -e "${BBlue}[INFO]${Color_Off} Création du fichier de service pour l'arrosage automatique..."
cat <<EOF > /etc/systemd/system/ArrosageAUTO.service
[Unit]
Description=Démarrage des services de l'arrosage automatique
After=network.target mosquitto.service

[Service]
Type=simple
# Starting process
ExecStart=/bin/bash /home/pi/Documents/ArrosageAUTO/start_arrosage.sh
WorkingDirectory=/home/pi/Documents/ArrosageAUTO
User=pi
Group=pi
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Recharger et activer le service
sudo systemctl daemon-reload || handle_error
sudo systemctl enable ArrosageAUTO.service || handle_error

# Redémarrage du Raspberry Pi
echo -e "${BBlue}[INFO]${Color_Off} Le Raspberry Pi va redémarrer..."
sudo reboot now || handle_error

# Vérifier que tout fonctionne avec htop (optionnel)
echo "Vérification des processus en cours..."
htop || handle_error
