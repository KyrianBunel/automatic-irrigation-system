# automatic-irrigation-system
open-source automatic irrigation system based on raspberryPi

# Features :
- Connect to local network over Ethernet
- Compatible with a weather station included in the project to collect temperature, humidity, pressure, brightness and also features a rain sensor
- Controllable through a web page (LOCAL_IP_ADDRESS/accueil ex : 192.168.1.10/accueil)
    - 3 operating modes :
  
          - MANU -> allows manual control of the 6 valves independently; once the selected valve is active, it can be deactivated only if the user does it manually.
          - AUTO -> uses weather station and soil moisture sensors to automatically trigger a 15-minute watering cycle.
          - PROG -> allows the user to enter information such as watering start and end date, watering duration, recurrence and watering time for each valve via a form.
- Ability to view the current program and sensors values via a dashboard page (LOCAL_IP_ADDRESS/dashboard ex : 192.168.1.10/dashboard)
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

# How to start up :
### Home page & Dashboard
- Open RaspberryPI imager and plug your micro sd card into your computer
- select the raspberryPI you are using and go Operating System -> Raspberry PI OS (other) and select Raspberry Pi OS Lite (64-bit)
- Press Ctrl + shift + X and enable SSH
- Press Next to flash the sd card
- Connect an Ethernet cable and the power supply to the Raspberry Pi
- Wait about a minute for the Raspberry Pi to boot up, then use software like Advanced IP Scanner to find the Raspberry Pi's IP address
- connect to the Raspberry Pi with SSH and enter the folowing commands to donwload the setup file and execute it

        curl -L https://raw.githubusercontent.com/KyrianBunel/automatic-irrigation-system/blob/main/setup.sh

        chmod +x setup.sh

        sudo ./setup.sh

# Additional material required :
If you whant the full experience you will need extra parts :
  - Heltec CubeCell HTCC-AB01 Dev board
  - [3D printed LoRa weather station](https://github.com/KyrianBunel/3D-printed-LoRa-weather-station)

# Web pages :
### Home page & Dashboard
<img width="600" alt="Capture d’écran 2023-11-24 à 09 25 02" src="https://github.com/KyrianBunel/Automatic-Watering-System/assets/136705314/ae5d1ec4-e019-4077-bf2f-7e15ebe8740a">

# Weather station :
<img width="575" alt="Capture d’écran 2024-05-02 à 09 52 37" src="https://github.com/KyrianBunel/Automatic-Watering-System/assets/136705314/31bd3141-2804-4d15-b55d-4a1a0c62ad59"><img width="575" alt="Capture d’écran 2024-05-02 à 09 52 37" src="https://github.com/KyrianBunel/Automatic-Watering-System/assets/136705314/a941a943-170a-44f0-a0c6-2e01a71dcc4b">


