from flask import Flask,redirect, url_for,request, render_template_string
from gpiozero import CPUTemperature
import threading
from datetime import datetime
import csv

app = Flask(__name__)
#####------------------------------------- Variables globales -------------------------------------#####
# Modes de fonctionnement & couleurs
MANU_color = ''
AUTO_color = ''
PROG_color = ''
vanne1_color = ''
vanne2_color = ''
vanne3_color = ''

mode = 'MANU'

# Etat des vannes (ON/OFF)
vanne1 = 0
vanne2 = 0
vanne3 = 0

# Variables du mode PROG
StrDuree = 0
StrDateDebut = '0000/00/00'
StrDateFin = '0000/00/00'
StrRecurrence = 0
StrZone1 = 0
StrZone2 = 0
StrZone3 = 0
StrDebut1 = '00/00/0000'
StrDebut2 = '00/00/0000'
StrDebut3 = '00/00/0000'

# Affichage Dashboard
zone1_class = "rectangleON" if StrZone1 == "ON" else "rectangleOFF"
zone1_text = "ON" if StrZone1 == "ON" else "OFF"

zone2_class = "rectangleON" if StrZone2 == "ON" else "rectangleOFF"
zone2_text = "ON" if StrZone2 == "ON" else "OFF"

zone3_class = "rectangleON" if StrZone3 == "ON" else "rectangleOFF"
zone3_text = "ON" if StrZone3 == "ON" else "OFF"

HTMLtabl = ""

def update_time():
    global current_dateTime, current_hour, current_min, current_sec, current_day, current_month, current_year
    current_dateTime = datetime.now()
    current_hour = int(current_dateTime.hour)  # Supprimer l'ajout de +1
    current_min = int(current_dateTime.minute)
    current_sec = int(current_dateTime.second)
    current_day = int(current_dateTime.day)
    current_month = int(current_dateTime.month)
    current_year = int(current_dateTime.year)
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

def update_CSV():
    global mode, StrDuree, StrDateDebut, StrDateFin, StrRecurrence, StrZone1, StrZone2, StrZone3, StrDebut1, StrDebut2, StrDebut3  # Accéder aux variables globales

    #####------------------------------------- Gestion du CSV ---------------->
    data = [
        ["StrDuree", StrDuree],
        ["StrDateDebut", StrDateDebut],
        ["StrDateFin", StrDateFin],
        ["StrRecurrence", StrRecurrence],
        ["StrZone1", StrZone1],
        ["StrZone2", StrZone2],
        ["StrZone3", StrZone3],
        ["StrDebut1", StrDebut1],
        ["StrDebut2", StrDebut2],
        ["StrDebut3", StrDebut3],
        ["vanne1", vanne1],
        ["vanne2", vanne2],
        ["vanne3", vanne3],
        ["mode", mode]
    ]

# Écriture dans le fichier CSV
    with open("/home/pi/Documents/ArrosageAUTO/data.csv", mode="w", newline="") as file:
        writer = csv.writer(file)
        writer.writerows(data)  # Écrire toutes les lignes d'un coup


#####----------------------------------------- Pages Web -----------------------------------------#####
# Page index
@app.route('/')
def index():
    return redirect(url_for('accueil'), code=302)

# Page MANU (redirrection)
@app.route('/manu', methods=['GET', 'POST'])
def manu():
    global mode  # Accéder aux variables globales
    mode = 'MANU'
    update_CSV()
    print(f"mode = {mode}")
    return redirect(url_for('accueil'), code=302)

# Page AUTO (redirrection)
@app.route('/auto', methods=['GET', 'POST'])
def auto():
    global mode  # Accéder aux variables globales
    mode = 'AUTO'
    update_CSV()
    print(f"mode = {mode}")
    return redirect(url_for('accueil'), code=302)

# Page PROG (redirrection)
@app.route('/prog', methods=['GET', 'POST'])
def prog():
    global mode  # Accéder aux variables globales
    mode = 'PROG'
    update_CSV()
    print(f"mode = {mode}")
    return redirect(url_for('accueil'), code=302)

