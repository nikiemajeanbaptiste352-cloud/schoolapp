/* ============================================================
   SchoolManager — Assemblage du contenu de l'application mobile
   ------------------------------------------------------------
   Fabrique mobile/www/ à partir du site web existant.

   RÈGLE ABSOLUE — liste blanche :
   seuls index.html, css/, js/, pages/ et assets/ entrent dans
   l'application. Tout le reste est exclu, en particulier :

     - backend/            (138 Mo, dont l'environnement Python)
     - .env.local          (secrets de configuration)
     - backend/data/*.db   (sauvegarde de la base de données)
     - supabase/, docs/, .git/, .vercel/

   L'application ne doit contenir AUCUNE donnée d'élève, aucun mot de
   passe et aucune clé : elle n'affiche que l'interface et interroge
   l'API distante.

   Deux écrans ne viennent PAS du site (dossier surcharges/) :

     - index.html : l'écran d'accueil de l'application (logo, connexion
       email / mot de passe). La page publique du site ne peut pas servir
       d'écran d'accueil : bandeau, photo, FAQ et pied de page font
       « site web », pas « application » ;
     - la page publique du site (index.html) est conservée sous le nom
       site.html : inscription établissement, code reçu par email et
       connexion Google restent accessibles depuis l'application.

   Usage :  node outils/assembler-www.js
   ============================================================ */

"use strict";

const fs = require("fs");
const path = require("path");

const MOBILE = path.resolve(__dirname, "..");
const RACINE = path.resolve(MOBILE, "..");
const WWW = path.join(MOBILE, "www");
const SURCHARGES = path.join(MOBILE, "surcharges");

/* Liste blanche */
const INCLUS = ["index.html", "css", "js", "pages", "assets"];

/* Écrans fournis par la version mobile, absents du site : ils s'ajoutent
   aux pages du site et doivent donc recevoir la configuration mobile eux
   aussi (js/mobile-config.js). */
const PAGES_MOBILE = ["index.html"];

/* Fichiers qui ne doivent JAMAIS se retrouver dans l'application */
const INTERDITS = [
  ".env",
  ".env.local",
  "backend",
  "supabase",
  "docs",
  ".git",
  ".vercel",
  "node_modules",
  "capacitor.config.json",
  "package.json"
];

function taille(chemin) {
  let total = 0;
  const stat = fs.statSync(chemin);
  if (stat.isFile()) return stat.size;
  for (const entree of fs.readdirSync(chemin)) {
    total += taille(path.join(chemin, entree));
  }
  return total;
}

function mo(octets) {
  return (octets / 1024 / 1024).toFixed(2) + " Mo";
}

function vider() {
  if (fs.existsSync(WWW)) fs.rmSync(WWW, { recursive: true, force: true });
  fs.mkdirSync(WWW, { recursive: true });
}

function copier() {
  const rapport = [];
  for (const element of INCLUS) {
    const source = path.join(RACINE, element);
    if (!fs.existsSync(source)) {
      throw new Error("Élément introuvable dans le site : " + element);
    }
    const cible = path.join(WWW, element);
    fs.cpSync(source, cible, { recursive: true });
    rapport.push({ element, octets: taille(cible) });
  }
  return rapport;
}

/**
 * La page publique du site devient « site.html » dans l'application :
 * l'écran d'accueil de l'application (surcharges/index.html) prend sa place.
 * Les liens de cette page sont relatifs à la racine : ils restent valides.
 */
function preparerSite() {
  const source = path.join(WWW, "index.html");
  if (!fs.existsSync(source)) return false;
  fs.renameSync(source, path.join(WWW, "site.html"));
  return true;
}

/**
 * Nombre de pages HTML du site (index.html + pages/*.html). Sert de
 * garde-fou : TOUTES les pages du site doivent avoir reçu la configuration
 * mobile. Le nombre est calculé — une page ajoutée au site ne doit pas
 * casser l'assemblage (c'est arrivé avec pages/vie-scolaire.html).
 */
function compterPagesSite() {
  let n = 0;
  if (fs.existsSync(path.join(RACINE, "index.html"))) n += 1;
  const dossier = path.join(RACINE, "pages");
  if (fs.existsSync(dossier)) {
    for (const entree of fs.readdirSync(dossier)) {
      if (entree.endsWith(".html")) n += 1;
    }
  }
  return n;
}

function appliquerSurcharges() {
  if (!fs.existsSync(SURCHARGES)) return 0;
  let n = 0;
  const parcourir = (dossier, relatif) => {
    for (const entree of fs.readdirSync(dossier)) {
      const src = path.join(dossier, entree);
      const rel = path.join(relatif, entree);
      const dest = path.join(WWW, rel);
      if (fs.statSync(src).isDirectory()) {
        parcourir(src, rel);
      } else {
        fs.mkdirSync(path.dirname(dest), { recursive: true });
        fs.copyFileSync(src, dest);
        n++;
      }
    }
  };
  parcourir(SURCHARGES, "");
  return n;
}

