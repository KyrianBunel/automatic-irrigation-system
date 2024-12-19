import socket
import time
from datetime import datetime
import csv

#####------------------------------------- Serveur TCP -------------------------------------#####

HOST = '0.0.0.0'  # Écouter sur toutes les interfaces réseau
PORT = 12345      # Port d'écoute

# Création du socket TCP
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind((HOST, PORT))
server_socket.listen(1)
print(f"Serveur TCP en écoute sur le port '{PORT}', en attente d'un client")



#####------------------------------------- Variables globales -------------------------------------#####

# Chemin du fichier CSV
filename = '/home/pi/Documents/ArrosageAUTO/data.csv'

# Initialisation des variables
StrDuree = None
StrDateDebut = None
StrDateFin = None
recurrence = 0
StrZone1 = None
StrZone2 = None
StrZone3 = None
StrDebut1 = None
StrDebut2 = None
StrDebut3 = None
bpVanne1 = ''
bpVanne2 = ''
bpVanne3 = ''
mode = None

# Variablers mode AUTO
SeuilHumidite = 10 #humididé dans le sol
SeuilTemperatureMAX = 25.00
SeuilTemperatureMIN = 15.00
SeuilHumidity = 40.00 #humidité dans l'air
JourArrosage = 0 #dernier jour d'arrosage en mode auto
delayAUTO = 600000 # duréé de l'arrosage en mode AUTO (en ms)
TimerAUTO = 0

# capteurs
MoistureSensor1 = 0
MoistureSensor3 = 0
MoistureSensor2 = 0
temperature = 25
pluie = 1

# Etat des vannes (ON/OFF)
Vanne1 = '0'
Vanne2 = '0'
Vanne3 = '0'

def update_time():
    global current_dateTime, current_hour, current_min, current_sec, current_day, current_month, current_year
    current_dateTime = datetime.now()
    current_hour = int(current_dateTime.hour)
    if current_hour == 23:
        current_hour = 0
    else:
        current_hour = int(current_dateTime.hour)+1
    current_min = int(current_dateTime.minute)
    current_sec = int(current_dateTime.second)
    if current_hour != 0:
        current_day = int(current_dateTime.day)
    else:
        current_day = int(current_dateTime.day)+1
    current_month = int(current_dateTime.month)
    current_year = int(current_dateTime.year)
    return 0

def allumer_vanne(num_vanne):
    global Vanne1, Vanne2, Vanne3
    if Vanne1 == '0' and num_vanne == 1:
        print(f"Vanne1 :ON    {datetime.now()}")
        Vanne1 = '1'
        send_data(Vanne1, Vanne2, Vanne3)
    if Vanne2 == '0' and num_vanne == 2:
        print(f"Vanne2 :ON    {datetime.now()}")
        Vanne2 = '1'
        send_data(Vanne1, Vanne2, Vanne3)
    if Vanne3 == '0' and num_vanne == 3:
        print(f"Vanne3 :ON    {datetime.now()}")
        Vanne3 = '1'
        send_data(Vanne1, Vanne2, Vanne3)

def send_data(val_Vanne1, val_Vanne2, val_Vanne3):
    # Attendre une connexion d'un client
    client_socket, client_address = server_socket.accept()
    #print("Connexion acceptée de", client_address)
    try:
        # Envoyer une réponse au client
        message = Vanne1 + ":" + Vanne2 + ":" + Vanne3
        client_socket.sendall(message.encode())
        #print("Message envoyé au client :", message)
    except Exception as e:
        print("Erreur :", e)

    # Fermer la connexion avec le client
    client_socket.close()
    #print("Connexion fermée avec le client.")
    return 0

