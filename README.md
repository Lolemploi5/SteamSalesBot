# 🤖 Steam Sales Bot

Un bot Telegram automatisé qui surveille les jeux Steam gratuits (promotion -100%) et envoie des notifications automatiques.

## 🚀 Fonctionnalités

- ✅ **Vérification automatique** : Tous les jours à 9h et 19h (heure de Paris)
- 🎮 **Détection des jeux gratuits** : Via l'API Steam officielle
- 📱 **Notifications Telegram** : Messages automatiques pour chaque nouveau jeu gratuit
- 🔍 **Vérification manuelle** : Commande `/check` pour vérifier à tout moment
- 🚫 **Pas de doublons** : Système de mémorisation des jeux déjà envoyés
- 👥 **Multi-utilisateurs** : Support de plusieurs utilisateurs Telegram

## 📋 Prérequis

- Python 3.8+
- Un bot Telegram (token via [@BotFather](https://t.me/BotFather))
- Accès Internet pour les API Steam et Telegram

## 🛠️ Installation locale

1. **Cloner le projet**
```bash
git clone <votre-repo>
cd steam-sales-bot
```

2. **Installer les dépendances**
```bash
pip install -r requirements.txt
```

3. **Configurer les variables d'environnement**
   ```bash
   cp .env.example .env
   # Éditez .env et ajoutez votre token Telegram
   ```
   
   Ou définissez directement la variable :
   ```bash
   export TELEGRAM_TOKEN="votre_token_telegram"
   ```

4. **Lancer le bot**
```bash
python main.py
```

## 🌐 Déploiement sur Render

### Configuration requise

1. **Variables d'environnement** (optionnel, le token est déjà dans le code) :
   - `TELEGRAM_TOKEN` : Token de votre bot Telegram

2. **Build Command** :
   ```bash
   pip install -r requirements.txt
   ```

3. **Start Command** :
   ```bash
   python main.py
   ```

### Configuration Render automatique

Créez un fichier `render.yaml` (optionnel) pour une configuration automatique :

```yaml
services:
  - type: web
    name: steam-sales-bot
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: python main.py
    envVars:
      - key: TELEGRAM_TOKEN
        value: YOUR_TELEGRAM_TOKEN_HERE
```

## 🎮 Utilisation

### Commandes disponibles

- `/start` - Initialiser le bot et s'inscrire aux notifications
- `/check` - Vérifier manuellement les jeux gratuits
- `/stats` - Afficher les statistiques du bot

### Fonctionnement automatique

Le bot vérifie automatiquement les jeux gratuits Steam :
- **9h00** (heure de Paris)
- **19h00** (heure de Paris)

Les utilisateurs inscrits reçoivent automatiquement les notifications.

## 📁 Structure du projet

```
steam-sales-bot/
├── main.py              # Script principal du bot
├── requirements.txt     # Dépendances Python
├── sent_games.json     # Base de données des jeux envoyés
├── README.md           # Documentation
├── .gitignore          # Fichiers à ignorer par Git
└── render.yaml         # Configuration Render (optionnel)
```

## 🔧 Configuration avancée

### Modifier les horaires de vérification

Dans `main.py`, fonction `setup_scheduler()` :

```python
# Vérification à 9h
self.scheduler.add_job(
    self.check_free_games_job,
    CronTrigger(hour=9, minute=0, timezone=TIMEZONE),
    id="morning_check"
)

# Vérification à 19h
self.scheduler.add_job(
    self.check_free_games_job,
    CronTrigger(hour=19, minute=0, timezone=TIMEZONE),
    id="evening_check"
)
```

### Ajouter d'autres horaires

```python
# Exemple : vérification toutes les 6 heures
self.scheduler.add_job(
    self.check_free_games_job,
    CronTrigger(hour="*/6", timezone=TIMEZONE),
    id="every_6_hours"
)
```

## 📊 API utilisée

Le bot utilise l'API Steam : `https://steamapi.xpaw.me/v1/steam/prices/USD.min.json`

Cette API fournit :
- Les prix actuels des jeux Steam
- Les informations de promotion
- Les identifiants des jeux

## 🐛 Dépannage

### Le bot ne démarre pas
- Vérifiez que le token Telegram est correct
- Vérifiez que les dépendances sont installées : `pip install -r requirements.txt`

### Pas de notifications
- Lancez `/start` dans votre conversation avec le bot
- Vérifiez les logs pour les erreurs de connexion

### Erreurs de timezone
- Le bot utilise automatiquement le fuseau `Europe/Paris`
- En cas de problème, vérifiez l'installation de `pytz`

## 📝 Logs

Le bot affiche des logs détaillés :
- Démarrage et arrêt
- Vérifications automatiques
- Nouveaux jeux détectés
- Erreurs de connexion

## 🤝 Contribution

1. Fork le projet
2. Créez une branche feature (`git checkout -b feature/nouvelle-fonctionnalite`)
3. Committez vos changements (`git commit -am 'Ajout nouvelle fonctionnalité'`)
4. Pushez vers la branche (`git push origin feature/nouvelle-fonctionnalite`)
5. Ouvrez une Pull Request

## 📄 Licence

Ce projet est sous licence MIT. Voir le fichier `LICENSE` pour plus de détails.

## ⚠️ Avertissement

Ce bot utilise une API non-officielle Steam. En cas de changement de l'API, le bot pourrait nécessiter des modifications.

## 📞 Support

En cas de problème :
1. Vérifiez les logs du bot
2. Consultez la section dépannage
3. Ouvrez une issue sur GitHub
