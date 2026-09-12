# SchoolManager — Application mobile Android

Cette documentation décrit l'application Android installable qui embarque l'interface
web de SchoolManager. Elle s'adresse à la personne qui devra **reconstruire**,
**mettre à jour** ou **publier** l'application.

---

## 1. Principe

L'application mobile ne réécrit pas l'interface. Elle **embarque les mêmes fichiers
HTML, CSS et JavaScript** que le site, et les affiche dans une vue interne (WebView)
fournie par [Capacitor](https://capacitorjs.com/). Seuls deux écrans changent, et
uniquement à l'intérieur de l'application : son écran d'accueil et son accès à la page
publique du site (voir § 7).

Conséquence directe : **toute correction faite sur le site ne s'applique pas
automatiquement à l'application déjà installée**. Pour qu'un correctif visuel apparaisse,
il faut reconstruire et republier une nouvelle version de l'application.

En revanche, **les données, les comptes et les calculs ne sont jamais dans
l'application** : elle interroge le serveur en direct. Un changement de tarif, un
nouvel élève ou une correction de note est donc visible immédiatement, sans
mise à jour de l'application.

```
   Application Android (mobile/)              Serveur (Vercel)
   ┌──────────────────────────┐              ┌─────────────────────────┐
   │  WebView                 │  HTTPS       │  FastAPI (asgi.py)      │
   │  index.html + css + js   │ ───────────► │  /api/v1/...            │
   │  (copie fidèle du site)  │              │                         │
   └──────────────────────────┘              └───────────┬─────────────┘
                                                         │
                                                ┌────────▼─────────┐
                                                │ Base de données   │
                                                └───────────────────┘
```

---

## 2. Où se trouve quoi

| Élément | Emplacement | Versionné ? |
|---|---|---|
| Projet mobile | `mobile/` | oui |
| Configuration Capacitor | `mobile/capacitor.config.json` | oui |
| Adaptations mobiles | `mobile/surcharges/js/mobile-config.js` | oui |
| Écran d'accueil de l'application | `mobile/surcharges/index.html` | oui |
| Script d'assemblage | `mobile/outils/assembler-www.js` | oui |
| Script d'identité (icônes) | `mobile/outils/generer-identite.js` | oui |
| Script de signature | `mobile/outils/creer-cle-signature.js` | oui |
| Site assemblé pour l'app | `mobile/www/` | non (reconstruit) |
| Projet Android | `mobile/android/` | oui (sauf compilations) |
| **Clé de signature** | `mobile/android/keystore/schoolmanager.jks` | **non — confidentiel** |
| **Mot de passe de la clé** | `mobile/android/key.properties` | **non — confidentiel** |
| Copie de sauvegarde de la clé | `Documents\SchoolManager-SIGNATURE\` | **hors dépôt** |
| Paquet à publier (`.aab`) | `Documents\schoolapp-mobile\SchoolManager-1.1.aab` | non |
| Fichier à installer (`.apk`) | `Documents\schoolapp-mobile\SchoolManager-1.1.apk` | non |

> ⚠️ `supabase/`, `backend/`, `docs/` et tout fichier `.env` sont **volontairement exclus**
> de l'application. Le script `assembler-www.js` vérifie cette exclusion et s'arrête
> en erreur s'il en détecte un seul.

---

## 3. Identité de l'application

| Champ | Valeur |
|---|---|
| Nom affiché | SchoolManager |
| Identifiant (paquet) | `com.schoolapp.mobile` |
| Code de version | `2` |
| Nom de version | `1.1` |
| Android minimal | 7.0 (niveau d'API 24) |
| Android ciblé | API 36 (Android 16) |
| Alias de signature | `schoolmanager` |
| Empreinte SHA-256 | `8D:C5:70:D4:69:95:0D:FB:0C:98:10:B0:D0:E3:6E:A5:CC:77:2D:8B:89:21:F5:DA:E1:A3:36:9A:F1:65:3C:09` |

Ces valeurs se modifient à deux endroits :

* le nom et l'identifiant dans `mobile/capacitor.config.json` ;
* les numéros de version dans `mobile/android/app/build.gradle`
  (`versionCode` et `versionName` dans `defaultConfig`).

---

## 4. Prérequis de compilation (déjà installés sur ce poste)

| Outil | Emplacement |
|---|---|
| Java 21 (Temurin) | `C:\Users\USER\AndroidToolchain\jdk` |
| SDK Android | `C:\Users\USER\AndroidToolchain\sdk` |
| Plateforme | `sdk\platforms\android-36` |
| Outils de compilation | `sdk\build-tools\36.0.0` |
| Node.js | `C:\Program Files\nodejs` |

Aucun droit administrateur n'est nécessaire : tout est installé dans le dossier
personnel de l'utilisateur.

---

## 5. Reconstruire l'application

Les quatre étapes se lancent **depuis le dossier `mobile/`**.

```powershell
cd "C:\Users\USER\SCHOOL AP\mobile"
```

### Étape 1 — Assembler le site dans l'application

```powershell
npm run www
```

Copie `index.html`, `css/`, `js/`, `pages/` et `assets/` dans `mobile/www/`, puis
applique les adaptations mobiles. La commande doit finir par :

```
  Surcharges mobiles appliquées : 2 fichier(s)
  Page publique du site         : conservée sous site.html
  Pages configurées             : 20 (19 du site + écran d'accueil)
  Taille totale de l'application: 0.81 Mo
OK — l'application ne contient aucune donnée ni aucun secret.
```

### Étape 2 — Transférer vers le projet Android

```powershell
npm run sync
```

(Équivaut à `npm run www` suivi de `npx cap sync android`.)

### Étape 3 — Compiler

```powershell
npm run aab           # paquet .aab, pour Google Play
npm run apk-release   # .apk signé, pour installer directement sur un téléphone
npm run apk           # .apk de test (plus rapide, non signé pour la publication)
```

Les fichiers produits :

```
mobile/android/app/build/outputs/bundle/release/app-release.aab
mobile/android/app/build/outputs/apk/release/app-release.apk
```

### Étape 4 — Vérifier

```powershell
# Signature du fichier installable
& "$env:USERPROFILE\AndroidToolchain\sdk\build-tools\36.0.0\apksigner.bat" verify --print-certs `
  "mobile\android\app\build\outputs\apk\release\app-release.apk"

# Identité de l'application
& "$env:USERPROFILE\AndroidToolchain\sdk\build-tools\36.0.0\aapt2.exe" dump badging `
  "mobile\android\app\build\outputs\apk\release\app-release.apk"
```

### Icônes et écran de démarrage

Générés depuis `mobile/assets/*.png`, eux-mêmes produits à partir de `assets/logo.svg`
par `mobile/outils/generer-identite.js`.

```powershell
node outils/generer-identite.js                              # recrée les 5 images sources
node node_modules/@capacitor/assets/bin/capacitor-assets generate --android   # les décline
npm run sync
```

---

## 6. Signature : la règle à ne jamais enfreindre

**La clé de signature prouve que les mises à jour viennent bien du même éditeur.**

* Android refuse d'installer une mise à jour signée avec une clé différente.
* Google Play refuse de recevoir une mise à jour signée avec une clé différente
  (sauf procédure de réinitialisation, lourde et encadrée).

Si la clé ou son mot de passe est perdu, **il devient impossible de mettre à jour
l'application déjà publiée**. Il faut publier une application entièrement nouvelle,
sous un autre identifiant, et tous les utilisateurs doivent la réinstaller.

### Ce qu'il faut faire

1. Le dossier `C:\Users\USER\Documents\SchoolManager-SIGNATURE\` contient
   `schoolmanager.jks` et `IDENTIFIANTS-SIGNATURE.txt`.
2. **Copiez ce dossier sur une clé USB et dans un espace de stockage en ligne privé.**
3. Ne l'envoyez jamais par messagerie, ne le déposez jamais sur GitHub.
4. Ne régénérez **jamais** la clé, même si vous reconstruisez le projet ailleurs :
   recopiez les fichiers existants.

Le mot de passe a été tiré au hasard par le script `outils/creer-cle-signature.js`.
Il n'a jamais été affiché : il n'existe que dans les deux fichiers ci-dessus.

### Comment Gradle signe

`mobile/android/key.properties` (non versionné) contient le chemin de la clé, l'alias et
les deux mots de passe. `mobile/android/app/build.gradle` lit ce fichier et l'applique
uniquement à la version de publication. **Si le fichier est absent, la compilation
fonctionne toujours mais produit un paquet non signé** : c'est le comportement voulu,
pour qu'un autre développeur puisse compiler sans posséder la clé.

---

## 7. Différences entre le site et l'application

Deux écrans sont propres à l'application. Ils vivent dans `mobile/surcharges/` et ne
remplacent les fichiers du site **qu'à l'intérieur de `mobile/www/`** : le site publié
sur Vercel n'est jamais touché.

| Écran | Fichier | Rôle |
|---|---|---|
| Écran d'accueil | `mobile/surcharges/index.html` | Remplace `www/index.html`. C'est le premier écran de l'application : logo, nom, formulaire de connexion, état du serveur. Aucun menu de site, aucun défilement de page, aucune photo de présentation. |
| Page publique | `www/site.html` | L'ancienne page d'accueil du site, conservée sous ce nom et atteignable par le lien **« Autres accès »** de l'écran d'accueil. Elle sert aux inscriptions et aux connexions Google ou par code. |

Les autres adaptations sont regroupées dans `mobile/surcharges/js/mobile-config.js`,
injecté automatiquement dans chaque page par l'assembleur. **Aucun fichier du site
lui-même n'a été modifié pour l'application, à une exception près** (`js/live.js`,
voir plus bas).

| Adaptation | Pourquoi |
|---|---|
| L'adresse du serveur est fixée explicitement | Dans l'application, les pages ne sont plus servies par le serveur : elles sont locales. Les chemins relatifs ne peuvent plus fonctionner. |
| `sessionStorage` est redirigé vers `localStorage` | Sur mobile, « session » signifie « tant que l'application n'est pas tuée ». La session aurait été perdue à chaque fermeture. Ce détour la conserve, sans toucher aux fichiers du site. |
| L'écran de démarrage est masqué dès que la page est prête | Sinon l'image de démarrage resterait affichée pendant que la page charge. |

`js/live.js` a reçu deux corrections utiles à l'application : un appel à
`window.SM_MASQUER_DEMARRAGE` lorsque la page est affichée (sans effet sur le site, où
cette fonction n'existe pas), et l'effacement de `sm_session` en même temps qu'un jeton
invalide — sans quoi l'application renvoyait sans fin de l'écran de connexion au
tableau de bord, puis du tableau de bord à l'écran de connexion.

### Conséquence à connaître

L'application ne fonctionne **que si le serveur est joignable**. Elle ne conserve pas de
copie des données. En l'absence de réseau, une page « service momentanément indisponible »
s'affiche.

### Changer l'adresse du serveur

L'adresse est écrite une seule fois, dans `mobile/surcharges/js/mobile-config.js` :

```js
window.SM_API_BASE = "https://schoolapp-flame-six.vercel.app/api/v1";
```

Il suffit de la modifier, puis de relancer les étapes 1 à 3 pour produire une version
mobile pointant vers un autre serveur.

---

## 8. Ce qui entre et ce qui n'entre pas dans l'application

**Entre :** `index.html`, `css/`, `js/`, `pages/`, `assets/`.

**N'entre pas :** `backend/`, `supabase/`, `docs/`, `tests/`, `.env`, la base de données,
`node_modules/`, ainsi que tout identifiant ou mot de passe.

Le script d'assemblage vérifie cette règle à chaque exécution et interrompt la
construction si un élément interdit est détecté.

---

## 9. Publier sur Google Play

### Ce qui ne peut être fait que par vous

Ces étapes engagent votre identité et votre argent : elles ne peuvent pas être
déléguées.

1. **Créer un compte Google Play Console** — 25 USD, une seule fois, via
   <https://play.google.com/console>.
   Le choix « organisation » ou « personnel » a une conséquence importante (point 3).
2. **Rédiger une politique de confidentialité** et l'héberger à une adresse publique.
   Google l'exige pour toute application (même sans collecte de données).
3. **Effectuer un test fermé** — compte **personnel** uniquement : Google exige
   **au moins 12 testeurs inscrits pendant 14 jours consécutifs** avant d'autoriser
   la publication publique. Un compte **organisation** (vérification d'entreprise)
   n'est pas soumis à cette règle.
4. **Créer la fiche Play Store** : description courte et longue, icône 512×512,
   bandeau 1024×500, au moins 2 captures d'écran de téléphone.
5. **Remplir les formulaires obligatoires** : classification du contenu,
   déclaration de sécurité des données, public visé, pays de diffusion.

### Ce qui peut être préparé à l'avance

* Le `.aab` signé, prêt à être téléversé.
* Le texte de la fiche, rédigé en français et en anglais.
* Les captures d'écran, prises avec l'application installée sur un téléphone.

### Téléversement

Play Console → votre application → **Production** (ou **Test fermé**) → **Créer une
version** → déposer `SchoolManager-1.1.aab` → écrire les notes de version → envoyer
pour examen. Le premier examen prend généralement quelques jours.

---

## 10. Publier une mise à jour

1. Modifier le site, puis reconstruire (étapes 1 à 3 du § 5).
2. **Incrémenter `versionCode`** dans `mobile/android/app/build.gradle`.
   Google Play refuse un code de version déjà utilisé. `versionName` est le numéro
   visible par les utilisateurs (`1.0`, `1.1`, `2.0`…).
3. Reconstruire le `.aab`, le téléverser, envoyer pour examen.

Le `versionCode` suit une progression stricte : 1, 2, 3… sans retour en arrière.

---

## 11. Installer sur un téléphone sans passer par Google Play

1. Copier `SchoolManager-1.1.apk` sur le téléphone (câble, courriel, ou `adb install`).
2. Sur le téléphone : Paramètres → Sécurité → autoriser l'installation
   d'applications de sources inconnues pour l'application utilisée.
3. Ouvrir le fichier `.apk` et confirmer.

Avec le câble, depuis un terminal :

```powershell
& "$env:USERPROFILE\AndroidToolchain\sdk\platform-tools\adb.exe" install -r `
  "C:\Users\USER\Documents\schoolapp-mobile\SchoolManager-1.1.apk"
```

Cette voie convient aux tests et aux utilisateurs avertis. Pour une diffusion large,
Google Play reste la seule solution raisonnable.

---

## 12. En cas de problème

| Symptôme | Cause probable | Solution |
|---|---|---|
| L'application affiche une page blanche | Le site n'a pas été assemblé | Relancer `npm run www` puis `npm run sync` |
| « Service momentanément indisponible » | Serveur injoignable ou adresse erronée | Vérifier `SM_API_BASE` dans `mobile/surcharges/js/mobile-config.js` et l'état du serveur |
| La session est perdue à chaque ouverture | L'adaptation `sessionStorage` n'a pas été appliquée | Vérifier que `js/mobile-config.js` est présent dans `www/` |
| L'écran de démarrage ne disparaît pas | `js/live.js` n'appelle pas `SM_MASQUER_DEMARRAGE` | Comparer avec la version du dépôt |
| L'application s'ouvre sur la page d'accueil du site web | La surcharge de l'écran d'accueil n'a pas été appliquée | Vérifier la présence de `mobile/surcharges/index.html`, puis relancer `npm run www` et `npm run sync` |
| `key.properties not found` à la compilation | Normal : aucun paquet signé ne sera produit | Recopier la clé depuis la sauvegarde, ou travailler en `.apk` de test |
| La compilation échoue après une modification de `build.gradle` | Syntaxe Gradle invalide | Revenir à la version du dépôt : `git checkout mobile/android/app/build.gradle` |

### Journal de la dernière compilation

```powershell
Get-Content "$env:USERPROFILE\AndroidToolchain\journaux\release.log" -Tail 50
```

---

## 13. Limites connues de la version 1.1

* **Android uniquement.** Une version iOS exigerait un Mac et un compte Apple
  Developer (99 USD par an) : la même base web est réutilisable, mais le travail
  reste à faire.
* **La connexion par Google et par courriel n'est pas disponible** dans
  l'application : ces procédés reposent sur une redirection du navigateur qui se
  comporte mal dans une vue interne. La connexion par identifiant et mot de passe
  fonctionne normalement. Le lien **« Autres accès »** ouvre la page publique, mais
  ces deux options ne fonctionneront que le jour où le serveur les activera
  (aujourd'hui : `{"google":false,"code_email":false}`).
* **Aucun fonctionnement hors ligne.** L'application exige une connexion réseau.
* **Pas de notifications.** L'envoi de notifications exigerait la mise en place
  d'un service de messagerie (Firebase) et un travail supplémentaire.
* **Pas de mode sombre système.** L'interface utilise son propre thème.
