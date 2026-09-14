@echo off
chcp 65001 >nul
title SchoolManager - configuration de la connexion
cd /d "%~dp0"

echo ==========================================================
echo  SchoolManager - configuration de la connexion
echo ==========================================================
echo.
echo  Repondez aux questions ci-dessous.
echo  - Les valeurs normales s'affichent quand vous tapez.
echo  - Les mots de passe ne s'affichent PAS : c'est normal.
echo  - Pour coller : clic droit dans la fenetre, puis Entree.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0_configurer_connexion.ps1"

echo.
echo ----------------------------------------------------------
echo   Appuyez sur une touche pour fermer cette fenetre.
echo ----------------------------------------------------------
pause >nul
