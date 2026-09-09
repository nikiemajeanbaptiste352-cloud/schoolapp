"""Lanceur pytest (console PowerShell dégradée) — écrit le résultat dans un
journal puis en affiche la fin. Chemins absolus : aucun cd requis."""
import os
import subprocess
import sys

BACKEND = os.path.dirname(os.path.abspath(__file__))
os.chdir(BACKEND)
LOG = os.path.join(BACKEND, "pytest_paie_log.txt")

args = [sys.executable, "-m", "pytest"]
# Cible : tous les tests ou un fichier précis passé en argument
args += sys.argv[1:] or ["tests/"]
args += ["-q", "--no-header", "-p", "no:cacheprovider"]

env = dict(os.environ, PYTHONIOENCODING="utf-8")
res = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
out = res.stdout + ("\n" + res.stderr if res.stderr else "")
with open(LOG, "w", encoding="utf-8") as f:
    f.write(out)
print("EXITCODE", res.returncode)
print(out[-4000:])