# Page Vanne1 (redirrection)
@app.route('/Vanne1', methods=['GET', 'POST'])
def Vanne1():
    global vanne1, zone1_class, zone1_text  # Accéder aux variables globales
    if vanne1 == 0:
        vanne1 = 1
        zone1_class = "rectangleON"
        zone1_text = "ON"
    else:
        vanne1 = 0
        zone1_class = "rectangleOFF"
        zone1_text = "OFF"
    update_CSV()
    return redirect(url_for('accueil'), code=302)

# Page Vanne2 (redirrection)
@app.route('/Vanne2', methods=['GET', 'POST'])
def Vanne2():
    global vanne2, zone2_class, zone2_text  # Accéder aux variables globales
    if vanne2 == 0:
        vanne2 = 1
        zone2_class = "rectangleON"
        zone2_text = "ON"
    else:
        vanne2 = 0
        zone2_class = "rectangleOFF"
        zone2_text = "OFF"
    update_CSV()
    return redirect(url_for('accueil'), code=302)

# Page Vanne3 (redirrection)
@app.route('/Vanne3', methods=['GET', 'POST'])
def Vanne3():
    global vanne3, zone3_class, zone3_text  # Accéder aux variables globales
    if vanne3 == 0:
        vanne3 = 1
        zone3_class = "rectangleON"
        zone3_text = "ON"
    else:
        vanne3 = 0
        zone3_class = "rectangleOFF"
        zone3_text = "OFF"
    update_CSV()
    return redirect(url_for('accueil'), code=302)

# Page submit
@app.route('/submit', methods=['POST'])
def submit():
    global mode, StrDuree, StrDateDebut, StrDateFin, StrRecurrence, StrZone1, StrZone2, StrZone3, StrDebut1, StrDebut2, StrDebut3  # Accéder aux variables globales
    # Récupération des données du formulaire
    StrDuree = request.form["duree"]
    StrDateDebut = request.form["dateDebut"]
    StrDateFin = request.form["dateFin"]
    StrRecurrence = request.form["recurrence"]
    StrZone1 = request.form.get("zone1")  # Utilisation de get() pour gérer les cases non cochées
    StrZone2 = request.form.get("zone2")
    StrZone3 = request.form.get("zone3")
    StrDebut1 = request.form["heureDebut1"]
    StrDebut2 = request.form["heureDebut2"]
    StrDebut3 = request.form["heureDebut3"]

    update_CSV()
    print("")
    print("Nouveau programme enregistré:")
    print("     ---------------------------")
    print(f"    ⎥StrDateDebut  ⎥{StrDateDebut}  ⎥")
    print(f"    ⎥StrDateFin    ⎥{StrDateFin}  ⎥")
    print(f"    ⎥StrDuree      ⎥{StrDuree} min       ⎥")
    print(f"    ⎥StrRecurrence ⎥{StrRecurrence} jours     ⎥")
    print("     ---------------------------")
    print("")
    # Redirection
    return redirect(url_for('accueil'), code=302)

