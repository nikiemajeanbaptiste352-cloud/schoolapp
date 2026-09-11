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
      if (html.indexOf("js/mobile-config.js") !== -1) continue; // déjà fait

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
const nbSurcharges = appliquerSurcharges();
const pages = injecterConfiguration();
const problemes = controler();

console.log("");
console.log("Contenu embarqué dans l'application :");
for (const ligne of rapport) {
  console.log(
    "  " + ligne.element.padEnd(12) + " " + mo(ligne.octets).padStart(9)
  );
}
console.log("");
console.log("  Surcharges mobiles appliquées : " + nbSurcharges + " fichier(s)");
console.log("  Pages configurées             : " + pages.length);
console.log("  Taille totale de l'application: " + mo(taille(WWW)));

if (problemes.length) {
  console.error("");
  console.error("ERREUR — éléments interdits dans l'application :");
  for (const p of problemes) console.error("  " + p);
  process.exit(1);
}

if (pages.length !== 18) {
  console.error("");
  console.error(
    "ERREUR — 18 pages attendues, " + pages.length + " configurée(s)."
  );
  process.exit(1);
}

console.log("");
console.log("OK — l'application ne contient aucune donnée ni aucun secret.");
