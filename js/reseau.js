/* ============================================================
   SchoolManager — Réseau scolaire interne (Phase 12)
   ------------------------------------------------------------
   Fil de l'établissement, forum, groupes de travail et
   bibliothèque de ressources.

   Deux principes :

   1. Le SERVEUR décide de tout : visibilité, autorisations,
      périmètre. La page ne fait que refléter les drapeaux
      calculés par l'API (`peutModifier`, `peutSupprimer`,
      `peutModerer`, `estMembre`, `peutSupprimer` du groupe…).
      Aucune règle de rôle n'est réécrite ici.
   2. Les capacités (`SM.peut`) servent uniquement à ne pas
      AFFICHER un bouton que le serveur refuserait de toute
      façon — jamais à autoriser quoi que ce soit.
   ============================================================ */

(function () {
  "use strict";

  var SM = window.SM;
  var API = window.API;
  var SD = window.SD || {};

  function el(id) { return document.getElementById(id); }

  /* ---------- Capacités (affichage seul) ---------- */
  var peutEcrire = SM.peut && SM.peut("reseau.ecrire");
  var peutModerer = SM.peut && SM.peut("reseau.moderer");

  /* ---------- État local ---------- */
  var vue = "fil";                 // fil | forum | groupes | bibliotheque
  var publications = [];
  var groupes = [];
  var ressources = [];
  var resume = null;
  var filtres = { q: "", auteur: "" };
  var commentairesOuverts = {};    // id de publication → liste affichée
  var modificationEnCours = null;  // id de publication en cours d'édition
  var supprAction = null;          // action en attente de confirmation
  var chargementEnCours = false;
  var minuteurRecherche = null;

  var moi = window.SM_MOI || {};

  /* ============================================================
     Utilitaires d'affichage
     ============================================================ */

  function echapper(s) {
    return SM.escapeHtml ? SM.escapeHtml(s == null ? "" : String(s)) : String(s == null ? "" : s);
  }

  /* Texte saisi par un utilisateur : échappé PUIS retours à la ligne
     convertis en <br>. L'échappement passe toujours en premier. */
  function texteRiche(s) {
    return echapper(s).replace(/\n/g, "<br>");
  }

  function dateHeure(iso) {
    if (!iso) return "";
    var d = new Date(iso.replace(" ", "T"));
    if (isNaN(d.getTime())) return "";
    return d.toLocaleString("fr-FR", {
      day: "numeric", month: "long", hour: "2-digit", minute: "2-digit"
    });
  }

  /* « il y a 3 min », « hier », « le 12/09 » … */
  function tempsRelatif(iso) {
    if (!iso) return "";
    var d = new Date(iso.replace(" ", "T"));
    if (isNaN(d.getTime())) return "";
    var secondes = Math.floor((Date.now() - d.getTime()) / 1000);
    if (secondes < 60) return "à l'instant";
    var minutes = Math.floor(secondes / 60);
    if (minutes < 60) return "il y a " + minutes + " min";
    var heures = Math.floor(minutes / 60);
    if (heures < 24) return "il y a " + heures + " h";
    var jours = Math.floor(heures / 24);
    if (jours === 1) return "hier";
    if (jours < 7) return "il y a " + jours + " jours";
    return "le " + d.toLocaleDateString("fr-FR");
  }

  var ICONE_GROUPE = { classe: "🏫", matiere: "📚", projet: "🚀", club: "🎯" };
  var ICONE_RESSOURCE = { lien: "🔗", document: "📄", video: "🎬", exercice: "✏️" };

  function classeBadge(role) {
    if (role === "Direction" || role === "Professeur") return "badge badge-info";
    if (role === "Surveillant") return "badge badge-warning";
    return "badge badge-neutral";
  }

  function estEncadrement() {
    var r = SM.roleCourant && SM.roleCourant();
    return r === "Administrateur" || r === "Professeur" || r === "Surveillant";
  }

  /* Types de groupe réellement ouverts à ce compte. « Club » et « projet »
     sont libres ; « classe » suppose qu'au moins une classe soit visible ;
     « matière » est réservé au personnel (même règle que le serveur). */
  function typesGroupeAutorises() {
    var types = ["club", "projet"];
    if ((SD.classes || []).length) types.push("classe");
    if (estEncadrement()) types.push("matiere");
    return types;
  }

  /* ============================================================
     Chargement des données
     ============================================================ */

  function afficherChargement() {
    var hote = el("reseauVue");
    if (hote) hote.innerHTML = '<div class="card reseau-charge">Chargement du réseau…</div>';
  }

  function erreurReseau(e) {
    var msg = (e && e.message) || "Le réseau est momentanément indisponible.";
    el("reseauVue").innerHTML =
      '<div class="card reseau-vide"><div class="empty-state"><div class="e-ico">🔌</div>' +
      "<h4>Impossible de charger le réseau</h4><p>" + echapper(msg) + "</p></div></div>";
  }

  function chargerResume() {
    return API.reseauResume().then(function (r) {
      resume = r;
      renduResume();
    }).catch(function () { /* indicateur secondaire : silencieux */ });
  }

  function chargerGroupes() {
    return API.reseauGroupes().then(function (r) {
      groupes = (r && r.groupes) || [];
      rendreGroupesCote();
      remplirSelecteursGroupes();
      if (vue === "groupes") renduGroupes();
    }).catch(function (e) {
      if (vue === "groupes") erreurReseau(e);
    });
  }

  function chargerRessources() {
    return API.reseauRessources(filtres.q ? { q: filtres.q } : {}).then(function (r) {
      ressources = (r && r.ressources) || [];
      if (vue === "bibliotheque") renduBibliotheque();
    }).catch(function (e) {
      if (vue === "bibliotheque") erreurReseau(e);
    });
  }

  function chargerPublications() {
    if (chargementEnCours) return Promise.resolve();
    chargementEnCours = true;
    afficherChargement();

    var filtresApi = {};
    if (filtres.q) filtresApi.q = filtres.q;
    if (filtres.auteur) filtresApi.auteur = filtres.auteur;
    if (vue === "forum") filtresApi.type = "discussion";

    return API.reseauFil(filtresApi).then(function (r) {
      publications = (r && r.publications) || [];
      chargementEnCours = false;
      renduFil();
    }).catch(function (e) {
      chargementEnCours = false;
      erreurReseau(e);
    });
  }

  function chargerTout() {
    return Promise.all([chargerPublications(), chargerGroupes(), chargerResume()]);
  }

  /* ============================================================
     Vue : FIL (et FORUM, même rendu filtré par type)
     ============================================================ */

  function renduFil() {
    var hote = el("reseauVue");
    if (!hote) return;

    if (!publications.length) {
      var messageVide = filtres.q
        ? "Aucune publication ne correspond à « " + echapper(filtres.q) + " »."
        : vue === "forum"
          ? "Aucune discussion ouverte pour le moment."
          : "Le fil de l'établissement est encore vide.";
      hote.innerHTML =
        '<div class="card reseau-vide"><div class="empty-state"><div class="e-ico">🌐</div>' +
        "<h4>Rien à afficher</h4><p>" + messageVide +
        (peutEcrire ? " Lancez la conversation ci-dessus." : "") + "</p></div></div>";
      return;
    }

    hote.innerHTML = publications.map(cartePublication).join("");
  }

  function cartePublication(p) {
    var enEdition = modificationEnCours === p.id;
    var ouvert = !!commentairesOuverts[p.id];

    var entete =
      '<div class="rp-tete">' +
      SM.avatarHTML(p.auteurNom || "Membre") +
      '<div class="rp-identite">' +
      '  <div class="rp-nom">' + echapper(p.auteurNom) +
      (p.estAuteur ? ' <span class="badge badge-neutral">vous</span>' : "") + "</div>" +
      '  <div class="rp-meta">' +
      '    <span class="' + classeBadge(p.auteurRoleLibelle) + '">' + echapper(p.auteurRoleLibelle || "") + "</span>" +
      "    <span>🕒 " + echapper(tempsRelatif(p.creeLe)) + "</span>" +
      (p.groupeNom ? '    <span class="chip-plain">👥 ' + echapper(p.groupeNom) + "</span>" : "") +
      (p.epingle ? '    <span class="badge badge-info">📌 Épinglé</span>' : "") +
      (p.masque ? '    <span class="badge badge-danger">🚫 Masqué</span>' : "") +
      (p.majLe ? '    <span title="Modifié le ' + echapper(dateHeure(p.majLe)) + '">(modifié)</span>' : "") +
      "  </div>" +
      "</div>" +
      menuPublication(p) +
      "</div>";

    var corps;
    if (enEdition) {
      corps =
        '<div class="rp-titre" style="margin-top:14px">Modifier la publication</div>' +
        '<textarea class="textarea" id="edContenu-' + p.id + '" rows="4">' + echapper(p.contenu) + "</textarea>" +
        '<div class="rp-barre">' +
        '  <button class="btn btn-primary" type="button" data-action="enregistrer-edition" data-id="' + p.id + '">Enregistrer</button>' +
        '  <button class="btn btn-ghost" type="button" data-action="annuler-edition">Annuler</button>' +
        "</div>";
    } else {
      corps =
        (p.titre ? '<div class="rp-titre">' + texteRiche(p.titre) + "</div>" : "") +
        '<div class="rp-contenu">' + texteRiche(p.contenu) + "</div>" +
        '<div class="rp-barre">' +
        '  <button class="rp-bouton' + (p.jaime ? " jaime" : "") + '" type="button" data-action="jaime" data-id="' + p.id + '"' +
        (peutEcrire ? "" : ' disabled title="Réservé aux membres"') + ">" +
        "    " + (p.jaime ? "❤️" : "🤍") + ' <span class="rp-nombre">' + (p.jaimeCount || 0) + "</span></button>" +
        '  <button class="rp-bouton" type="button" data-action="commentaires" data-id="' + p.id + '">' +
        "    💬 Commenter" + (p.commentaires && p.commentaires.length ? ' <span class="rp-nombre">' + p.commentaires.length + "</span>" : "") +
        "</button>" +
        "</div>";
    }

    var commentaires = ouvert ? zoneCommentaires(p) : "";

    return (
      '<article class="card reseau-post' + (p.epingle ? " epingle" : "") + (p.masque ? " masque" : "") + '">' +
      entete + corps + commentaires +
      "</article>"
    );
  }

  function menuPublication(p) {
    var actions = [];
    if (p.peutModifier && !p.masque) {
      actions.push('<button class="btn-icon" title="Modifier" data-action="editer" data-id="' + p.id + '">✏️</button>');
    }
    if (p.peutModerer) {
      actions.push('<button class="btn-icon" title="' + (p.epingle ? "Désépingler" : "Épingler") + '" data-action="epingler" data-id="' + p.id + '">📌</button>');
      actions.push('<button class="btn-icon" title="' + (p.masque ? "Réafficher" : "Masquer (modération)") + '" data-action="masquer" data-id="' + p.id + '">' + (p.masque ? "👁️" : "🚫") + "</button>");
    }
    if (p.peutSupprimer) {
      actions.push('<button class="btn-icon danger" title="Supprimer" data-action="supprimer-publication" data-id="' + p.id + '">🗑️</button>');
    }
    if (!actions.length) return "";
    return '<div class="rp-actions">' + actions.join("") + "</div>";
  }

  function zoneCommentaires(p) {
    var liste = (p.commentaires || []).map(function (c) {
      return (
        '<div class="rp-commentaire">' +
        SM.avatarHTML(c.auteurNom || "Membre", "sm") +
        '<div class="rp-commentaire-corps">' +
        '  <div class="rp-commentaire-nom">' + echapper(c.auteurNom) +
        '    <span class="chip-plain" style="margin-left:6px">' + echapper(c.auteurRoleLibelle || "") + "</span>" +
        "  </div>" +
        '  <div class="rp-commentaire-texte">' + texteRiche(c.contenu) + "</div>" +
        '  <div class="rp-commentaire-temps">' + echapper(dateHeure(c.creeLe)) + "</div>" +
        "</div>" +
        (c.peutSupprimer
          ? '<button class="rp-commentaire-suppr" title="Supprimer" data-action="supprimer-commentaire" data-id="' + c.id + '">✕</button>'
          : "") +
        "</div>"
      );
    }).join("");

    var saisie = peutEcrire
      ? '<div class="rp-saisie-commentaire">' +
        SM.avatarHTML(moi.nom || "Moi", "sm") +
        '<input class="input" id="cmt-' + p.id + '" placeholder="Écrire un commentaire…">' +
        '<button class="btn btn-primary" type="button" data-action="envoyer-commentaire" data-id="' + p.id + '">Envoyer</button>' +
        "</div>"
      : "";

    return '<div class="rp-commentaires">' + liste + "</div>" + saisie;
  }

  /* ============================================================
     Vue : GROUPES
     ============================================================ */

  function renduGroupes() {
    var hote = el("reseauVue");
    if (!hote) return;

    if (!groupes.length) {
      hote.innerHTML =
        '<div class="card reseau-vide"><div class="empty-state"><div class="e-ico">👥</div>' +
        "<h4>Aucun groupe accessible</h4><p>" +
        (peutEcrire
          ? "Créez le premier groupe de travail de l'établissement."
          : "Vous n'êtes rattaché à aucun groupe pour l'instant.") +
        "</p></div></div>";
      return;
    }

    var cartes = groupes.map(function (g) {
      var bouton;
      if (g.estMembre) {
        bouton = '<button class="btn btn-ghost" type="button" data-action="quitter-groupe" data-id="' + g.id + '">Quitter</button>';
      } else {
        bouton = '<button class="btn btn-primary" type="button" data-action="rejoindre-groupe" data-id="' + g.id + '">Rejoindre</button>';
      }
      var supprimer = g.peutSupprimer
        ? '<button class="btn-icon danger" title="Supprimer le groupe" data-action="supprimer-groupe" data-id="' + g.id + '">🗑️</button>'
        : "";

      return (
        '<div class="card rg-carte">' +
        '  <div class="rg-entete">' +
        '    <span class="rg-ico">' + (ICONE_GROUPE[g.type] || "👥") + "</span>" +
        '    <div style="min-width:0">' +
        '      <div class="rg-nom">' + echapper(g.nom) + "</div>" +
        '      <div class="rp-meta">' +
        (g.classeNom ? '<span class="chip-plain">🏫 ' + echapper(g.classeNom) + "</span>" : "") +
        (g.matiereNom ? '<span class="chip-plain">📚 ' + echapper(g.matiereNom) + "</span>" : "") +
        "      </div>" +
        "    </div>" +
        "  </div>" +
        '  <div class="rg-desc">' + (g.description ? texteRiche(g.description) : "<em>Aucune description.</em>") + "</div>" +
        '  <div class="rg-pied">' + bouton +
        '    <span class="rg-effectif">👤 ' + (g.membres || 0) + "</span>" + supprimer +
        "  </div>" +
        "</div>"
      );
    }).join("");

    hote.innerHTML = '<div class="reseau-groupes-grille">' + cartes + "</div>";
  }

  function rendreGroupesCote() {
    var hote = el("reseauGroupesCote");
    if (!hote) return;
    var mes = groupes.filter(function (g) { return g.estMembre; });
    if (!mes.length) {
      hote.innerHTML = '<div class="text-soft" style="font-size:13px">Aucun groupe rejoint.</div>';
      return;
    }
    hote.innerHTML = mes.slice(0, 8).map(function (g) {
      return '<button class="rg-lien" type="button" data-action="fil-du-groupe" data-id="' + g.id + '">' +
        "<span>" + (ICONE_GROUPE[g.type] || "👥") + "</span>" +
        "<span>" + echapper(g.nom) + "</span>" +
        '<span class="rg-aide">' + (g.membres || 0) + "</span></button>";
    }).join("");
  }

  /* ============================================================
     Vue : BIBLIOTHÈQUE
     ============================================================ */

  function renduBibliotheque() {
    var hote = el("reseauVue");
    if (!hote) return;

    if (!ressources.length) {
      hote.innerHTML =
        '<div class="card reseau-vide"><div class="empty-state"><div class="e-ico">📚</div>' +
        "<h4>Bibliothèque vide</h4><p>Partagez un lien, un document ou une vidéo utile à l'établissement.</p></div></div>";
      return;
    }

    hote.innerHTML = ressources.map(function (r) {
      var supprimer = r.peutSupprimer
        ? '<button class="btn-icon danger" title="Retirer" data-action="supprimer-ressource" data-id="' + r.id + '">🗑️</button>'
        : "";
      return (
        '<div class="card res-bloc">' +
        '  <span class="res-ico">' + (ICONE_RESSOURCE[r.type] || "🔗") + "</span>" +
        '  <div class="res-corps">' +
        '    <div class="res-titre">' + echapper(r.titre) + "</div>" +
        (r.description ? '    <div class="res-desc">' + texteRiche(r.description) + "</div>" : "") +
        '    <div class="res-meta">' +
        (r.matiereNom ? '<span class="chip-plain">📚 ' + echapper(r.matiereNom) + "</span>" : "") +
        (r.niveau ? '<span class="chip-plain">' + echapper(r.niveau) + "</span>" : "") +
        "      <span>👤 " + echapper(r.auteurNom) + "</span>" +
        "      <span>🕒 " + echapper(tempsRelatif(r.creeLe)) + "</span>" +
        '      <a class="btn btn-ghost" style="padding:4px 10px;font-size:12.5px" href="' + echapper(r.url) + '" target="_blank" rel="noopener noreferrer">Ouvrir ↗</a>' +
        "    </div>" +
        "  </div>" + supprimer +
        "</div>"
      );
    }).join("");
  }

  /* ============================================================
     Vue : panneau d'activité
     ============================================================ */

  function renduResume() {
    var hote = el("reseauResume");
    if (!hote || !resume) return;
    var valeurs = [
      [resume.publications, "Publications"],
      [resume.groupes, "Groupes"],
      [resume.ressources, "Ressources"]
    ];
    hote.innerHTML = valeurs.map(function (v) {
      return '<div class="rq-item"><span class="rq-nombre">' + (v[0] == null ? "–" : v[0]) +
        '</span><span class="rq-libelle">' + v[1] + "</span></div>";
    }).join("");
  }

  /* ============================================================
     Sélecteurs (groupes / classes / matières)
     ============================================================ */

  function remplirSelecteursGroupes() {
    var selecteur = el("rcGroupe");
    if (selecteur) {
      var courant = selecteur.value;
      selecteur.innerHTML = '<option value="">🏫 Tout l\'établissement</option>' +
        groupes.map(function (g) {
          return '<option value="' + g.id + '">' + (ICONE_GROUPE[g.type] || "👥") + " " + echapper(g.nom) + "</option>";
        }).join("");
      selecteur.value = courant;
    }
  }

  function remplirSelecteursReferentiel() {
    var classes = SD.classes || [];
    var matieres = SD.matieres || [];

    var fgClasse = el("fgClasse");
    if (fgClasse) {
      fgClasse.innerHTML = '<option value="">— Aucune —</option>' + classes.map(function (c) {
        return '<option value="' + echapper(c.id) + '">' + echapper(c.nom || c.id) + "</option>";
      }).join("");
    }

    var optionsMatieres = matieres.map(function (m) {
      return '<option value="' + echapper(m.id) + '">' + echapper(m.nom || m.libelle || m.id) + "</option>";
    }).join("");

    var fgMatiere = el("fgMatiere");
    if (fgMatiere) fgMatiere.innerHTML = '<option value="">— Aucune —</option>' + optionsMatieres;

    var frMatiere = el("frMatiere");
    if (frMatiere) frMatiere.innerHTML = '<option value="">— Aucune —</option>' + optionsMatieres;
  }

  /* ============================================================
     Actions serveur
     ============================================================ */

  function apresEcriture(message) {
    if (message) SM.toast(message, "success");
    return chargerPublications().then(chargerResume);
  }

  function publier() {
    var contenu = el("rcContenu").value.trim();
    if (!contenu) { SM.toast("Écrivez d'abord votre message.", "error"); return; }

    var corps = {
      contenu: contenu,
      type: el("rcType").value,
      groupeId: el("rcGroupe").value || null
    };

    var bouton = el("btnPublier");
    bouton.disabled = true;
    API.reseauPublier(corps).then(function () {
      el("rcContenu").value = "";
      el("rcType").value = "publication";
      SM.toast("Publication ajoutée.", "success");
      return chargerPublications().then(function () {
        chargerResume();
        chargerGroupes();
      });
    }).catch(function (e) {
      SM.toast((e && e.message) || "Publication impossible.", "error");
    }).then(function () {
      bouton.disabled = false;
    });
  }

  function basculerJaime(id) {
    API.reseauJaime(id).then(function (r) {
      var p = trouverPublication(id);
      if (p) { p.jaime = r.jaime; p.jaimeCount = r.jaimeCount; }
      renduFil();
    }).catch(function (e) {
      SM.toast((e && e.message) || "Action impossible.", "error");
    });
  }

  function trouverPublication(id) {
    for (var i = 0; i < publications.length; i++) {
      if (publications[i].id === id) return publications[i];
    }
    return null;
  }

  function envoyerCommentaire(id) {
    var champ = el("cmt-" + id);
    if (!champ) return;
    var contenu = champ.value.trim();
    if (!contenu) { SM.toast("Le commentaire est vide.", "error"); return; }

    API.reseauCommenter(id, { contenu: contenu }).then(function () {
      commentairesOuverts[id] = true;
      return chargerPublications();
    }).catch(function (e) {
      SM.toast((e && e.message) || "Commentaire impossible.", "error");
    });
  }

  function enregistrerEdition(id) {
    var champ = el("edContenu-" + id);
    if (!champ) return;
    var contenu = champ.value.trim();
    if (!contenu) { SM.toast("Le message ne peut pas être vide.", "error"); return; }

    API.reseauModifierPublication(id, { contenu: contenu }).then(function () {
      modificationEnCours = null;
      SM.toast("Publication modifiée.", "success");
      return chargerPublications();
    }).catch(function (e) {
      SM.toast((e && e.message) || "Modification impossible.", "error");
    });
  }

  function modererPublication(id, corps, message) {
    API.reseauModifierPublication(id, corps).then(function () {
      SM.toast(message, "success");
      return chargerPublications();
    }).catch(function (e) {
      SM.toast((e && e.message) || "Action impossible.", "error");
    });
  }

  function confirmer(titre, texte, action) {
    el("supprTitre").textContent = titre;
    el("supprTexte").textContent = texte;
    supprAction = action;
    SM.openModal("modalSuppr");
  }

  function executerSuppression() {
    var action = supprAction;
    supprAction = null;
    SM.closeModal("modalSuppr");
    if (action) action();
  }

  function creerGroupe() {
    var nom = el("fgNom").value.trim();
    if (!nom) {
      el("fgNom").classList.add("invalid");
      el("errgNom").classList.add("show");
      SM.toast("Le nom du groupe est obligatoire.", "error");
      return;
    }
    var type = el("fgType").value;
    var corps = {
      nom: nom,
      type: type,
      description: el("fgDescription").value.trim(),
      classeId: type === "classe" ? (el("fgClasse").value || null) : null,
      matiereId: type === "matiere" ? (el("fgMatiere").value || null) : null
    };
    if (type === "classe" && !corps.classeId) {
      SM.toast("Choisissez la classe associée.", "error");
      return;
    }
    if (type === "matiere" && !corps.matiereId) {
      SM.toast("Choisissez la matière associée.", "error");
      return;
    }

    var bouton = el("btnCreerGroupe");
    bouton.disabled = true;
    API.reseauCreerGroupe(corps).then(function () {
      SM.closeModal("modalGroupe");
      el("fgNom").value = "";
      el("fgDescription").value = "";
      el("fgNom").classList.remove("invalid");
      el("errgNom").classList.remove("show");
      SM.toast("Groupe créé.", "success");
      return chargerGroupes().then(chargerResume);
    }).catch(function (e) {
      SM.toast((e && e.message) || "Création impossible.", "error");
    }).then(function () {
      bouton.disabled = false;
    });
  }

  function creerRessource() {
    var titre = el("frTitre").value.trim();
    var url = el("frUrl").value.trim();
    var ok = true;

    el("frTitre").classList.remove("invalid");
    el("errrTitre").classList.remove("show");
    el("frUrl").classList.remove("invalid");
    el("errrUrl").classList.remove("show");

    if (!titre) { el("frTitre").classList.add("invalid"); el("errrTitre").classList.add("show"); ok = false; }
    if (!/^https?:\/\//i.test(url)) { el("frUrl").classList.add("invalid"); el("errrUrl").classList.add("show"); ok = false; }
    if (!ok) { SM.toast("Vérifiez les champs obligatoires.", "error"); return; }

    var bouton = el("btnCreerRessource");
    bouton.disabled = true;
    API.reseauCreerRessource({
      titre: titre,
      url: url,
      type: el("frType").value,
      matiereId: el("frMatiere").value || null,
      description: el("frDescription").value.trim()
    }).then(function () {
      SM.closeModal("modalRessource");
      el("frTitre").value = "";
      el("frUrl").value = "";
      el("frDescription").value = "";
      SM.toast("Ressource partagée.", "success");
      switch (vue) {
        case "bibliotheque": return chargerRessources().then(chargerResume);
        default: return chargerPublications().then(chargerResume);
      }
    }).catch(function (e) {
      SM.toast((e && e.message) || "Partage impossible.", "error");
    }).then(function () {
      bouton.disabled = false;
    });
  }

  /* ============================================================
     Onglets et filtres
     ============================================================ */

  function definirVue(nouvelle) {
    vue = nouvelle;

    var onglets = el("reseauTabs").querySelectorAll(".tab");
    for (var i = 0; i < onglets.length; i++) {
      onglets[i].classList.toggle("active", onglets[i].getAttribute("data-vue") === vue);
    }

    // La barre d'outils du fil (recherche, « mes publications ») n'a pas de
    // sens sur les vues Groupes et Bibliothèque.
    var outils = el("reseauOutils");
    if (outils) outils.style.display = (vue === "groupes") ? "none" : "flex";

    // Le composeur reste utile partout sauf dans la bibliothèque, qui a sa
    // propre modale de partage.
    var compose = el("reseauCompose");
    if (compose) compose.style.display = (vue === "bibliotheque") ? "none" : "";

    if (vue === "groupes") { afficherChargement(); chargerGroupes(); return; }
    if (vue === "bibliotheque") { afficherChargement(); chargerRessources(); return; }
    chargerPublications();
  }

  function brancherOnglets() {
    el("reseauTabs").addEventListener("click", function (e) {
      var onglet = e.target.closest(".tab");
      if (onglet) definirVue(onglet.getAttribute("data-vue"));
    });
  }

  function brancherRecherche() {
    var champ = el("rcRecherche");
    if (champ) {
      champ.addEventListener("input", function () {
        var valeur = this.value.trim();
        if (minuteurRecherche) clearTimeout(minuteurRecherche);
        minuteurRecherche = setTimeout(function () {
          filtres.q = valeur;
          if (vue === "bibliotheque") chargerRessources(); else chargerPublications();
        }, 350);
      });
    }

    var cases = el("rcMesPublications");
    if (cases) {
      cases.addEventListener("change", function () {
        el("wrapMesPublications").classList.toggle("on", this.checked);
        filtres.auteur = this.checked ? "moi" : "";
        chargerPublications();
      });
    }

    var rafraichir = el("btnRafraichir");
    if (rafraichir) {
      rafraichir.addEventListener("click", function () {
        if (vue === "groupes") return chargerGroupes();
        if (vue === "bibliotheque") return chargerRessources().then(chargerResume);
        return chargerTout();
      });
    }
  }

  /* ============================================================
     Délégation de tous les clics sur la vue
     ============================================================ */

  function brancherActions() {
    var hote = el("reseauVue");

    hote.addEventListener("click", function (e) {
      var cible = e.target.closest("[data-action]");
      if (!cible) return;
      var action = cible.getAttribute("data-action");
      var id = parseInt(cible.getAttribute("data-id"), 10);

      switch (action) {
        case "jaime":
          basculerJaime(id);
          break;

        case "commentaires":
          commentairesOuverts[id] = !commentairesOuverts[id];
          renduFil();
          if (commentairesOuverts[id]) {
            var champ = el("cmt-" + id);
            if (champ) champ.focus();
          }
          break;

        case "envoyer-commentaire":
          envoyerCommentaire(id);
          break;

        case "supprimer-commentaire":
          confirmer("Supprimer ce commentaire ?", "Cette action est irréversible.", function () {
            API.reseauSupprimerCommentaire(id).then(function () {
              SM.toast("Commentaire supprimé.", "success");
              return chargerPublications();
            }).catch(function (err) {
              SM.toast((err && err.message) || "Suppression impossible.", "error");
            });
          });
          break;

        case "editer":
          modificationEnCours = id;
          renduFil();
          break;

        case "annuler-edition":
          modificationEnCours = null;
          renduFil();
          break;

        case "enregistrer-edition":
          enregistrerEdition(id);
          break;

        case "epingler":
          var p = trouverPublication(id);
          modererPublication(id, { epingle: !(p && p.epingle) },
            (p && p.epingle) ? "Publication désépinglée." : "Publication épinglée.");
          break;

        case "masquer":
          var q = trouverPublication(id);
          modererPublication(id, { masque: !(q && q.masque) },
            (q && q.masque) ? "Publication réaffichée." : "Publication masquée.");
          break;

        case "supprimer-publication":
          confirmer("Supprimer cette publication ?",
            "Le message et ses commentaires seront définitivement retirés du réseau.",
            function () {
              API.reseauSupprimerPublication(id).then(function () {
                SM.toast("Publication supprimée.", "success");
                return chargerPublications().then(chargerResume);
              }).catch(function (err) {
                SM.toast((err && err.message) || "Suppression impossible.", "error");
              });
            });
          break;

        case "rejoindre-groupe":
          API.reseauRejoindreGroupe(id).then(function () {
            SM.toast("Vous avez rejoint le groupe.", "success");
            return chargerGroupes().then(chargerResume);
          }).catch(function (err) {
            SM.toast((err && err.message) || "Action impossible.", "error");
          });
          break;

        case "quitter-groupe":
          confirmer("Quitter ce groupe ?", "Vous pourrez le rejoindre à nouveau plus tard.", function () {
            API.reseauQuitterGroupe(id).then(function () {
              SM.toast("Vous avez quitté le groupe.", "success");
              return chargerGroupes().then(chargerResume);
            }).catch(function (err) {
              SM.toast((err && err.message) || "Action impossible.", "error");
            });
          });
          break;

        case "supprimer-groupe":
          confirmer("Supprimer ce groupe ?",
            "Toutes les publications du groupe seront définitivement supprimées.",
            function () {
              API.reseauSupprimerGroupe(id).then(function () {
                SM.toast("Groupe supprimé.", "success");
                return chargerGroupes().then(chargerPublications).then(chargerResume);
              }).catch(function (err) {
                SM.toast((err && err.message) || "Suppression impossible.", "error");
              });
            });
          break;

        case "fil-du-groupe":
          el("rcGroupe").value = String(id);
          definirVue("fil");
          break;

        case "supprimer-ressource":
          confirmer("Retirer cette ressource ?", "Elle disparaîtra de la bibliothèque.", function () {
            API.reseauSupprimerRessource(id).then(function () {
              SM.toast("Ressource retirée.", "success");
              return chargerRessources().then(chargerResume);
            }).catch(function (err) {
              SM.toast((err && err.message) || "Suppression impossible.", "error");
            });
          });
          break;
      }
    });

    // Entrée dans un champ de commentaire = envoyer
    hote.addEventListener("keydown", function (e) {
      if (e.key !== "Enter") return;
      var champ = e.target;
      if (!champ.id) return;
      if (champ.id.indexOf("cmt-") === 0) {
        e.preventDefault();
        envoyerCommentaire(parseInt(champ.id.substring(4), 10));
      }
    });
  }

  /* ============================================================
     Démarrage
     ============================================================ */

  function initialiser() {
    // Le composeur n'a de sens que pour un profil autorisé à écrire.
    // Le serveur reste la seule autorité : il refuse de toute façon.
    if (!peutEcrire) {
      var compose = el("reseauCompose");
      if (compose) compose.style.display = "none";
      var boutons = document.querySelectorAll('[data-cap="reseau.ecrire"]');
      for (var i = 0; i < boutons.length; i++) boutons[i].style.display = "none";
    }

    var avatar = el("rcAvatar");
    if (avatar) avatar.innerHTML = SM.avatarHTML(moi.nom || "Moi");

    remplirSelecteursReferentiel();
    brancherOnglets();
    brancherRecherche();
    brancherActions();

    var publier_ = el("btnPublier");
    if (publier_) publier_.addEventListener("click", publier);
    var creerG = el("btnCreerGroupe");
    if (creerG) creerG.addEventListener("click", creerGroupe);
    var creerR = el("btnCreerRessource");
    if (creerR) creerR.addEventListener("click", creerRessource);
    var confirmerSuppr = el("btnConfirmerSuppr");
    if (confirmerSuppr) confirmerSuppr.addEventListener("click", executerSuppression);

    var typeGroupe = el("fgType");
    if (typeGroupe) {
      // Le formulaire ne propose que les types que ce compte peut réellement
      // créer : offrir « Matière » à un élève ne mènerait qu'à un refus.
      var autorises = typesGroupeAutorises();
      var gardees = Array.prototype.filter.call(typeGroupe.options, function (o) {
        return autorises.indexOf(o.value) !== -1;
      });
      typeGroupe.innerHTML = gardees.map(function (o) {
        return '<option value="' + o.value + '">' + echapper(o.textContent) + "</option>";
      }).join("");
      if (autorises.indexOf(typeGroupe.value) === -1) typeGroupe.value = "club";

      typeGroupe.addEventListener("change", function () {
        var v = this.value;
        var wrapClasse = el("wrapGClasse");
        var wrapMatiere = el("wrapGMatiere");
        if (wrapClasse) wrapClasse.style.display = (v === "classe") ? "" : "none";
        if (wrapMatiere) wrapMatiere.style.display = (v === "matiere") ? "" : "none";
      });
      // Valeurs initiales : seuls les champs pertinents sont proposés.
      var wrapClasse0 = el("wrapGClasse");
      var wrapMatiere0 = el("wrapGMatiere");
      if (wrapClasse0) wrapClasse0.style.display = "none";
      if (wrapMatiere0) wrapMatiere0.style.display = "none";
    }

    // Le bouton de modération n'apparaît pas pour les autres profils.
    if (!peutModerer) {
      // rien à masquer statiquement : le serveur ne renvoie `peutModerer`
      // que vrai pour la direction, donc les boutons ne sont pas générés.
    }

    chargerTout();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialiser);
  } else {
    initialiser();
  }
})();
