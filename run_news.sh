#!/bin/bash

# Définition des chemins absolus
export PROJECT_DIR="/Users/jonathan/news-py"
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PYTHONPATH="$PROJECT_DIR"

# Définir le LOG_FILE avec chemin absolu
LOG_FILE="$PROJECT_DIR/news.log"

# Aller dans le répertoire du projet
cd "$PROJECT_DIR"

# Activer l'environnement virtuel avec chemin absolu
source "$PROJECT_DIR/venv/bin/activate"

# Exécuter le script Python
"$PROJECT_DIR/venv/bin/python" "$PROJECT_DIR/main.py" >> "$LOG_FILE" 2>&1

# Pas besoin de PID car launchd gère le processus