def eteindre_vanne(num_vanne):
    global Vanne1, Vanne2, Vanne3
    if Vanne1 == '1' and num_vanne == 1:
        print(f"Vanne1 :OFF   {datetime.now()}")
        Vanne1 = '0'
        send_data(Vanne1, Vanne2, Vanne3)
    if Vanne2 == '1' and num_vanne == 2:
        print(f"Vanne2 :OFF   {datetime.now()}")
        Vanne2 = '0'
        send_data(Vanne1, Vanne2, Vanne3)
    if Vanne3 == '1' and num_vanne == 3:
        print(f"Vanne3 :OFF   {datetime.now()}")
        Vanne3 = '0'
        send_data(Vanne1, Vanne2, Vanne3)
    return 0


def calculerPremierJour(annee, mois): #calculer le premier jour du mois
    a = (14 - mois) / 12
    y = annee - a
    m = mois + 12 * a - 2
    jour = (1 + y + y / 4 - y / 100 + y / 400 + (31 * m) / 12) % 7
    jour = jour -1
    return jour # Retourne le jour


def getNumberOfDays(year, month): # Calculer le nombre de jours dans le mois
    if month == 1 or month == 3 or month == 5 or month == 7 or month == 8 or month == 10 or month == 12:
        return 31
    elif month == 4 or month == 6 or month == 9 or month == 11:
        return 30
    elif month == 2:
        if (year % 4 == 0 and year % 100 != 0) or year % 400 == 0:
            return 29 # Année bissextile
        else:
            return 28
    else:
        return 0 #Mois invalide

def get_data():
    global duree, StrDateDebut, StrDateFin, recurrence, StrZone1, StrZone2, StrZone3
    global StrDebut1, StrDebut2, StrDebut3, bpVanne1, bpVanne2, bpVanne3, mode, StartDay, StartMonth, StartYear, HeureDebut1, MinDebut1, HeureDebut2, MinDebut2, HeureDebut3, MinDebut3, EndMin1, EndHour1, EndMin2, EndHour2, EndMin3, EndHour3
    # Lecture du fichier CSV
    with open(filename, mode="r", newline="") as file:
        reader = csv.reader(file)

        # Parcourir chaque ligne et affecter les valeurs aux variables correspondantes
        for row in reader:
            if row[0] == "StrDuree":
                duree = int(row[1])
            elif row[0] == "StrDateDebut":
                StrDateDebut = row[1]
            elif row[0] == "StrDateFin":
                StrDateFin = row[1]
            elif row[0] == "StrRecurrence":
                recurrence = int(row[1])
            elif row[0] == "StrZone1":
                StrZone1 = row[1]
            elif row[0] == "StrZone2":
                StrZone2 = row[1]
            elif row[0] == "StrZone3":
                StrZone3 = row[1]
            elif row[0] == "StrDebut1":
                StrDebut1 = row[1]
            elif row[0] == "StrDebut2":
                StrDebut2 = row[1]
            elif row[0] == "StrDebut3":
                StrDebut3 = row[1]
            elif row[0] == "vanne1":
                bpVanne1 = row[1]
            elif row[0] == "vanne2":
                bpVanne2 = row[1]
            elif row[0] == "vanne3":
                bpVanne3 = row[1]
            elif row[0] == "mode":
                mode = row[1]

    StartDay = int(StrDateDebut[8:10])
    StartMonth = int(StrDateDebut[5:7])
    StartYear = int(StrDateDebut[0:4])

    if StrDebut1 != '':
        HeureDebut1 = int(StrDebut1[0:2])
        MinDebut1 = int(StrDebut1[3:5])
    else:
        HeureDebut1 = 0
        MinDebut1 = 0

    if StrDebut2 != '':
        HeureDebut2 = int(StrDebut2[0:2])
        MinDebut2 = int(StrDebut2[3:5])
    else:
        HeureDebut2 = 0
        MinDebut2 = 0

    if StrDebut3 != '':
        HeureDebut3 = int(StrDebut3[0:2])
        MinDebut3 = int(StrDebut3[3:5])
    else:
        HeureDebut3 = 0
        MinDebut3 = 0

    EndMin1 = MinDebut1 + duree
    EndMin2 = MinDebut2 + duree
    EndMin3 = MinDebut3 + duree

    EndHour1 = HeureDebut1
    EndHour2 = HeureDebut2
    EndHour3 = HeureDebut3

    if EndMin1 >= 60:
        EndMin1 = EndMin1 - 60
        EndHour1 = EndHour1 + 1

    if EndMin2 >= 60:
        EndMin2 = EndMin2 - 60
        EndHour2 = EndHour2 + 1

    if EndMin3 >= 60:
        EndMin3 = EndMin3 - 60
        EndHour3 = EndHour3 + 1

    return 0

