# Modifications du 24/11/2026

Les fichiers d'origine sont dans `_sauvegarde_avant_modifs_2026-11-24/`. Le token Telegram et le mot de passe Wi-Fi en ont été retirés.

## À faire de ton côté (obligatoire)

1. **Révoquer le token du bot Telegram.** Envoie `/revoke` (ou `/deletebot`) à @BotFather : le token reste visible dans l'historique GitHub même si le fichier est supprimé.
2. **Purger l'historique GitHub.** Utilise `git filter-repo --path Code/Supervisor.py --invert-paths` puis `git push --force`. Tu peux aussi recréer le dépôt.
3. **Créer `CODE_ESP_CLIENT/secrets.h`.** Il est déjà créé en local avec ton Wi-Fi. Il reste à y mettre le mot de passe MQTT `esp32`, que `setup.sh` affiche dans `/etc/arrosage/identifiants_mqtt.txt`, puis à reflasher l'ESP32.
4. **Relancer `./setup.sh` sur le Raspberry Pi**, avec ton utilisateur habituel et sans sudo.
5. **Home Assistant** : dans l'intégration MQTT, utilise l'utilisateur `homeassistant` et son mot de passe.
6. **Vérifier le câblage des relais** : si le module colle quand la broche est à LOW, mets `RELAIS_ACTIF_BAS = true` dans le firmware.

## Ce qui a changé

### Supprimé
- `Code/Supervisor.py` (bot Telegram).

### Sécurité
- Secrets sortis du code. Côté Raspberry Pi : `/etc/arrosage/config.json`. Côté ESP32 : `secrets.h`. Les deux sont ignorés par git (`.gitignore`).
- Mosquitto : accès anonyme interdit, un compte par appareil (`arrosage`, `esp32`, `homeassistant`).
- Interface web : identifiant et mot de passe, actions en POST uniquement avec jeton anti-CSRF, en-têtes de sécurité, aucune ressource externe, serveur `waitress` à la place du serveur de développement Flask.
- `setup.sh` installe depuis le dossier cloné, et non plus en téléchargeant la branche `main` à chaque fois.
- Récepteur LoRa : correction d'un débordement de tampon (trame de 90 caractères pour un tampon de 80).

### Sécurité de l'eau
- ESP32 : coupure automatique d'une vanne ouverte depuis plus de 125 min, même si le Raspberry Pi a planté.
- Commandes de vannes sur un nouveau topic `arrosage/cmd/vanneN`, **jamais retenu**. Les anciens ordres retenus sous `arrosage/config/vanneN` sont effacés au démarrage.
- L'ESP32 publie l'état réel (`arrosage/status/vanneN`) et sa présence (`arrosage/status/esp` : online/offline, via un message LWT).
- Vannes fermées dès que le Wi-Fi ou le MQTT tombe. La reconnexion ne bloque plus la surveillance.
- Mode MANU : fermeture automatique après 60 min (`duree_max_manu_min`).
- En cas d'erreur dans la logique, toutes les vannes sont fermées.
- Modes automatiques : une seule vanne ouverte à la fois.
- Si l'heure n'est pas synchronisée (NTP), aucun arrosage automatique ne démarre.

### Bugs corrigés
- systemd : un service par script (`arrosage-meteo`, `arrosage-logique`, `arrosage-web`), lancés après Mosquitto, avec `Restart=always`. Avant, la logique d'arrosage ne démarrait jamais.
- Mode AUTO : abonnement à la station météo, mise à jour Open-Meteo toutes les 30 min, une seule décision par jour.
- Mode PROG : suppression de la condition `pluie == "1"` qui bloquait tout, et prise en compte de la date de fin. Le programme est suspendu s'il a plu (réglable).
- Home Assistant : état réel des vannes, disponibilité de l'ESP32, boutons « Lancer un cycle » et « Tout arrêter », capteur « Dernière décision ».
- `gestion_serie.py` : plus de numpy/scipy/matplotlib, logs dans journald (rotation automatique), horodatage des mesures.

