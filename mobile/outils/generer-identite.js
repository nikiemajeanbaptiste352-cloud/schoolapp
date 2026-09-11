/* ============================================================
   SchoolManager — Génération de l'identité visuelle de l'application
   ------------------------------------------------------------
   Fabrique les images sources attendues par @capacitor/assets à
   partir de assets/logo.svg (le logo du site) :

     mobile/assets/icon-only.png         icône complète (repli)
     mobile/assets/icon-foreground.png   avant-plan de l'icône adaptative
     mobile/assets/icon-background.png   fond de l'icône adaptative
     mobile/assets/splash.png            écran de démarrage
     mobile/assets/splash-dark.png       écran de démarrage (thème sombre)

   Couleurs reprises du logo : dégradé #1e4c8f → #2563eb.

   Usage :  node outils/generer-identite.js
   ============================================================ */

"use strict";

const fs = require("fs");
const path = require("path");
const sharp = require("sharp");

const MOBILE = path.resolve(__dirname, "..");
const DEST = path.join(MOBILE, "assets");
const COULEUR_HAUT = "#1e4c8f";
const COULEUR_BAS = "#2563eb";

if (!fs.existsSync(DEST)) fs.mkdirSync(DEST, { recursive: true });

/* ---------- Le bâtiment, extrait de assets/logo.svg ---------- */
function batiment() {
  return `
    <path d="M64 26 L26 52 v42 a4 4 0 0 0 4 4 h68 a4 4 0 0 0 4 -4 V52 Z" fill="#ffffff" opacity="0.96"/>
    <path d="M52 98 V72 h24 v26" fill="none" stroke="#12315f" stroke-width="5"/>
    <path d="M26 52 L64 30 L102 52" fill="none" stroke="#12315f" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>
    <rect x="86" y="70" width="14" height="10" rx="2" fill="#60a5fa"/>
    <rect x="86" y="84" width="14" height="10" rx="2" fill="#60a5fa"/>`;
}

/* Le bâtiment occupe la zone centrale : 26..102 en largeur, 26..98 en hauteur. */
const CX = 64;   // centre horizontal du bâtiment
const CY = 62;   // centre vertical du bâtiment

/** Bâtiment seul, centré sur un carré de `taille`, occupant `part` de la largeur. */
function svgBatiment(taille, part) {
  const s = (taille * part) / 76; // 76 = largeur du bâtiment dans son repère
  const tx = taille / 2 - CX * s;
  const ty = taille / 2 - CY * s;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${taille}" height="${taille}" viewBox="0 0 ${taille} ${taille}">
  <g transform="translate(${tx} ${ty}) scale(${s})">${batiment()}
  </g>
</svg>`;
}

/** Fond dégradé plein. */
function svgFond(taille) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${taille}" height="${taille}" viewBox="0 0 ${taille} ${taille}">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="${COULEUR_HAUT}"/>
      <stop offset="1" stop-color="${COULEUR_BAS}"/>
    </linearGradient>
  </defs>
  <rect width="${taille}" height="${taille}" fill="url(#g)"/>
</svg>`;
}

/** Icône complète : carré arrondi dégradé + bâtiment (repli pour anciens Android). */
function svgIconeComplete(taille) {
  const r = Math.round(taille * 0.22);
  const s = (taille * 0.62) / 76;
  const tx = taille / 2 - CX * s;
  const ty = taille / 2 - CY * s;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${taille}" height="${taille}" viewBox="0 0 ${taille} ${taille}">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="${COULEUR_HAUT}"/>
      <stop offset="1" stop-color="${COULEUR_BAS}"/>
    </linearGradient>
  </defs>
  <rect width="${taille}" height="${taille}" rx="${r}" ry="${r}" fill="url(#g)"/>
  <g transform="translate(${tx} ${ty}) scale(${s})">${batiment()}
  </g>
</svg>`;
}

/** Écran de démarrage : fond dégradé plein + logo centré. */
function svgDemarrage(taille, part) {
  const s = (taille * part) / 76;
  const tx = taille / 2 - CX * s;
  const ty = taille / 2 - CY * s;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${taille}" height="${taille}" viewBox="0 0 ${taille} ${taille}">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="${COULEUR_HAUT}"/>
      <stop offset="1" stop-color="${COULEUR_BAS}"/>
    </linearGradient>
  </defs>
  <rect width="${taille}" height="${taille}" fill="url(#g)"/>
  <g transform="translate(${tx} ${ty}) scale(${s})">${batiment()}
  </g>
</svg>`;
}

/* ---------- Rendu ---------- */
async function rendre(svg, nom, taille) {
  const cible = path.join(DEST, nom);
  // Pas d'option « density » : l'image est redimensionnée à la taille exacte
  // demandée, ce qui évite les surprises d'échelle d'un SVG à l'autre.
  await sharp(Buffer.from(svg))
    .resize(taille, taille, { fit: "fill" })
    .png()
    .toFile(cible);
  const m = await sharp(cible).metadata();
  const ko = (fs.statSync(cible).size / 1024).toFixed(1);
  if (m.width !== taille || m.height !== taille) {
    throw new Error(nom + " : " + m.width + "x" + m.height + " au lieu de " + taille);
  }
  console.log("  " + nom.padEnd(26) + m.width + "x" + m.height + "  " + ko + " Ko");
}

(async () => {
  console.log("Génération de l'identité visuelle :");
  await rendre(svgIconeComplete(1024), "icon-only.png", 1024);
  await rendre(svgBatiment(1024, 0.60), "icon-foreground.png", 1024);
  await rendre(svgFond(1024), "icon-background.png", 1024);
  await rendre(svgDemarrage(2732, 0.20), "splash.png", 2732);
  await rendre(svgDemarrage(2732, 0.20), "splash-dark.png", 2732);
  console.log("");
  console.log("Terminé. Lancer ensuite :  npx @capacitor/assets generate --android");
})().catch((e) => {
  console.error("ERREUR : " + e.message);
  process.exit(1);
});
