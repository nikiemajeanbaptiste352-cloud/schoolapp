/* ============================================================
   SchoolManager — Création de la clé de signature Android
   ------------------------------------------------------------
   ⚠️  À LIRE UNE FOIS DANS SA VIE  ⚠️

   La clé de signature prouve que les mises à jour d'une application
   viennent bien du même éditeur. Si cette clé est PERDUE, il devient
   IMPOSSIBLE de mettre à jour l'application déjà publiée sur Google
   Play : il faudrait publier une application entièrement nouvelle,
   sous un autre identifiant, et tous les utilisateurs devraient la
   réinstaller.

   Ce script :

     1. tire au hasard un mot de passe long (jamais affiché, jamais
        transmis : il n'existe que sur ce disque) ;
     2. crée la clé de signature (android/keystore/schoolmanager.jks) ;
     3. écrit les identifiants dans android/key.properties, que Gradle
        lit pour signer la version de publication (fichier non versionné) ;
     4. dépose une copie de sauvegarde complète dans
        Documents\SchoolManager-SIGNATURE — À CONSERVER EN DEUX ENDROITS
        DIFFÉRENTS (par exemple clé USB + espace de stockage en ligne) ;
     5. vérifie la clé et affiche son empreinte (utile à Google Play).

   Usage :  node outils/creer-cle-signature.js
   ============================================================ */

"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const crypto = require("crypto");
const { execFileSync, spawnSync } = require("child_process");

const MOBILE = path.resolve(__dirname, "..");
const ANDROID = path.join(MOBILE, "android");
const JDK = "C:\\Users\\USER\\AndroidToolchain\\jdk";
const KEYTOOL = path.join(JDK, "bin", "keytool.exe");

const DOSSIER_CLE = path.join(ANDROID, "keystore");
const FICHIER_CLE = path.join(DOSSIER_CLE, "schoolmanager.jks");
const FICHIER_PROPS = path.join(ANDROID, "key.properties");
const SAUVEGARDE = path.join(os.homedir(), "Documents", "SchoolManager-SIGNATURE");

const ALIAS = "schoolmanager";
const VALIDITE_JOURS = 10000; // ≈ 27 ans
const DN = "CN=SchoolManager, OU=Mobile, O=SchoolManager, C=CM";

/* Le mot de passe ne comporte volontairement pas de caractères qui posent
   problème en ligne de commande ou dans un fichier de propriétés Java
   (ni « = », ni « : », ni « \ », ni guillemet, ni espace). */
const ALPHABET =
  "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#%*+-?";
function tirerMotDePasse(longueur) {
  const octets = crypto.randomBytes(longueur * 2);
  let sortie = "";
  for (let i = 0; sortie.length < longueur; i += 2) {
    const valeur = (octets[i] << 8) | octets[i + 1];
    const c = ALPHABET[valeur % ALPHABET.length];
    // On évite un caractère répété à l'identique : sans intérêt pour la
    // solidité, mais cela facilite la recopie manuelle si besoin.
    if (c !== sortie[sortie.length - 1]) sortie += c;
  }
  return sortie;
}

function creerCle(motDePasse) {
  // Le mot de passe est fourni par un fichier temporaire : il n'apparaît
  // donc jamais dans la liste des commandes du système.
  const temporaire = path.join(os.tmpdir(), "sm-pw-" + crypto.randomBytes(8).toString("hex") + ".txt");
  fs.writeFileSync(temporaire, motDePasse, { encoding: "utf8", mode: 0o600 });
  try {
    const args = [
      "-genkeypair", "-v",
      "-keystore", FICHIER_CLE,
      "-alias", ALIAS,
      "-keyalg", "RSA",
      "-keysize", "4096",
      "-validity", String(VALIDITE_JOURS),
      "-storetype", "PKCS12",
      "-dname", DN,
      "-storepass:file", temporaire,
      "-keypass:file", temporaire
    ];
    const r = spawnSync(KEYTOOL, args, { encoding: "utf8" });
    if (r.status === 0) return { ok: true };

    // Repli : certaines versions de keytool n'acceptent pas « :file ».
    // On fournit alors le mot de passe par l'entrée standard.
    const r2 = spawnSync(KEYTOOL, args.slice(0, -4), {
      encoding: "utf8",
      input: motDePasse + "\n" + motDePasse + "\n" + motDePasse + "\n"
    });
    if (r2.status === 0) return { ok: true };
    return {
      ok: false,
      message: (r2.stderr || r2.stdout || r.stderr || r.stdout || "").slice(-600)
    };
  } finally {
    try { fs.rmSync(temporaire, { force: true }); } catch (e) { /* sans effet */ }
  }
}