# Page d'accueil
@app.route('/accueil')
def accueil():
    global vanne1, vanne2, vanne3, mode  # Accéder aux variables globales

    MANU_color = "green" if mode == "MANU" else ""
    AUTO_color = "green" if mode == "AUTO" else ""
    PROG_color = "green" if mode == "PROG" else ""

    vanne1_color = "green" if vanne1 == 1 else ""
    vanne2_color = "green" if vanne2 == 1 else ""
    vanne3_color = "green" if vanne3 == 1 else ""

    if mode == 'MANU':
        return render_template_string('''
           <!DOCTYPE html>
            <html>
            <head>
                <link rel="icon" type="image/png" href="https://static.vecteezy.com/system/resources/previews/021/432/957/non_2x/seedling-and-watering-png.png">
                <link rel="apple-touch-icon" href="https://static.vecteezy.com/system/resources/previews/021/432/957/non_2x/seedling-and-watering-png.png">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
                <title>Arrosage automatique</title>
                    <style>
                        body {
                            font-family: Arial, sans-serif;
                            background-image: url("https://img.freepik.com/vecteurs-libre/fond-geometrique-blanc-dore-realiste_79603-2032.jpg?w=2000"); /* Remplacez par le chemin vers votre image */
                            background-repeat: no-repeat;
                            background-size: cover;
                            margin: 0;
                            padding: 0;
                            display: flex;
                            justify-content: center;
                            align-items: center;
                        }

                        h1 {
                            font-size: 36px;
                            margin-bottom: 25px;
                            color: #4CAF50;
                            text-align: center;
                            font-weight: 700 ;
                        }

                        h2 {
                            font-size: 18px;
                            margin-bottom: 20px;
                            color: #333;
                        }

                        .container {
                            width: 90%;
                            max-width: 700px;
                            min-height: 100vh;
                        }

                        .card {
                            background-color: #fff;
                            border-radius: 10px;
                            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                            padding: 20px;
                            margin-top: 20px;
                            max-width: 700px;
                            border: 1px solid black;
                        }

                        .button {
                        font-size: 14px;
                        background-color: white;
                        color: black;
                        padding: 10px 20px;
                        border: 1px solid rgba(128, 128, 128, 0.25);
                        width: 100px;
                        cursor: pointer;
                        display: flex;
                        justify-content: center;
                        }

                        .button.green {
                            background-color: #4CAF50;
                            color: white;
                        }

                    </style>

                </head>
                <body>
                    <div class="container">
                        <h1>Arrosage automatique</h1>
                        <div class="card">
                            <h2>Mode de fonctionnement :</h2>
                            <form action="/manu" method="post">
                                <button id="button1" class="button {{ MANU_color }}">MANU</button>
                            </form>

                            <form action="/auto" method="post">
                                <button id="button2" class="button {{ AUTO_color }}">AUTO</button>
                            </form>

                            <form action="/prog" method="post">
                                <button id="button3" class="button {{ PROG_color }}">PROG</button>
                            </form>
                        </div>
                        <div class="card">
                            <form action="/Vanne1" method="post">
                                <button id="button4" class="button {{ vanne1_color }}">Vanne 1</button>
                            </form>
                            <br><br>
                            <form action="/Vanne2" method="post">
                                <button id="button5" class="button {{ vanne2_color }}">Vanne 2</button>
                            </form>
                            <br><br>
                            <form action="/Vanne3" method="post">
                                <button id="button6" class="button {{ vanne3_color }}">Vanne 3</button>
                            </form>
                            <br><br>
                        </div>
                    </body>
                    </html>
           ''', MANU_color=MANU_color, AUTO_color=AUTO_color, PROG_color=PROG_color, vanne1_color=vanne1_color, vanne2_color=vanne2_color, vanne3_color=vanne3_color)

    if mode == "AUTO":
        vanne1 = 0
        vanne2 = 0
        vanne3 = 0
        return render_template_string('''
            <!DOCTYPE html>
            <html>
            <head>
                <link rel="icon" type="image/png" href="https://static.vecteezy.com/system/resources/previews/021/432/957/non_2x/seedling-and-watering-png.png">
                <link rel="apple-touch-icon" href="https://static.vecteezy.com/system/resources/previews/021/432/957/non_2x/seedling-and-watering-png.png">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
                <title>Arrosage automatique</title>
                    <style>

                        body {
                            font-family: Arial, sans-serif;
                            background-image: url("https://img.freepik.com/vecteurs-libre/fond-geometrique-blanc-dore-realiste_79603-2032.jpg?w=2000"); /* Remplacez par le chemin vers votre image */
                            background-repeat: no-repeat;
                            background-size: cover;
                            margin: 0;
                            padding: 0;
                            display: flex;
                            justify-content: center;
                            align-items: center;
                        }

                        h1 {
                            font-size: 36px;
                            margin-bottom: 25px;
                            color: #4CAF50;
                            text-align: center;
                            font-weight: 700 ;
                        }

                        .container {
                            width: 90%;
                            max-width: 700px;
                            min-height: 100vh;
                        }

                        .card {
                            background-color: #fff;
                            border-radius: 10px;
                            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                            padding: 20px;
                            margin-top: 20px;
                            max-width: 700px;
                            border: 1px solid black;
                        }

                        h2 {
                            font-size: 18px;
                            margin-bottom: 20px;
                            color: #333;
                        }

                        .button {
                        font-size: 14px;
                        background-color: white;
                        color: black;
                        padding: 10px 20px;
                        border: 1px solid rgba(128, 128, 128, 0.25);
                        width: 100px;
                        cursor: pointer;
                        display: flex;
                        justify-content: center;
                        }

                        .button.green {
                            background-color: #4CAF50;
                            color: white;
                        }


                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1>Arrosage automatique</h1>
                        <div class="card">
                            <h2>Mode de fonctionnement :</h2>
                            <form action="/manu" method="post">
                                <button id="button1" class="button {{ MANU_color }}">MANU</button>
                            </form>

                            <form action="/auto" method="post">
                                <button id="button2" class="button {{ AUTO_color }}">AUTO</button>
                            </form>

                            <form action="/prog" method="post">
                                <button id="button3" class="button {{ PROG_color }}">PROG</button>
                            </form>
                        </div>
                    </body>
                    </html>''', MANU_color=MANU_color, AUTO_color=AUTO_color, PROG_color=PROG_color)

    if mode == "PROG":
        vanne1 = 0
        vanne2 = 0
        vanne3 = 0
        return render_template_string('''
            <!DOCTYPE html>
            <html>
            <head>
                <link rel="icon" type="image/png" href="https://static.vecteezy.com/system/resources/previews/021/432/957/non_2x/seedling-and-watering-png.png">
                <link rel="apple-touch-icon" href="https://static.vecteezy.com/system/resources/previews/021/432/957/non_2x/seedling-and-watering-png.png">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
                <title>Arrosage automatique</title>
                    <style>
                        .popup {
                            position: fixed;
                            top: 50%;
                            left: 50%;
                            transform: translate(-50%, -50%);
                            width: 300px;
                            height: 130px;
                            background-color: white;
                            border: 1px solid black;
                            padding: 20px;
                            display: none;
                        }

                        body {
                            font-family: Arial, sans-serif;
                            background-image: url("https://img.freepik.com/vecteurs-libre/fond-geometrique-blanc-dore-realiste_79603-2032.jpg?w=2000"); /* Remplacez par le chemin vers votre image */
                            background-repeat: no-repeat;
                            background-size: cover;
                            margin: 0;
                            padding: 0;
                            display: flex;
                            justify-content: center;
                            align-items: center;
                        }

                        h1 {
                            font-size: 36px;
                            margin-bottom: 25px;
                            color: #4CAF50;
                            text-align: center;
                            font-weight: 700 ;
                        }

                        h3 {
                            font-size: 30px;
                            margin-bottom: 20px;
                            color: #4CAF50;
                            text-align: center;
                            font-weight: 700 ;
                        }

                        h4 {
                            margin-bottom: 10px;
                            margin-right: 20px;
                            font-weight: normal;
                            text-align: center;
                        }

                        .container {
                            width: 90%;
                            max-width: 700px;
                            min-height: 100vh;
                        }

                        .card {
                            background-color: #fff;
                            border-radius: 10px;
                            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                            padding: 20px;
                            margin-top: 20px;
                            max-width: 700px;
                            border: 1px solid black;
                        }

                        label {
                            display: block;
                            margin-bottom: 10px;
                            color: #666666;
                        }

                        input[type="number"],
                        input[type="date"],
                        input[type="time"]

                        {
                            width: 100%;
                            padding: 8px;
                            border: 1px solid #cccccc;
                            border-radius: 3px;
                            font-size: 12px;
                            margin-bottom: 10px;
                        }

                        input[type="checkbox"] {
                            margin-left: 10px;
                            margin-right: 10px;
                        }

                        .zone {
                            margin-bottom: 10px;
                            margin-right: 20px;
                            font-weight: normal;
                        }

                        input[type="submit"] {
                            width: 150px;
                            height: 30px;
                            background-color: #4CAF50;
                            text-align: center;
                            font-family: Arial, sans-serif;
                            font-size: 15px;
                            color: white;
                        }

                        h2 {
                            font-size: 18px;
                            margin-bottom: 20px;
                            color: #333;
                        }

                        .button {
                        font-size: 14px;
                        background-color: white;
                        color: black;
                        padding: 10px 20px;
                        border: 1px solid rgba(128, 128, 128, 0.25);
                        width: 100px;
                        cursor: pointer;
                        display: flex;
                        justify-content: center;
                        }

                        .button.green {
                            background-color: #4CAF50;
                            color: white;
                        }


                    </style>
                    <script>

                        function showNotification() {
                            alert("Le programme d'arrosage a été enregistré !");
                        }

                        function checkTimeInput(zoneId, heureDebutId) {
                            var zoneCheckbox = document.getElementById(zoneId).checked;
                            var heureDebutInput = document.getElementById(heureDebutId);

                            if (!zoneCheckbox) {
                                heureDebutInput.value = "";
                                heureDebutInput.disabled = true;
                            } else {
                                heureDebutInput.disabled = false;
                            }
                        }

                        function validateForm(event) {
                            // Vérification des informations essentielles ici
                            var duree = document.getElementById("duree").value;
                            var dateDebut = document.getElementById("dateDebut").value;
                            var dateFin = document.getElementById("dateFin").value;
                            var recurrence = document.getElementById("recurrence").value;

                            // Exemple de vérification pour le champ "Durée du programme"
                            if (duree === "" || dateDebut === "" || dateFin === "" || recurrence === "") {
                                alert("Veuillez renseigner les informations nécessaires");
                                event.preventDefault(); // Empêche l'envoi du formulaire
                            }
                            else {
                                alert("Le programme a bien été enregistré !");
                            }
                        }

                    </script>

                </head>
                <body>
                    <div class="container">
                        <h1>Arrosage automatique</h1>
                        <div class="card">
                            <h2>Mode de fonctionnement :</h2>
                            <form action="/manu" method="post">
                                <button id="button1" class="button {{ MANU_color }}">MANU</button>
                            </form>

                            <form action="/auto" method="post">
                                <button id="button2" class="button {{ AUTO_color }}">AUTO</button>
                            </form>

                            <form action="/prog" method="post">
                                <button id="button3" class="button {{ PROG_color }}">PROG</button>
                            </form>
                        </div>

                        <div class="card">
                            <form action="/submit" method="post">
                            <label for="duree">Durée du programme (en minutes) :</label>
                            <input type="number" id="duree" name="duree" > 

                            <br><br>
                            <label for="dateDebut">Date de début :</label>
                            <input type="date" id="dateDebut" name="dateDebut" >

                            <br><br>
                            <label for="dateFin">Date de fin :</label>
                            <input type="date" id="dateFin" name="dateFin" >

                            <br><br>
                            <label for="recurrence">Récurrence (en jours) :</label>
                            <input type="number" id="recurrence" name="recurrence" >

                            <br><br>
                            <h2>Zones du jardin :</h2>
                            <div class="zone">
                                <label for="zone1">
                                    <input type="checkbox" id="zone1" name="zone1" onchange="checkTimeInput('zone1', 'heureDebut1')">
                                    Zone 1
                                </label>
                                <input type="time" id="heureDebut1" name="heureDebut1">
                            </div>

                            <div class="zone">
                                <label for="zone2">
                                    <input type="checkbox" id="zone2" name="zone2" onchange="checkTimeInput('zone2', 'heureDebut2')">
                                    Zone 2
                                </label>
                                <input type="time" id="heureDebut2" name="heureDebut2">
                            </div>
                            <div class="zone">
                                <label for="zone3">
                                    <input type="checkbox" id="zone3" name="zone3" onchange="checkTimeInput('zone3', 'heureDebut3')">
                                    Zone 3
                                </label>
                            <input type="time" id="heureDebut3" name="heureDebut3">
                        </div>
                        <div id="popup" class="popup">
                            <h3>Information</h3>
                            <h4>Le programme a bien été enregistré</h4>
                        </div>

                        <br><br>
                            <input type="submit" value="Valider" onclick="validateForm(event)">
                        </form>
                    </body>
                    </html>''', MANU_color=MANU_color, AUTO_color=AUTO_color, PROG_color=PROG_color)

