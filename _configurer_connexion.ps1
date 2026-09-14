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
#  Usage (le plus simple) :
#    double-cliquez sur « Configurer-la-connexion.cmd » (meme dossier), ou
#    dans un terminal :  .\Configurer-la-connexion.cmd
#
#  ⚠️ NE TAPEZ RIEN A L'INVITE POWERSHELL VOUS-MEME : le script pose lui-meme
#  ses questions. Si vous voyez « Erreur », « Jeton inattendu » ou « n'est pas
#  reconnu », c'est que vous avez tape une valeur au mauvais endroit :
#  relancez le script et repondez AU MOMENT ou il demande.
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
    if ($LASTEXITCODE -eq 0) {
        Write-Host ("  [ok]     {0}" -f $Nom) -ForegroundColor Green
    } else {
        Write-Host ("  [ECHEC]  {0}  (la commande Vercel a renvoye le code {1})" -f $Nom, $LASTEXITCODE) -ForegroundColor Red
        Write-Host "           La variable n'a PAS ete enregistree." -ForegroundColor DarkGray
    }
}

# Accepte o / oui / y / yes (majuscules comprises) comme une reponse positive.
function EstOui {
    param([string]$Reponse)
    if ([string]::IsNullOrWhiteSpace($Reponse)) { return $false }
    return ($Reponse.Trim() -match '^(o|oui|y|yes|ok)$')
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
Write-Host "   Collez la valeur qui se termine par .apps.googleusercontent.com" -ForegroundColor DarkGray
Write-Host "   (clic droit dans la fenetre = coller, puis appuyez sur Entree)" -ForegroundColor DarkGray
$idClient = (Read-Host "   Identifiant client").Trim()

if ([string]::IsNullOrWhiteSpace($idClient)) {
    Write-Host "   [ignore] Aucun identifiant saisi : la connexion Google restera desactivee." -ForegroundColor DarkGray
} elseif ($idClient -notlike "*.apps.googleusercontent.com") {
    Write-Host "   ATTENTION : cette valeur ne ressemble pas a un identifiant client Google." -ForegroundColor Red
    Write-Host "   Un identifiant client fait environ 73 caracteres et se termine" -ForegroundColor DarkGray
    Write-Host "   obligatoirement par .apps.googleusercontent.com" -ForegroundColor DarkGray
    $confirme = Read-Host "   Continuer quand meme ? (o/n)"
    if (-not (EstOui $confirme)) { $idClient = "" }
}

$codeClient = ""
if (-not [string]::IsNullOrWhiteSpace($idClient)) {
    $codeClient = LireMasque "   Code client Google (saisie masquee, rien ne s'affiche)"
    PoserVariable "GOOGLE_CLIENT_ID" $idClient.Trim() "config"
    PoserVariable "GOOGLE_CLIENT_SECRET" $codeClient.Trim() "secret"
}

# --- 2. Connexion par code envoye par email ---------------------------------
#  Le visiteur saisit son adresse, recoit un code a 6 chiffres (valable 10 min)
#  et se connecte avec. Il faut donc : une adresse d'expedition + un moyen
#  d'envoyer. Le plus simple est Gmail avec un « mot de passe d'application ».
Write-Host ""
Write-Host "2. Connexion par code envoye par email" -ForegroundColor Yellow
$reponse = Read-Host "   La configurer maintenant ? (o = oui / n = non)"

if (EstOui $reponse) {
    $expediteur = Read-Host "   Adresse d'expedition (ex. SchoolManager <vous@gmail.com>)"
    PoserVariable "EMAIL_FROM" $expediteur.Trim() "config"

    # Adresse seule (sans le « Nom <> ») : sert d'utilisateur SMTP.
    $adresseSeule = $expediteur.Trim()
    if ($adresseSeule -match "<([^>]+)>") { $adresseSeule = $matches[1] }
    $adresseSeule = $adresseSeule.Trim()

    Write-Host ""
    Write-Host "   Mode d'envoi :" -ForegroundColor DarkGray
    Write-Host "     g = Gmail      (le plus simple : une seule question ensuite)" -ForegroundColor DarkGray
    Write-Host "     a = autre SMTP (serveur, port et utilisateur a saisir)" -ForegroundColor DarkGray
    Write-Host "     r = Resend     (exige un domaine verifie sur resend.com)" -ForegroundColor DarkGray
    $mode = (Read-Host "   Votre choix (g/a/r)  [Entree = g]").Trim().ToLower()

    if ($mode -eq "r") {
        $cle = LireMasque "   Cle API Resend (saisie masquee)"
        PoserVariable "RESEND_API_KEY" $cle.Trim() "secret"
    } elseif ($mode -eq "a") {
        $hote = Read-Host "   Serveur SMTP (ex. mail.mondomaine.com)"
        $port = Read-Host "   Port [587]"
        if ([string]::IsNullOrWhiteSpace($port)) { $port = "587" }
        $utilisateur = Read-Host "   Nom d'utilisateur SMTP"
        $motDePasse = LireMasque "   Mot de passe (saisie masquee)"
        PoserVariable "SMTP_HOST" $hote.Trim() "config"
        PoserVariable "SMTP_PORT" $port.Trim() "config"
        PoserVariable "SMTP_USER" $utilisateur.Trim() "config"
        PoserVariable "SMTP_PASS" $motDePasse.Trim() "secret"
    } else {
        # Gmail : serveur, port et utilisateur sont toujours identiques — on les
        # deduit de l'adresse, il ne reste donc que le mot de passe a saisir.
        PoserVariable "SMTP_HOST" "smtp.gmail.com" "config"
        PoserVariable "SMTP_PORT" "587" "config"
        PoserVariable "SMTP_USER" $adresseSeule "config"
        Write-Host ("   Utilisateur SMTP deduit de l'adresse : {0}" -f $adresseSeule) -ForegroundColor DarkGray
        $motDePasse = LireMasque "   Mot de passe d'application Gmail (16 caracteres, saisie masquee)"
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
Write-Host "Verifiez ci-dessus que les lignes GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET," -ForegroundColor Cyan
Write-Host "EMAIL_FROM et SMTP_* sont bien presentes." -ForegroundColor Cyan
Write-Host ""
Write-Host "Termine. Un changement de variable ne s'applique qu'au" -ForegroundColor Cyan
Write-Host "DEPLOIEMENT SUIVANT : il faut redeployer la production." -ForegroundColor Cyan
Write-Host ""
Write-Host "Etape suivante : dites simplement « c'est fait » a l'assistant, il" -ForegroundColor Yellow
Write-Host "redeclenchera le deploiement et verifiera les 2 boutons de connexion." -ForegroundColor Yellow
Write-Host ""