while(1):
    update_time() # mettre à jour la date
    get_data() #mettre à jour les donnees
    if mode == 'MANU':
        if bpVanne1 == '1':
            allumer_vanne(1)
        else:
            eteindre_vanne(1)

        if bpVanne2 == '1':
            allumer_vanne(2)
        else:
            eteindre_vanne(2)

        if bpVanne3 == '1':
            allumer_vanne(3)
        else:

            eteindre_vanne(3)

    if mode == 'AUTO':
        if current_day - JourArrosage >= 2 and pluie <= 200 and MoistureSensor1 <= SeuilHumidite and temperature < SeuilTemperatureMAX and temperature > SeuilTemperatureMIN and humidity < SeuilHumidity:
            allumer_vanne(1)
            TimerAUTO = TimerAUTO
            JourArrosage = current_day
        else:
           eteindre_vanne(1)

        if TimerAUTO >= delayAUTO:
            TimerAUTO = 0
            eteindre_vanne(1)

    if mode == 'PROG':
        if recurrence != 0 and mode == "PROG": #vérification du mode et de la récurence (div 0)
            if current_day >= StartDay and current_month >= StartMonth and current_year >= StartYear: #vérification de la date d'arrosage
                if StrZone1 == "on" and current_day % recurrence == 0 and current_hour >= HeureDebut1 and current_hour <= EndHour1 and current_min >= MinDebut1 and current_min < EndMin1 and pluie == 1:
                    allumer_vanne(1)
                else:
                    eteindre_vanne(1)
                if StrZone2 == "on" and current_day % recurrence == 0 and current_hour >= HeureDebut2 and current_hour <= EndHour2 and current_min >= MinDebut2 and current_min < EndMin2 and pluie == 1: # vérification de l'heure d'arrogage, de la selection de la zone & capteur de pluie
                    allumer_vanne(2)
                else:
                    eteindre_vanne(2)
                if StrZone3 == "on" and current_day % recurrence == 0 and current_hour >= HeureDebut3 and current_hour <= EndHour3 and current_min >= MinDebut3 and current_min < EndMin3 and pluie == 1:  # vérification de l'heure d'arrogage, de la selection de la zone & capteur de pluie
                    allumer_vanne(3)
                else:
                    eteindre_vanne(3)

        if current_min >= EndMin1 and StrZone1 == "on":
            eteindre_vanne(1)

        if current_min >= EndMin2 and StrZone2 == "on":
            eteindre_vanne(2)

        if current_min >= EndMin3 and StrZone3 == "on":
            eteindre_vanne(3)

#----------------- DEBUG -----------------#
    #print(f"current_day: {current_day}")
    #print(f"current_hour: {current_hour}")
    #print(f"current_min: {current_min}")
    #print(f"StrRecurrence: {StrRecurrence}")
    #print(f"StrZone1: {StrZone1}")
    #print(f"StrZone2: {StrZone2}")
    #print(f"StrZone3: {StrZone3}")
    #print(f"StrDebut1: {StrDebut1}")
    #print(f"StrDebut2: {StrDebut2}")
    #print(f"StrDebut3: {StrDebut3}")
    #print(f"bpVanne1: {bpVanne1}")
    #print(f"bpVanne2: {bpVanne2}")
    #print(f"bpVanne3: {bpVanne3}")
    #print(f"mode: {mode}")
    #print(f"curent date/time: {current_dateTime}")
    #print(f"data : {data}")
    #print("-----------------------------------")
    #time.sleep(0.5)
