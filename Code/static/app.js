// Arrosage – web app. Affiche l'état réel (rafraîchi toutes les 3 s) et envoie les commandes en JSON.
(function () {
  "use strict";

  const CSRF = document.body.dataset.csrf;
  const NOMS_MODES = { MANU: "Manuel", AUTO: "Météo", PROG: "Programme" };
  const $ = (id) => document.getElementById(id);

  let etat = null;
  let progEdite = false;      // ne pas écraser le formulaire pendant la saisie
  let dureeEditee = false;
  let minuterie = null;

  // ---------------------------------------------------------------------------
  // Outils
  // ---------------------------------------------------------------------------
  function duree(secondes) {
    const min = Math.ceil(secondes / 60);
    if (min < 60) return min + " min";
    const h = Math.floor(min / 60), m = min % 60;
    return h + " h" + (m ? " " + String(m).padStart(2, "0") : "");
  }

  function listeFr(items) {
    if (items.length <= 1) return items.join("");
    return items.slice(0, -1).join(", ") + " et " + items[items.length - 1];
  }

  function nombre(x, decimales) {
    return x === null || x === undefined ? "—" : x.toFixed(decimales).replace(".", ",");
  }

  let toastTimer = null;
  function toast(message, erreur) {
    const t = $("toast");
    t.textContent = message;
    t.classList.toggle("erreur", !!erreur);
    t.classList.add("visible");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove("visible"), erreur ? 5000 : 2600);
  }

  async function envoyer(url, donnees) {
    try {
      const rep = await fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": CSRF },
        body: JSON.stringify(donnees || {}),
      });
      if (rep.status === 401) { window.location.href = "/connexion"; return null; }
      const r = await rep.json();
      toast(r.message, !r.ok);
      return r;
    } catch (e) {
      toast("Le Raspberry Pi ne répond pas. Vérifiez que vous êtes sur le Wi-Fi de la maison.", true);
      return null;
    } finally {
      rafraichir();
    }
  }

  // ---------------------------------------------------------------------------
  // Affichage
  // ---------------------------------------------------------------------------
  function afficherEtat(d) {
    const bloc = $("etat");
    const coulent = d.zones.filter((z) => z.ouverte);
    bloc.classList.remove("eau", "alerte");
    $("debit").hidden = true;
    $("arreter").hidden = true;

    if (d.esp === false) {
      bloc.classList.add("alerte");
      $("phrase").textContent = "Le boîtier des vannes ne répond pas.";
      $("detail").textContent = "Les vannes restent fermées par sécurité. Vérifiez son alimentation et le Wi-Fi.";
      return;
    }

    if (coulent.length) {
      bloc.classList.add("eau");
      const noms = coulent.map((z) => String(z.zone));
      $("phrase").textContent = coulent.length === 1
        ? "La zone " + noms[0] + " arrose."
        : "Les zones " + listeFr(noms) + " arrosent.";
      const avecTemps = coulent.filter((z) => z.reste_s !== null);
      if (avecTemps.length) {
        const z = avecTemps.reduce((a, b) => (a.reste_s < b.reste_s ? a : b));
        let texte = "Encore " + duree(z.reste_s) + ".";
        if (z.source === "MANU") texte = "Fermeture automatique dans " + duree(z.reste_s) + ".";
        $("detail").textContent = texte;
        if (z.total_s) {
          const fait = Math.min(1, Math.max(0, 1 - z.reste_s / z.total_s));
          $("debit-niveau").style.width = (fait * 100).toFixed(1) + "%";
          $("debit").hidden = false;
        }
      } else {
        $("detail").textContent = "";
      }
      $("arreter").hidden = false;
      return;
    }

    $("phrase").textContent = "Rien n'arrose.";
    if (d.mode === "MANU") {
      $("detail").textContent = "Ouvrez une zone ci-dessous pour arroser.";
    } else if (d.mode === "AUTO") {
      $("detail").textContent = "Prochaine vérification de la météo " + d.auto.prochaine + ".";
    } else if (d.prochain) {
      $("detail").textContent = "Prochain arrosage " + d.prochain.quand + " à " + d.prochain.creneaux[0].heure + ".";
    } else {
      $("detail").textContent = "Aucun arrosage programmé.";
    }
  }

  function afficherLiaison(d) {
    const l = $("liaison");
    l.classList.toggle("ok", d.esp === true);
    l.classList.toggle("ko", d.esp === false);
    l.textContent = d.esp === true ? "Vannes connectées" : d.esp === false ? "Vannes déconnectées" : "État des vannes inconnu";
  }

  function afficherMode(d) {
    document.querySelectorAll(".segments button").forEach((b) => {
      b.setAttribute("aria-checked", String(b.dataset.mode === d.mode));
    });
    const explications = {
      MANU: "Vous ouvrez et fermez les zones vous-même. Une zone se referme seule au bout de " + d.limites.manu_min + " min.",
      AUTO: "Chaque matin, le système décide d'arroser en fonction de la pluie et de la température.",
      PROG: "Les zones s'arrosent aux jours et aux heures que vous choisissez.",
    };
    $("explication").textContent = explications[d.mode];
    const dec = $("decision");
    dec.hidden = d.mode === "MANU" || !d.decision;
    dec.textContent = d.decision ? "Dernière décision\u00a0: " + d.decision : "";
    $("panneau-auto").hidden = d.mode !== "AUTO";
    $("panneau-prog").hidden = d.mode !== "PROG";
  }

  function afficherZones(d) {
    const ul = $("zones");
    if (ul.children.length !== d.zones.length) {
      ul.innerHTML = "";
      d.zones.forEach((z) => {
        const li = document.createElement("li");
        li.innerHTML =
          '<span class="zone-texte"><span class="zone-nom">Zone ' + z.zone + '</span>' +
          '<span class="zone-etat"></span></span>' +
          '<span class="inter"><input type="checkbox" role="switch" aria-label="Zone ' + z.zone + '"></span>';
        li.querySelector("input").addEventListener("change", (e) => {
          const ouvrir = e.target.checked;
          e.target.disabled = true;
          envoyer("/api/vanne/" + z.zone, { ouvrir: ouvrir }).then((r) => {
            if (!r || !r.ok) e.target.checked = !ouvrir;
          });
        });
        ul.appendChild(li);
      });
    }
    d.zones.forEach((z, k) => {
      const li = ul.children[k];
      const inter = li.querySelector("input");
      li.classList.toggle("coule", z.ouverte === true);
      inter.checked = z.ouverte === true;
      inter.disabled = d.mode !== "MANU" || d.esp !== true;
      let texte;
      if (z.ouverte === true) texte = z.reste_s !== null ? "Arrose, encore " + duree(z.reste_s) : "Arrose";
      else if (z.ouverte === false) texte = d.mode === "MANU" ? "Fermée" : "Fermée, pilotée par le mode " + NOMS_MODES[d.mode];
      else texte = "État inconnu";
      li.querySelector(".zone-etat").textContent = texte;
    });
  }

  function afficherAuto(d) {
    if (d.mode !== "AUTO") return;
    $("regle-auto").textContent = "Chaque jour à " + d.auto.heure +
      ", les zones s'arrosent l'une après l'autre si ces trois conditions sont réunies\u00a0:";
    $("criteres").innerHTML = "";
    d.auto.criteres.forEach((c) => {
      const li = document.createElement("li");
      const classe = c.ok === true ? "ok" : c.ok === false ? "ko" : "inconnu";
      const signe = c.ok === true ? "✓ " : c.ok === false ? "✗ " : "";
      li.innerHTML = '<span class="critere-texte"><span></span><span class="critere-condition"></span></span>' +
        '<span class="critere-valeur ' + classe + '"></span>';
      li.querySelector(".critere-texte span").textContent = c.nom;
      li.querySelector(".critere-condition").textContent = c.condition;
      li.querySelector(".critere-valeur").textContent = c.valeur === null ? "inconnu" : signe + c.valeur;
      $("criteres").appendChild(li);
    });
    const champ = $("duree-auto");
    champ.max = d.limites.duree_max;
    if (!dureeEditee && document.activeElement !== champ) champ.value = d.auto.duree;
  }

  function afficherProgramme(d) {
    if (d.mode !== "PROG") return;
    const p = d.prochain;
    $("prochain").innerHTML = "";
    if (p) {
      $("prochain").append("Prochain arrosage ");
      const fort = document.createElement("strong");
      fort.textContent = p.quand + ", " + listeFr(p.creneaux.map((c) => "zone " + c.zone + " à " + c.heure));
      $("prochain").append(fort, ".");
    } else {
      $("prochain").textContent = "Aucun arrosage à venir : complétez le programme ci-dessous.";
    }
    $("aide-prog").textContent = "Une seule zone arrose à la fois : espacez les heures de départ d'au moins la durée par zone." +
      (d.limites.pluie_prog ? " Le programme est suspendu s'il est tombé plus de " + d.limites.seuil_pluie + " mm." : "");

    if (progEdite) return;
    const f = $("form-prog");
    const prog = d.programme;
    f.dateDebut.value = prog.dateDebut || "";
    f.dateFin.value = prog.dateFin || "";
    f.recurrence.value = prog.recurrence;
    f.duree.value = prog.duree;
    f.duree.max = d.limites.duree_max;

    const ul = $("prog-zones");
    if (ul.children.length !== prog.zones.length) {
      ul.innerHTML = "";
      prog.zones.forEach((z) => {
        const li = document.createElement("li");
        li.innerHTML =
          '<span class="inter"><input type="checkbox" role="switch" name="zone' + z.zone + '" aria-label="Arroser la zone ' + z.zone + '"></span>' +
          '<span class="zone-nom">Zone ' + z.zone + '</span>' +
          '<input type="time" name="heureDebut' + z.zone + '" aria-label="Heure de départ zone ' + z.zone + '">';
        const caseZone = li.querySelector("input[type=checkbox]");
        const heure = li.querySelector("input[type=time]");
        caseZone.addEventListener("change", () => { heure.disabled = !caseZone.checked; if (caseZone.checked && !heure.value) heure.focus(); });
        ul.appendChild(li);
      });
    }
    prog.zones.forEach((z, k) => {
      const li = ul.children[k];
      const caseZone = li.querySelector("input[type=checkbox]");
      const heure = li.querySelector("input[type=time]");
      caseZone.checked = z.active;
      heure.value = z.heure || "";
      heure.disabled = !z.active;
    });
  }

  function afficherMeteo(d) {
    const s = d.station;
    const cases = [
      [nombre(s.temperature, 1) + "°", "Temp."],
      [s.humidite === null ? "—" : Math.round(s.humidite) + " %", "Humidité"],
      [nombre(s.pluie, 1) + " mm", "Pluie 1 h"],
      [s.batterie === null ? "—" : s.batterie + " %", "Batterie"],
    ];
    const dl = $("meteo");
    dl.innerHTML = "";
    cases.forEach(([valeur, nom]) => {
      const div = document.createElement("div");
      const dd = document.createElement("dd");
      const dt = document.createElement("dt");
      dd.textContent = valeur;
      dt.textContent = nom;
      div.append(dd, dt);
      dl.appendChild(div);
    });
    let maj = "La station météo n'a encore rien envoyé.";
    if (s.horodatage) {
      const t = new Date(s.horodatage);
      const minutes = Math.round((Date.now() - t.getTime()) / 60000);
      const heure = t.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
      maj = minutes > 180
        ? "Dernière mesure le " + t.toLocaleDateString("fr-FR") + " à " + heure + " : la station ne transmet plus."
        : "Mesuré à " + heure + " par la station du jardin.";
    }
    $("meteo-maj").textContent = maj;
  }

  function afficher(d) {
    etat = d;
    afficherLiaison(d);
    afficherEtat(d);
    afficherMode(d);
    afficherZones(d);
    afficherAuto(d);
    afficherProgramme(d);
    afficherMeteo(d);
  }

  async function rafraichir() {
    try {
      const rep = await fetch("/api/etat", { cache: "no-store", credentials: "same-origin" });
      if (rep.status === 401) { window.location.href = "/connexion"; return; }
      if (!rep.ok) throw new Error(rep.status);
      afficher(await rep.json());
    } catch (e) {
      const l = $("liaison");
      l.className = "liaison ko";
      l.textContent = "Raspberry Pi injoignable";
    }
  }

  function demarrer() {
    rafraichir();
    clearInterval(minuterie);
    minuterie = setInterval(rafraichir, 3000);
  }

  // ---------------------------------------------------------------------------
  // Actions
  // ---------------------------------------------------------------------------
  document.querySelectorAll(".segments button").forEach((b) => {
    b.addEventListener("click", () => {
      if (etat && b.dataset.mode === etat.mode) return;
      progEdite = false;
      envoyer("/api/mode", { mode: b.dataset.mode });
    });
  });

  $("arreter").addEventListener("click", () => envoyer("/api/arreter"));
  $("lancer").addEventListener("click", (e) => {
    e.target.disabled = true;
    envoyer("/api/cycle").finally(() => { e.target.disabled = false; });
  });

  // Boutons − / +
  document.querySelectorAll(".pas").forEach((pas) => {
    const champ = pas.querySelector("input");
    const changer = (delta) => {
      const min = Number(champ.min) || 1, max = Number(champ.max) || 999;
      champ.value = Math.min(max, Math.max(min, (Number(champ.value) || min) + delta));
      champ.dispatchEvent(new Event("change", { bubbles: true }));
    };
    pas.querySelector(".pas-moins").addEventListener("click", () => changer(-1));
    pas.querySelector(".pas-plus").addEventListener("click", () => changer(1));
  });

  // Durée du mode Météo : enregistrée 0,8 s après le dernier changement
  let dureeTimer = null;
  $("duree-auto").addEventListener("change", (e) => {
    dureeEditee = true;
    clearTimeout(dureeTimer);
    dureeTimer = setTimeout(() => {
      envoyer("/api/duree", { duree: e.target.value }).finally(() => { dureeEditee = false; });
    }, 800);
  });

  const form = $("form-prog");
  form.addEventListener("input", () => { progEdite = true; });
  form.addEventListener("change", () => { progEdite = true; });
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const donnees = {
      dateDebut: form.dateDebut.value,
      dateFin: form.dateFin.value,
      recurrence: form.recurrence.value,
      duree: form.duree.value,
    };
    form.querySelectorAll("#prog-zones li").forEach((li, k) => {
      const n = k + 1;
      donnees["zone" + n] = li.querySelector("input[type=checkbox]").checked ? "on" : "";
      donnees["heureDebut" + n] = li.querySelector("input[type=time]").value;
    });
    const bouton = form.querySelector("button[type=submit]");
    bouton.disabled = true;
    const r = await envoyer("/api/programme", donnees);
    bouton.disabled = false;
    const ul = $("erreurs");
    ul.innerHTML = "";
    if (r && r.erreurs && r.erreurs.length) {
      r.erreurs.forEach((m) => { const li = document.createElement("li"); li.textContent = m; ul.appendChild(li); });
      ul.hidden = false;
      ul.scrollIntoView({ behavior: "smooth", block: "center" });
    } else {
      ul.hidden = true;
      if (r && r.ok) progEdite = false;
    }
  });

  // Conseil d'installation sur iPhone (hors mode plein écran)
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
  let masque = false;
  try { masque = localStorage.getItem("installer-masque") === "1"; } catch (e) { /* stockage indisponible */ }
  if (ios && !navigator.standalone && !masque) $("installer").hidden = false;
  $("installer-fermer").addEventListener("click", () => {
    $("installer").hidden = true;
    try { localStorage.setItem("installer-masque", "1"); } catch (e) { /* rien */ }
  });

  // Pause quand l'app est en arrière-plan
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) clearInterval(minuterie);
    else demarrer();
  });

  demarrer();
})();