function lireEmpreinte(motDePasse) {
  const temporaire = path.join(os.tmpdir(), "sm-pw2-" + crypto.randomBytes(8).toString("hex") + ".txt");
  fs.writeFileSync(temporaire, motDePasse, { encoding: "utf8", mode: 0o600 });
  try {
    const r = spawnSync(
      KEYTOOL,
      ["-list", "-v", "-keystore", FICHIER_CLE, "-alias", ALIAS, "-storepass:file", temporaire],
      { encoding: "utf8" }
    );
    let texte = (r.stdout || "") + (r.stderr || "");
    if (r.status !== 0) {
      const r2 = spawnSync(KEYTOOL, ["-list", "-v", "-keystore", FICHIER_CLE, "-alias", ALIAS], {
        encoding: "utf8",
        input: motDePasse + "\n"
      });
      texte = (r2.stdout || "") + (r2.stderr || "");
    }
    const sha = texte.match(/SHA256:\s*([0-9A-F:]+)/i);
    const sha1 = texte.match(/SHA1:\s*([0-9A-F:]+)/i);
    return {
      sha256: sha ? sha[1].trim() : "(non lue)",
      sha1: sha1 ? sha1[1].trim() : "(non lue)"
    };
  } finally {
    try { fs.rmSync(temporaire, { force: true }); } catch (e) { /* sans effet */ }
  }
}

(function principal() {
  console.log("=== Clé de signature SchoolManager ===");
  console.log("");

  if (fs.existsSync(FICHIER_CLE) && fs.existsSync(FICHIER_PROPS)) {
    console.log("Une clé de signature existe déjà :");
    console.log("  " + FICHIER_CLE);
    console.log("");
    console.log("Rien n'a été modifié. Pour la remplacer volontairement,");
    console.log("supprimez ce fichier ainsi que android/key.properties,");
    console.log("puis relancez ce script.");
    return;
  }

  if (!fs.existsSync(KEYTOOL)) {
    console.error("keytool introuvable : " + KEYTOOL);
    process.exit(1);
  }

  fs.mkdirSync(DOSSIER_CLE, { recursive: true });

  const motDePasse = tirerMotDePasse(34);
  console.log("Création de la clé (RSA 4096 bits, valable " + Math.round(VALIDITE_JOURS / 365) + " ans)…");
  const resultat = creerCle(motDePasse);
  if (!resultat.ok) {
    console.error("Échec de la création de la clé.");
    console.error(resultat.message);
    process.exit(1);
  }

  /* ---------- Gradle ---------- */
  const cheminGradle = FICHIER_CLE.replace(/\\/g, "/");
  fs.writeFileSync(
    FICHIER_PROPS,
    [
      "# Identifiants de signature — FICHIER CONFIDENTIEL, NON VERSIONNÉ",
      "# Généré par mobile/outils/creer-cle-signature.js",
      "storeFile=" + cheminGradle,
      "storePassword=" + motDePasse,
      "keyAlias=" + ALIAS,
      "keyPassword=" + motDePasse,
      ""
    ].join("\n"),
    "utf8"
  );

  /* ---------- Sauvegarde hors dépôt ---------- */
  fs.mkdirSync(SAUVEGARDE, { recursive: true });
  fs.copyFileSync(FICHIER_CLE, path.join(SAUVEGARDE, "schoolmanager.jks"));
  const empreinte = lireEmpreinte(motDePasse);
  fs.writeFileSync(
    path.join(SAUVEGARDE, "IDENTIFIANTS-SIGNATURE.txt"),
    [
      "SchoolManager — identifiants de signature de l'application Android",
      "===================================================================",
      "",
      "  Fichier de la clé : schoolmanager.jks",
      "  Alias             : " + ALIAS,
      "  Mot de passe      : " + motDePasse,
      "  Empreinte SHA-256 : " + empreinte.sha256,
      "  Empreinte SHA-1   : " + empreinte.sha1,
      "",
      "-------------------------------------------------------------------",
      "A CONSERVER EN DEUX ENDROITS DIFFERENTS (cle USB + stockage en ligne).",
      "",
      "Si ce mot de passe ou ce fichier est perdu, il devient IMPOSSIBLE",
      "de publier une mise a jour de l'application sur Google Play.",
      "",
      "Ce fichier ne doit JAMAIS etre envoye par messagerie, ni depose",
      "sur GitHub, ni transmis a qui que ce soit.",
      "-------------------------------------------------------------------",
      ""
    ].join("\n"),
    "utf8"
  );

  console.log("");
  console.log("Clé créée et vérifiée.");
  console.log("  clé          : " + FICHIER_CLE);
  console.log("  Gradle       : " + FICHIER_PROPS + "  (non versionné)");
  console.log("  sauvegarde   : " + SAUVEGARDE);
  console.log("  alias        : " + ALIAS);
  console.log("  SHA-256      : " + empreinte.sha256);
  console.log("");
  console.log("Le mot de passe a été tiré au hasard et n'est affiché nulle part :");
  console.log("il se trouve uniquement dans les deux fichiers ci-dessus.");
  console.log("");
  console.log("=> Copiez le dossier « SchoolManager-SIGNATURE » sur une clé USB.");
  console.log("   Sans lui, aucune mise à jour ne sera plus possible.");
})()

