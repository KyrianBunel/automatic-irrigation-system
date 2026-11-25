# automatic-irrigation-system
open-source automatic irrigation system based on raspberryPi

# Features :
- Connect to local network over Ethernet
- Compatible with a weather station included in the project to collect temperature, humidity, pressure, brightness and also features a rain sensor
- Controllable through a password-protected web app (LOCAL_IP_ADDRESS:5000 ex : 192.168.1.10:5000) and Home Assistant (MQTT auto-discovery)
    - On iPhone: open it in Safari, then Share → Add to Home Screen to use it full screen like an app (login remembered for 30 days, dark mode, works without internet)
    - 3 operating modes :
  
          - MANU -> allows manual control of the 3 valves independently; a valve left open is closed automatically after 60 min.
          - AUTO -> every day at 05:00, uses the weather station and Open-Meteo forecasts to decide whether to water; zones are watered one after the other.
          - PROG -> allows the user to enter information such as watering start and end date, watering duration, recurrence and watering time for each valve via a form.
- Real valve state, last decision and weather values shown on the home page, refreshed every 3 s
- Safety: the ESP32 closes any valve open for more than 125 min, and closes everything if the connection is lost
- Automatic sprinkler stop in case of rain (except in MANU mode)
- Transmits sensor data every 30min to a MQTT server host by the RaspberryPI to create a database and display data with NodeRED

# Future improvements :
- Web pages :
    - Add a settings page
    - Add the possibility of choosing the language (French only for the moment)
    - Add the possibility to modify the number of valve used
    - Dashboard page not fully working for now
- Database 
    - Improve the data sent as the total duration of watering during the last hour to be able to deduct the cost of watering per month and per year
- Add Mosquitto Mqtt server
- Display datas with Graphana
# How to start up :
### Home page & Dashboard
- Open RaspberryPI imager and plug your micro sd card into your computer
- select the raspberryPI you are using and go Operating System -> Raspberry PI OS (other) and select Raspberry Pi OS Lite (64-bit)
- Press Ctrl + shift + X and enable SSH
- Press Next to flash the sd card
- Connect an Ethernet cable and the power supply to the Raspberry Pi
- Wait about a minute for the Raspberry Pi to boot up, then use software like Advanced IP Scanner to find the Raspberry Pi's IP address
- connect to the Raspberry Pi with SSH and enter the folowing commands to donwload the setup file and execute it

        sudo apt install -y git
        git clone https://github.com/KyrianBunel/automatic-irrigation-system.git
        cd automatic-irrigation-system
        ./setup.sh

- Run it as your normal user (not with sudo). The script generates the MQTT and web passwords in `/etc/arrosage/identifiants_mqtt.txt`.
- ESP32: copy `CODE_ESP_CLIENT/secrets.example.h` to `secrets.h`, fill in your Wi-Fi and the `esp32` MQTT password, then flash the board.
- See `MODIFICATIONS.md` (French) for the full list of changes and settings.

# Additional material required :
If you whant the full experience you will need extra parts :
  - Heltec CubeCell HTCC-AB01 Dev board
  - [3D printed LoRa weather station](https://github.com/KyrianBunel/3D-printed-LoRa-weather-station)

# Web pages :
### Home page & Dashboard
<img width="600" alt="Capture d’écran 2023-11-24 à 09 25 02" src="https://github.com/KyrianBunel/Automatic-Watering-System/assets/136705314/ae5d1ec4-e019-4077-bf2f-7e15ebe8740a">

### NodeRED dashboard

# Weather station :
<img width="575" alt="Capture d’écran 2024-05-02 à 09 52 37" src="https://github.com/KyrianBunel/Automatic-Watering-System/assets/136705314/31bd3141-2804-4d15-b55d-4a1a0c62ad59"><img width="575" alt="Capture d’écran 2024-05-02 à 09 52 37" src="https://github.com/KyrianBunel/Automatic-Watering-System/assets/136705314/a941a943-170a-44f0-a0c6-2e01a71dcc4b">


