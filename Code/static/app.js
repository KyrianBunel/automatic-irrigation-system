// Rafraîchit l'état réel (vannes, ESP32, décision) toutes les 3 secondes.
(function () {
  "use strict";

  const modeAffiche = document.body.dataset.mode;
  const bandeau = document.getElementById("connexion");

  function majVanne(carte, ouverte) {
    carte.classList.toggle("ouverte", ouverte === true);
    carte.querySelector(".etat").textContent =
      ouverte === true ? "Ouverte" : ouverte === false ? "Fermée" : "Inconnu";
    const champ = carte.querySelector("input[name=etat]");
    const bouton = carte.querySelector("button");
    if (champ && bouton) {
      champ.value = ouverte ? "0" : "1";
      bouton.textContent = ouverte ? "Fermer" : "Ouvrir";
    }
  }

  async function rafraichir() {
    try {
      const rep = await fetch("/api/etat", { cache: "no-store", credentials: "same-origin" });
      if (!rep.ok) throw new Error(rep.status);
      const d = await rep.json();
      bandeau.classList.add("cache");

      // Mode changé ailleurs (Home Assistant...) : on recharge, sauf si un formulaire est en cours de saisie
      if (d.mode !== modeAffiche && !document.activeElement.matches("input")) {
        window.location.reload();
        return;
      }

      document.querySelectorAll(".vanne").forEach(function (carte) {
        majVanne(carte, d.vannes[carte.dataset.vanne]);
      });

      const esp = document.getElementById("esp");
      esp.classList.toggle("ok", d.esp === true);
      esp.classList.toggle("ko", d.esp !== true);
      esp.textContent = d.esp === true ? "Vannes en ligne"
        : d.esp === false ? "Vannes hors ligne" : "Vannes : état inconnu";

      if (d.decision) document.getElementById("decision").textContent = d.decision;
      document.getElementById("heure").textContent = d.heure;
    } catch (e) {
      bandeau.classList.remove("cache");
    }
  }

  // Programme : l'heure n'est modifiable (et obligatoire) que si la zone est cochée
  document.querySelectorAll("input[type=checkbox][data-heure]").forEach(function (caseZone) {
    const heure = document.getElementById(caseZone.dataset.heure);
    const maj = function () {
      heure.disabled = !caseZone.checked;
      heure.required = caseZone.checked;
    };
    caseZone.addEventListener("change", maj);
    maj();
  });

  // Évite le double envoi d'un formulaire (double appui sur mobile)
  document.querySelectorAll("form").forEach(function (f) {
    f.addEventListener("submit", function () {
      const b = f.querySelector("button");
      if (b) setTimeout(function () { b.disabled = true; }, 0);
    });
  });

  rafraichir();
  setInterval(rafraichir, 3000);
})();