### Ergonomie (interface web)
- Une seule page, qui affiche l'état réel des vannes dans tous les modes et se rafraîchit toutes les 3 s.
- Bouton « Tout arrêter » toujours visible.
- AUTO : les conditions (pluie, température) et leur valeur actuelle s'affichent avec ✓ ou ✗. Dernière décision expliquée, durée par zone modifiable, bouton « Lancer un cycle maintenant ».
- PROG : formulaire prérempli avec le programme en cours, « Prochain arrosage » affiché, vérifications côté serveur (dates, durées, heure obligatoire, zones qui se chevauchent) avec des messages clairs.

## Web app iPhone (refonte de l'interface)

- **Installer** : dans Safari sur l'iPhone, ouvre `http://<IP du Pi>:5000`, connecte-toi, puis **Partager → Sur l'écran d'accueil**. L'app s'ouvre en plein écran avec son icône.
- **Connexion** : identifiant `admin` et mot de passe dans `/etc/arrosage/identifiants_mqtt.txt`. La session est mémorisée 30 jours. Après 5 essais ratés, la connexion est bloquée 5 minutes.
- **En haut de l'écran**, une phrase dit ce qui se passe (« La zone 2 arrose. Encore 8 min. », « Rien n'arrose. Prochain arrosage demain à 06:00. »), avec une barre d'eau qui se remplit et un bouton « Tout arrêter » quand une zone arrose.
- **Modes** : Manuel, Météo (ancien AUTO), Programme (ancien PROG). Les zones s'ouvrent et se ferment avec des interrupteurs.
- **Météo** : les trois conditions s'affichent avec leur valeur du moment (✓ ou ✗), et la durée par zone se règle avec − et +.
- **Programme** : formulaire prérempli, enregistré sans recharger la page, erreurs expliquées en clair.
- **Mode sombre** automatique, aucune ressource externe : l'app fonctionne sans internet, sur le Wi-Fi de la maison.
- **Hors de chez toi** : passe par un VPN (Tailscale ou WireGuard). N'ouvre pas le port 5000 sur ta box.
- **Technique** : la page appelle `/api/etat` toutes les 3 s, et les commandes passent en JSON avec un jeton anti-CSRF. La logique publie la zone en cours et son heure de fin sur `arrosage/info/en_cours`.
- **Si `config.json` existe déjà** (installation antérieure), ajoute `"cle_secrete"` dans la section `web`, sinon les sessions dépendent du mot de passe.

## Changements de comportement à connaître
- La pluie « prévue » couvre aujourd'hui et demain. Avant, elle couvrait demain et après-demain.
- Si les données météo manquent (station muette et Open-Meteo injoignable), le mode AUTO **n'arrose pas** et l'indique.
- En mode AUTO ou PROG, une vanne ouverte depuis Home Assistant est refermée par l'automatisme. Il faut passer en MANU.
- Les topics de batterie de la station deviennent `batterie_tension` et `batterie_pourcent`. Les identifiants HA restent les mêmes.

## Réglages (`/etc/arrosage/config.json`, section `arrosage`)
| Clé | Défaut | Rôle |
|---|---|---|
| `heure_auto` | `05:00` | heure de décision du mode AUTO |
| `duree_max_zone_min` | 120 | durée maximale d'une zone |
| `duree_max_manu_min` | 60 | fermeture automatique en MANU |
| `seuil_pluie_passee_mm` | 5 | pluie récente au-delà de laquelle on n'arrose pas |
| `seuil_pluie_prevue_mm` | 2 | pluie prévue au-delà de laquelle on n'arrose pas |
| `temperature_min_c` | 12 | température minimale pour arroser en AUTO |
| `prog_suspendre_si_pluie` | true | le mode PROG respecte aussi le seuil de pluie |