# Page dashboard
@app.route('/dashboard')
def dashboard():
    if mode == 'PROG' and (StrDateDebut == '0000/00/00' or StrDateFin == '0000/00/00' or StrDuree == '0' or StrRecurrence == '0'):
        return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <link rel='icon' type='image/png' href='https://img.freepik.com/free-icon/pie-chart_318-372376.jpg'>
            <link rel='apple-touch-icon' href='https://img.freepik.com/free-icon/pie-chart_318-372376.jpg'>
            <meta name='viewport' content='width=device-width, initial-scale=1.0'>
            <meta charset='UTF-8'>
            <meta name='viewport' content='width=device-width, initial-scale=1.0'>
            <title>Dashboard</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    background-color: #f2f2f2;
                    margin: 0;
                    padding: 0;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                }

                .container {
                    width: 90%;
                    max-width: 700px;
                    min-height: 100vh;
                }

                .card {
                    background-color: #fff;
                    border-radius: 10px;
                    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                    padding: 20px;
                    margin: 0 auto;
                    max-width: 700px;
                    border: 1px solid black;
                }

                h1 {
                    font-size: 36px;
                    margin-bottom: 25px; 
                    color: #4CAF50; 
                    text-align: center; 
                    font-weight: 700 ;
                }
                h2 {
                    font-size: 18px;
                    margin-bottom: 20px;
                    color: #333;
                    text-align: center;
                }

                h3 {
                    font-size: 24px;
                    margin-bottom: 20px;
                    color: #ff0000;
                    text-align: center;
                }

                p {
                    font-size: 18px;
                    margin-bottom: 20px;
                    color: #666;
                }
                .footer p {
                    text-align: center; 
                    margin-top: 20px;
                    font-size: 14px;
                }

            </style>

            <script src='https://unpkg.com/@lottiefiles/lottie-player@latest/dist/lottie-player.js'></script>

            <body>
            <div class='container'>
                <h1>Tableau de bord</h1>
                <div class='card'>
                    <h3>Erreur</h3>
                    <h2>Aucun programme enregistré</h2>
                    <p>Pour créer votre premier programme: <a href='http://192.168.1.30:5000'>Cliquez ici</a></p>
                    <lottie-player src='https://assets5.lottiefiles.com/packages/lf20_zsLhI1gTMs.json'  background='transparent'  speed='0.7'  style='width: 300px; margin: 0 auto; height: 300px;'  loop  autoplay></lottie-player></head>
                </div>
            <div class='footer'>
                <p style='font-size: 14px;'>Développé par Kyrian BUNEL - 2023</p>
            </div>
            </div>
        </body>
        </html>''')

    else :
        global HTMLtabl
        HTMLtabl = "<h2>Planning d'arrosage</h2> <table> <thead><tr> <th>Lun</th> <th>Mar</th> <th>Mer</th> <th>Jeu</th> <th>Ven</th> <th>Sam</th> <th>Dim</th> </tr> </thead> <tbody>"
        tablDay = 1
        offset = 1
        current_year = datetime.now().year
        current_month = datetime.now().month
        PremierJour = calculerPremierJour(current_year, current_month)
        NumberOfDays = getNumberOfDays(current_year, current_month)

        if PremierJour == 6 and NumberOfDays == 30:
            MaxIter = 7
        else :
            MaxIter = 6

        for a in range(1, MaxIter):
            HTMLtabl += "<tr>"
            for i in range(1, 8):  # 1 to 7
                modulo = tablDay % int(StrRecurrence)
                if PremierJour >= offset or tablDay > NumberOfDays:
                    HTMLtabl += "<td></td>"
                elif modulo == 0 and int(StrDateDebut[-2:]) <= tablDay <= int(StrDateFin[-2:]):
                    HTMLtabl += f"<td class='highlight'>{tablDay}</td>"
                    tablDay += 1
                else:
                    HTMLtabl += f"<td>{tablDay}</td>"
                    tablDay += 1
                offset += 1
            HTMLtabl += "</tr>"

        return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <link rel="icon" type="image/png" href="https://img.freepik.com/free-icon/pie-chart_318-372376.jpg">
            <link rel="apple-touch-icon" href="https://img.freepik.com/free-icon/pie-chart_318-372376.jpg">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <!--meta http-equiv="refresh" content="1"-->
            <title>Dashboard</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    background-color: #f2f2f2;
                    margin: 0;
                    padding: 0;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                }

                .rectangleON {
                    width: 150px;
                    height: 30px;
                    background-color: #4CAF50;
                    text-align: center;
                    line-height: 30px;
                    font-family: Arial, sans-serif;
                    color: white;
                }

                .rectangleOFF {
                    width: 150px;
                    height: 30px;
                    background-color: #ff0d00;
                    text-align: center;
                    line-height: 30px;
                    font-family: Arial, sans-serif;
                    color: white;
                }

                .rectangleDISABLED {
                    width: 150px;
                    height: 30px;
                    background-color: #860063;
                    text-align: center;
                    line-height: 30px;
                    font-family: Arial, sans-serif;
                    color: white;
                }

                .container {
                    width: 90%;
                    max-width: 700px;
                    min-height: 100vh;
                }

                .card {
                    background-color: #fff;
                    border-radius: 10px;
                    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                    padding: 20px;
                    margin: 0 auto;
                    max-width: 700px;
                    border: 1px solid black;
                }


                h1 {
                    font-size: 36px;
                    margin-bottom: 25px; 
                    color: #4CAF50; 
                    text-align: center; 
                    font-weight: 700 ;
                }
                h2 {
                    font-size: 18px;
                    margin-bottom: 20px;
                    color: #333;
                    text-align: center;
                }

                p {
                    font-size: 18px;
                    margin-bottom: 10px;
                    color: #666;
                }

                table {
                    border-collapse: collapse;
                    width: 100%;
                    margin-bottom: 20px;
                }

                th, td {
                    text-align: center;
                    padding: 8px;
                }

                th {
                    background-color: #333;
                    color: white;
                }

                td {
                    border: 1px solid #ddd;
                }

                .today {
                    background-color: #4CAF50;
                    color: white;
                }

                .footer p {
                    text-align: center; 
                    margin-top: 20px;
                    font-size: 14px;
                }

                .highlight {
                    background-color: #4CAF50;
                    color: white;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Tableau de bord</h1>
                <div class="card">
                    <h2>Programme en cours</h2>
                    <p>Date de début: {{StrDateDebut}}</p>
                    <p>Date de fin: {{StrDateFin}}</p>
                    <p>Durée d'arrosage: {{StrDuree}} min</p>
                    <p>Récurrence: {{StrRecurrence}} jours</p>
                    {{HTMLtabl}}
                            </tbody>
                        </table>
                    <h2>Etat des vannes</h2>
                    <p>Zone 1: </p>
                    <div class="{{zone1_class}}">{{zone1_text}}</div>
                    <p>Zone 2: </p>
                    <div class="{{zone2_class}}">{{zone2_text}}</div>
                    <p>Zone 3: </p>
                    <div class="{{zone3_class}}">{{zone3_text}}</div>
                    <p>Zone 4: </p>
                    <div class="{{zone4_class}}">{{zone4_text}}</div>
                    <h2>Etat des capteurs</h2>
                    <p>Date locale: <span id="heure"></span></p>
                    <p>Heure locale: <span id="heure"></span></p>
                    <p>Débit mesuré: <span id="debit"></span></p>
                    <p>Valeur capteur de pluie: <span id="capteurPluie"></span></p>
                    <p>Utilisation de la mémoire: <span id="capteurPluie"></span></p>
                </div>
                <div class="footer">
                    <p style="font-size: 14px;">Développé par Kyrian BUNEL - 2023</p>
                </div>
            </div>
        </body>
        </html>''', StrDateDebut=StrDateDebut, StrDateFin=StrDateFin, StrDuree=StrDuree, StrRecurrence=StrRecurrence, zone1_class=zone1_class, zone1_text=zone1_text, zone2_class=zone2_class, zone2_text=zone2_text, zone3_class=zone3_class, zone3_text=zone3_text, HTMLtabl=HTMLtabl)

if __name__ == '__main__':
    # Lancement du serveur Flask
    app.run(host='0.0.0.0')