/**
 * Insère <script src=".../js/mobile-config.js"> juste AVANT js/api.js,
 * car api.js lit window.SM_API_BASE au chargement.
 * Les pages concernées utilisent soit "js/api.js", soit "../js/api.js".
 */
function injecterConfiguration() {
  const pages = [];
  const parcourir = (dossier) => {
    for (const entree of fs.readdirSync(dossier)) {
      const complet = path.join(dossier, entree);
      if (fs.statSync(complet).isDirectory()) {
        parcourir(complet);
        continue;
      }
      if (!entree.endsWith(".html")) continue;

      let html = fs.readFileSync(complet, "utf8");
      // Déjà configurée ? On cherche la BALISE, pas le simple nom : un
      // commentaire expliquant mobile-config.js ne doit pas faire croire que
      // la page est déjà équipée.
      if (/<script[^>]*src="[^"]*js\/mobile-config\.js"/.test(html)) continue;

      // Cas normal : la page charge js/api.js → la configuration doit
      // passer juste AVANT, puisque api.js lit window.SM_API_BASE.
      const motif = /<script[^>]*src="([^"]*js\/api\.js)"[^>]*>\s*<\/script>/;
      const trouve = html.match(motif);
      if (trouve) {
        const prefixe = trouve[1].replace(/js\/api\.js$/, "");
        const balise =
          '<script src="' + prefixe + 'js/mobile-config.js"></script>\n  ' + trouve[0];
        html = html.replace(motif, balise);
      } else {
        // Page autonome (ex. pages/oauth-callback.html, qui écrit
        // directement la session sans passer par api.js) : la
        // configuration est placée en tout premier dans <head>.
        const entete = html.match(/<head[^>]*>/);
        if (!entete) {
          throw new Error(
            "Page sans js/api.js ni <head> : " +
              path.relative(RACINE, complet)
          );
        }
        const isole = path.relative(WWW, complet).replace(/\\/g, "/");
        const profondeur = isole.split("/").length - 1;
        const prefixe = profondeur > 0 ? "../".repeat(profondeur) : "";
        const balise =
          entete[0] +
          '\n  <script src="' + prefixe + 'js/mobile-config.js"></script>';
        html = html.replace(entete[0], balise);
      }
      fs.writeFileSync(complet, html, "utf8");
      pages.push(path.relative(WWW, complet).replace(/\\/g, "/"));
    }
  };
  parcourir(WWW);
  return pages;
}

function controler() {
  const problemes = [];
  const parcourir = (dossier) => {
    for (const entree of fs.readdirSync(dossier)) {
      const complet = path.join(dossier, entree);
      const relatif = path.relative(WWW, complet).replace(/\\/g, "/");
      if (INTERDITS.indexOf(entree) !== -1 || relatif.startsWith("backend/")) {
        problemes.push(relatif);
      }
      if (fs.statSync(complet).isDirectory()) parcourir(complet);
    }
  };
  parcourir(WWW);
  return problemes;
}

/* ---------- Exécution ---------- */
console.log("Assemblage de l'application depuis : " + RACINE);
vider();

const rapport = copier();
const pageSiteRangee = preparerSite();
const nbSurcharges = appliquerSurcharges();
const pages = injecterConfiguration();
const problemes = controler();

/* Pages attendues : toutes celles du site + les écrans de l'application. */
const pagesSite = compterPagesSite();
const pagesAttendues = pagesSite + PAGES_MOBILE.length;

console.log("");
console.log("Contenu embarqué dans l'application :");
for (const ligne of rapport) {
  console.log(
    "  " + ligne.element.padEnd(12) + " " + mo(ligne.octets).padStart(9)
  );
}
console.log("");
console.log("  Surcharges mobiles appliquées : " + nbSurcharges + " fichier(s)");
console.log(
  "  Page publique du site         : " +
    (pageSiteRangee ? "conservée sous site.html" : "INTROUVABLE")
);
console.log(
  "  Pages configurées             : " +
    pages.length +
    " (" +
    pagesSite +
    " du site + écran d'accueil)"
);
console.log("  Taille totale de l'application: " + mo(taille(WWW)));

if (problemes.length) {
  console.error("");
  console.error("ERREUR — éléments interdits dans l'application :");
  for (const p of problemes) console.error("  " + p);
  process.exit(1);
}

if (pages.length !== pagesAttendues) {
  console.error("");
  console.error(
    "ERREUR — " +
      pagesAttendues +
      " pages attendues (" +
      pagesSite +
      " du site + " +
      PAGES_MOBILE.length +
      " écran d'accueil mobile), " +
      pages.length +
      " configurée(s)."
  );
  process.exit(1);
}

console.log("");
console.log("OK — l'application ne contient aucune donnée ni aucun secret.");
