# =============================================================================
#  SchoolManager — assistant de configuration de la connexion
#
#  Ajoute dans Vercel (Production) les variables d'environnement nécessaires à
#  « Se connecter avec Google » et à la « connexion par code envoyé par email ».
#
#  ⚠️ À QUOI SERT CE SCRIPT, ET À QUOI IL NE SERT PAS
#  Le site utilise sa PROPRE connexion Google (écrite dans le backend,
#  backend/app/routers/auth.py) : elle lit ses identifiants dans les variables
#  d'environnement Vercel. Supabase, dans ce projet, n'est QUE la base de
#  données PostgreSQL : activer Google dans le tableau de bord Supabase n'a
#  aucun effet sur le site.
#
#  Les valeurs sensibles (code client Google, mot de passe d'application) sont
#  saisies en mode masqué : elles ne s'affichent jamais à l'écran et ne sont
#  écrites nulle part sur le disque.
#
#  Usage :
#    powershell -ExecutionPolicy Bypass -File .\_configurer_connexion.ps1
# =============================================================================

$ErrorActionPreference = "Continue"
if ($PSScriptRoot) { Set-Location $PSScriptRoot }

$Vercel = "C:\Users\USER\AppData\Local\Programs\nodejs\vercel.cmd"
$REDIRECT_URI = "https://schoolapp-flame-six.vercel.app/api/v1/auth/google/callback"

if (-not (Test-Path $Vercel)) {
    Write-Host "La commande Vercel est introuvable : $Vercel" -ForegroundColor Red
    exit 1
}

function PoserVariable {
    param([string]$Nom, [string]$Valeur, [string]$Type = "config")
    if ([string]::IsNullOrWhiteSpace($Valeur)) {
        Write-Host ("  [ignore] {0} (valeur vide)" -f $Nom) -ForegroundColor DarkGray
        return
    }
    & $Vercel env rm $Nom production -y --no-color *> $null
    $Valeur | & $Vercel env add $Nom production --type $Type --no-color *> $null
    Write-Host ("  [ok]     {0}" -f $Nom) -ForegroundColor Green
}

function LireMasque {
    param([string]$Invite)
    $sec = Read-Host -AsSecureString $Invite
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}

Write-Host ""
Write-Host "=========================================================" -ForegroundColor Cyan
Write-Host " SchoolManager - configuration de la connexion" -ForegroundColor Cyan
Write-Host "=========================================================" -ForegroundColor Cyan

# --- 0. Adresse de retour (valeur publique, indispensable) -------------------
# Google exige que cette adresse soit déclarée à l'identique dans la console
# Google Cloud, sinon Google refuse la connexion.
Write-Host ""
Write-Host "0. Adresse de retour Google (déjà renseignée, on la confirme)" -ForegroundColor Yellow
PoserVariable "GOOGLE_REDIRECT_URI" $REDIRECT_URI "config"
Write-Host ("   Adresse à déclarer dans Google Cloud : {0}" -f $REDIRECT_URI) -ForegroundColor DarkGray

# --- 1. Connexion Google -----------------------------------------------------
Write-Host ""
Write-Host "1. Connexion Google" -ForegroundColor Yellow
Write-Host "   Console Google Cloud > APIs et services > Identifiants" -ForegroundColor DarkGray
Write-Host "   > votre ID client OAuth « Application Web » > copier les 2 valeurs." -ForegroundColor DarkGray
Write-Host ""
$idClient = Read-Host "   Identifiant client (se termine par .apps.googleusercontent.com)"

if ([string]::IsNullOrWhiteSpace($idClient)) {
    Write-Host "   [ignore] Aucun identifiant saisi : la connexion Google restera desactivee." -ForegroundColor DarkGray
} elseif ($idClient -notlike "*.apps.googleusercontent.com") {
    Write-Host "   ATTENTION : cette valeur ne ressemble pas a un identifiant client Google." -ForegroundColor Red
    $confirme = Read-Host "   Continuer quand meme ? (o/n)"
    if ($confirme -ne "o") { $idClient = "" }
}

$codeClient = ""
if (-not [string]::IsNullOrWhiteSpace($idClient)) {
    $codeClient = LireMasque "   Code client Google (saisie masquee, rien ne s'affiche)"
    PoserVariable "GOOGLE_CLIENT_ID" $idClient.Trim() "config"
    PoserVariable "GOOGLE_CLIENT_SECRET" $codeClient.Trim() "secret"
}

# --- 2. Connexion par code envoye par email ---------------------------------
Write-Host ""
Write-Host "2. Connexion par code envoye par email (facultatif)" -ForegroundColor Yellow
$reponse = Read-Host "   La configurer maintenant ? (o/n)"

if ($reponse -eq "o") {
    $expediteur = Read-Host "   Adresse d'expedition (ex. SchoolManager <vous@gmail.com>)"
    PoserVariable "EMAIL_FROM" $expediteur.Trim() "config"

    Write-Host ""
    Write-Host "   Mode d'envoi :" -ForegroundColor DarkGray
    Write-Host "     g = Gmail / autre SMTP  (marche tout de suite, gratuit)" -ForegroundColor DarkGray
    Write-Host "     r = Resend              (exige un domaine verifie)" -ForegroundColor DarkGray
    $mode = Read-Host "   Votre choix (g/r)"

    if ($mode -eq "r") {
        $cle = LireMasque "   Cle API Resend (saisie masquee)"
        PoserVariable "RESEND_API_KEY" $cle.Trim() "secret"
    } else {
        $hote = Read-Host "   Serveur SMTP [smtp.gmail.com]"
        if ([string]::IsNullOrWhiteSpace($hote)) { $hote = "smtp.gmail.com" }
        $port = Read-Host "   Port [587]"
        if ([string]::IsNullOrWhiteSpace($port)) { $port = "587" }
        $utilisateur = Read-Host "   Nom d'utilisateur SMTP (votre adresse email)"
        $motDePasse = LireMasque "   Mot de passe d'application (16 caracteres, saisie masquee)"
        PoserVariable "SMTP_HOST" $hote.Trim() "config"
        PoserVariable "SMTP_PORT" $port.Trim() "config"
        PoserVariable "SMTP_USER" $utilisateur.Trim() "config"
        PoserVariable "SMTP_PASS" $motDePasse.Trim() "secret"
    }
} else {
    Write-Host "   [ignore] Vous pourrez relancer ce script plus tard." -ForegroundColor DarkGray
}

# --- 3. Recapitulatif --------------------------------------------------------
Write-Host ""
Write-Host "3. Etat des variables de production" -ForegroundColor Yellow
& $Vercel env ls production --no-color

Write-Host ""
Write-Host "Termine. Un changement de variable ne s'applique qu'au" -ForegroundColor Cyan
Write-Host "DEPLOIEMENT SUIVANT : il faut redeployer la production." -ForegroundColor Cyan
Write-Host ""
