#!/usr/bin/env python3
"""
Steam Sales Bot - Telegram Bot pour notifier les jeux Steam gratuits
Vérifie uniquement les vraies promotions -100% (pas les jeux F2P de base)
"""

import json
import os
import logging
import requests
import asyncio
import threading
import time
from datetime import datetime
from typing import Dict, List, Set
from http.server import HTTPServer, BaseHTTPRequestHandler
from string import Template

import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Configuration du logging améliorée
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        # Optionnel: logging vers fichier en production
        # logging.FileHandler('steam_bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Réduire le niveau de logging pour les bibliothèques externes
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.WARNING)
logging.getLogger('apscheduler').setLevel(logging.WARNING)

# Configuration
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TELEGRAM_TOKEN:
    logger.error("❌ TELEGRAM_TOKEN environment variable is required!")
    logger.error("💡 Set it with: export TELEGRAM_TOKEN='your_bot_token'")
    logger.error("🤖 Get your token from @BotFather on Telegram")
    exit(1)
    
STEAM_API_URLS = [
    "https://store.steampowered.com/api/featured/",
    "https://steamapi.xpaw.me/v1/steam/prices/USD.min.json"
]
SENT_GAMES_FILE = "sent_games.json"
TIMEZONE = pytz.timezone('Europe/Paris')

# Constantes
CONTENT_TYPE_JSON = 'application/json'
CONTENT_TYPE_HTML = 'text/html'
PORT = int(os.getenv('PORT', 8000))

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")


def render_template(name, **context):
    path = os.path.join(TEMPLATE_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        template = Template(f.read())
    return template.safe_substitute(**context)


# Serveur HTTP minimal pour Render
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', CONTENT_TYPE_JSON)
            self.end_headers()
            
            status = {
                "status": "healthy",
                "service": "Steam Sales Bot",
                "timestamp": datetime.now(TIMEZONE).isoformat(),
                "scheduled_checks": "9:00 and 19:00 Europe/Paris",
                "total_users": len(steam_bot.chat_ids) if 'steam_bot' in globals() else 0
            }
            self.wfile.write(json.dumps(status, indent=2).encode())
            
        elif self.path.startswith('/subscribe/'):
            # Endpoint d'inscription: /subscribe/CHAT_ID
            try:
                chat_id_str = self.path.split('/')[-1]
                
                # Validation du chat_id
                if not chat_id_str.isdigit():
                    raise ValueError("Chat ID doit être un nombre")
                
                chat_id = int(chat_id_str)
                
                # Validation des limites Telegram (chat_id doit être positif et dans une plage raisonnable)
                if chat_id <= 0 or chat_id > 9999999999:  # Limite Telegram approximative
                    raise ValueError("Chat ID invalide")
                
                # Ajouter le chat_id à la liste
                if 'steam_bot' in globals():
                    steam_bot.add_chat_id(chat_id)
                    
                self.send_response(200)
                self.send_header('Content-type', CONTENT_TYPE_HTML)
                self.end_headers()
                
                total_users = len(steam_bot.chat_ids) if 'steam_bot' in globals() else 0
                html = render_template('success.html', chat_id=chat_id, total_users=total_users)
                self.wfile.write(html.encode())
                
                logger.info(f"✅ Nouvel utilisateur inscrit: {chat_id} (Total: {total_users})")
                
            except ValueError as e:
                self.send_response(400)
                self.send_header('Content-type', CONTENT_TYPE_HTML)
                self.end_headers()
                error_html = f"""
                <html><head><title>Erreur d'inscription</title></head><body>
                <h1>❌ Erreur: {str(e)}</h1>
                <p>Veuillez vérifier votre Chat ID.</p>
                <p><a href='/'>← Retour à l'accueil</a></p>
                </body></html>
                """
                self.wfile.write(error_html.encode())
                logger.warning(f"⚠️ Tentative d'inscription avec Chat ID invalide: {self.path}")
                
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', CONTENT_TYPE_HTML)
                self.end_headers()
                error_html = f"""
                <html><head><title>Erreur serveur</title></head><body>
                <h1>❌ Erreur serveur interne</h1>
                <p>Une erreur s'est produite lors de l'inscription.</p>
                <p><a href='/'>← Retour à l'accueil</a></p>
                </body></html>
                """
                self.wfile.write(error_html.encode())
                logger.error(f"Erreur serveur lors de l'inscription: {e}")
        
        else:
            self.send_response(200)
            self.send_header('Content-type', CONTENT_TYPE_HTML)
            self.end_headers()
            
            html = render_template('index.html', total_users=len(steam_bot.chat_ids) if 'steam_bot' in globals() else 0, last_update=datetime.now(TIMEZONE).strftime('%H:%M'))
            self.wfile.write(html.encode())
    
    def log_message(self, format, *args):
        # Supprimer les logs HTTP pour éviter le spam
        pass

def start_http_server():
    """Démarre le serveur HTTP pour Render"""
    try:
        server = HTTPServer(('0.0.0.0', PORT), HealthCheckHandler)
        logger.info(f"🌐 Serveur HTTP démarré sur le port {PORT}")
        server.serve_forever()
    except OSError as e:
        if "Address already in use" in str(e):
            logger.info(f"⚠️ Port {PORT} déjà utilisé - serveur HTTP ignoré (normal sur Render)")
        else:
            logger.error(f"Erreur serveur HTTP: {e}")

class SteamSalesBot:
    def __init__(self):
        self.sent_games: Dict = self.load_sent_games()
        self.chat_ids: Set[int] = set(self.sent_games.get('chat_ids', []))
        self._last_telegram_call = 0
        self._telegram_call_interval = 1.0  # Minimum 1 seconde entre les appels Telegram
        
    def load_sent_games(self) -> Dict:
        """Charge les jeux déjà envoyés depuis le fichier JSON avec gestion d'erreurs robuste"""
        default_data = {"sent_games": {}, "chat_ids": []}
        
        if not os.path.exists(SENT_GAMES_FILE):
            logger.info(f"Fichier {SENT_GAMES_FILE} non trouvé, création avec données par défaut")
            self.save_sent_games_with_data(default_data)
            return default_data
            
        try:
            with open(SENT_GAMES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Validation de la structure des données
            if not isinstance(data, dict):
                raise ValueError("Le fichier JSON doit contenir un objet")
                
            if 'sent_games' not in data or not isinstance(data['sent_games'], dict):
                logger.warning("Clé 'sent_games' manquante ou invalide, réinitialisation")
                data['sent_games'] = {}
                
            if 'chat_ids' not in data or not isinstance(data['chat_ids'], list):
                logger.warning("Clé 'chat_ids' manquante ou invalide, réinitialisation")
                data['chat_ids'] = []
            
            # Nettoyer les chat_ids invalides
            valid_chat_ids = []
            for chat_id in data['chat_ids']:
                if isinstance(chat_id, int) and chat_id > 0:
                    valid_chat_ids.append(chat_id)
                else:
                    logger.warning(f"Chat ID invalide supprimé: {chat_id}")
            
            data['chat_ids'] = valid_chat_ids
            logger.info(f"Chargé {len(data['sent_games'])} jeux et {len(valid_chat_ids)} utilisateurs")
            return data
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Fichier {SENT_GAMES_FILE} corrompu: {e}")
            # Créer une sauvegarde du fichier corrompu
            backup_file = f"{SENT_GAMES_FILE}.backup.{int(datetime.now().timestamp())}"
            try:
                os.rename(SENT_GAMES_FILE, backup_file)
                logger.info(f"Fichier corrompu sauvegardé vers {backup_file}")
            except Exception:
                pass
            
            # Retourner les données par défaut
            self.save_sent_games_with_data(default_data)
            return default_data
            
        except Exception as e:
            logger.error(f"Erreur inattendue lors du chargement de {SENT_GAMES_FILE}: {e}")
            return default_data
    
    def save_sent_games(self):
        """Sauvegarde les jeux envoyés dans le fichier JSON"""
        data = {
            "sent_games": self.sent_games.get("sent_games", {}),
            "chat_ids": list(self.chat_ids)
        }
        self.save_sent_games_with_data(data)
    
    def save_sent_games_with_data(self, data: Dict):
        """Sauvegarde des données spécifiques dans le fichier JSON"""
        try:
            # Écrire dans un fichier temporaire d'abord
            temp_file = f"{SENT_GAMES_FILE}.tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # Remplacer atomiquement le fichier original
            os.replace(temp_file, SENT_GAMES_FILE)
            logger.debug(f"Données sauvegardées avec succès dans {SENT_GAMES_FILE}")
            
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde de {SENT_GAMES_FILE}: {e}")
            # Nettoyer le fichier temporaire en cas d'erreur
            try:
                if os.path.exists(f"{SENT_GAMES_FILE}.tmp"):
                    os.remove(f"{SENT_GAMES_FILE}.tmp")
            except Exception:
                pass
    
    def add_chat_id(self, chat_id: int):
        """Ajoute un chat_id à la liste des destinataires et envoie une notification de bienvenue"""
        is_new_user = chat_id not in self.chat_ids
        self.chat_ids.add(chat_id)
        self.save_sent_games()
        logger.info(f"Chat ID {chat_id} ajouté à la liste des destinataires")
        
        # Envoyer une notification de bienvenue si c'est un nouvel utilisateur
        if is_new_user:
            try:
                # Vérifier s'il y a un event loop actif
                try:
                    asyncio.get_running_loop()
                    # Si on est dans un event loop existant, créer une tâche
                    welcome_task = asyncio.create_task(self.send_welcome_notification(chat_id))
                    self._welcome_tasks = getattr(self, '_welcome_tasks', set())
                    self._welcome_tasks.add(welcome_task)
                    welcome_task.add_done_callback(self._welcome_tasks.discard)
                except RuntimeError:
                    # Pas d'event loop actif, utiliser l'API HTTP directe
                    self.send_welcome_notification_sync(chat_id)
            except Exception as e:
                logger.warning(f"Erreur lors de l'envoi de la notification de bienvenue: {e}")
    
    def _rate_limit_telegram_call(self):
        """Applique un rate limiting simple pour les appels Telegram API"""
        current_time = time.time()
        time_since_last_call = current_time - self._last_telegram_call
        
        if time_since_last_call < self._telegram_call_interval:
            sleep_time = self._telegram_call_interval - time_since_last_call
            logger.debug(f"Rate limiting: attente de {sleep_time:.2f}s")
            time.sleep(sleep_time)
        
        self._last_telegram_call = time.time()
    
    def send_welcome_notification_sync(self, chat_id: int):
        """Envoie une notification de bienvenue via l'API HTTP Telegram (version synchrone)"""
        try:
            if not TELEGRAM_TOKEN:
                logger.warning("Token Telegram non configuré - notification de bienvenue ignorée")
                return
            
            self._rate_limit_telegram_call()
                
            welcome_message = f"""🎉 **Bienvenue sur Steam Sales Bot !**

✅ **Inscription confirmée !**
🆔 **Votre Chat ID :** `{chat_id}`

🎮 **Ce que vous recevrez :**
• Notifications automatiques à 9h et 19h (heure de Paris)
• Jeux Steam en vraie promotion -100% uniquement
• Pas de spam, seulement les vraies bonnes affaires !

🔍 **Commandes disponibles :**
• `/start` - Afficher le menu principal
• `/check` - Vérifier manuellement les promotions

🌐 **Partagez le bot :** https://t.me/Steam_Sales_Notifier_Bot

⚡ **Première vérification en cours...**"""

            # Envoyer via l'API HTTP Telegram
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            data = {
                'chat_id': chat_id,
                'text': welcome_message,
                'parse_mode': 'Markdown',
                'disable_web_page_preview': True
            }
            
            response = requests.post(url, data=data, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"✅ Notification de bienvenue envoyée à {chat_id}")
            else:
                error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
                logger.warning(f"⚠️ Erreur envoi notification bienvenue (HTTP {response.status_code}): {error_data}")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Erreur réseau lors de l'envoi de la notification de bienvenue: {e}")
        except Exception as e:
            logger.error(f"Erreur inattendue lors de l'envoi de la notification de bienvenue: {e}")
    
    async def send_welcome_notification(self, chat_id: int):
        """Envoie une notification de bienvenue à un nouvel utilisateur"""
        try:
            # Vérifier si le token Telegram est disponible
            if not TELEGRAM_TOKEN:
                logger.warning("Token Telegram non configuré - notification de bienvenue ignorée")
                return

            # Créer un bot temporaire pour envoyer la notification
            bot = Bot(token=TELEGRAM_TOKEN)
            
            welcome_message = f"""🎉 **Bienvenue sur Steam Sales Bot !**

✅ **Inscription confirmée !**
🆔 **Votre Chat ID :** `{chat_id}`
👥 **Vous rejoignez {len(self.chat_ids)} gamers inscrits**

🎮 **Ce que vous allez recevoir :**
• Notifications instantanées des jeux Steam en vraie promotion -100%
• Exclusion des jeux gratuits de base (pas de spam)
• Liens directs vers Steam pour télécharger immédiatement
• Vérifications automatiques à 9h et 19h (Europe/Paris)

🔔 **Prochaines notifications :**
• **Automatiques** : 9h00 et 19h00 tous les jours
• **À la demande** : Utilisez la commande /check quand vous voulez

⚡ **Important :** Je ne notifie que les **vraies promotions temporaires**, pas les jeux free-to-play permanents comme CS2, TF2, Dota 2, etc.

🎯 **Bon gaming et n'hésitez pas à partager le bot !**

_Vous pouvez utiliser /check à tout moment pour vérifier manuellement._"""
            
            await bot.send_message(
                chat_id=chat_id,
                text=welcome_message,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            
            logger.info(f"✅ Notification de bienvenue envoyée à {chat_id}")
            
        except Exception as e:
            logger.error(f"❌ Erreur lors de l'envoi de la notification de bienvenue à {chat_id}: {e}")
            # Ne pas faire échouer l'inscription si la notification échoue
    
    def get_free_games(self) -> List[Dict]:
        """Récupère uniquement les jeux en vraie promotion -100% (pas les F2P de base)"""
        for api_url in STEAM_API_URLS:
            try:
                logger.info(f"Tentative de récupération via {api_url}")
                response = requests.get(api_url, timeout=30, 
                                      headers={'User-Agent': 'Steam Sales Bot/1.0'})
                response.raise_for_status()
                
                if api_url == STEAM_API_URLS[0]:  # Featured API
                    return self._parse_featured_api(response.json())
                else:  # xpaw API
                    return self._parse_xpaw_api(response.json())
                    
            except requests.exceptions.RequestException as e:
                logger.warning(f"Erreur API {api_url}: {e}")
                continue
            except Exception as e:
                logger.error(f"Erreur inattendue avec {api_url}: {e}")
                continue
        
        logger.error("Toutes les API Steam ont échoué")
        return []
    
    def _parse_featured_api(self, data: Dict) -> List[Dict]:
        """Parse les données de l'API featured Steam"""
        free_games = []
        
        # Ne vérifier que la section "specials" qui contient les vraies promotions
        if 'specials' in data and 'items' in data['specials']:
            for item in data['specials']['items']:
                discount_percent = item.get('discount_percent', 0)
                final_price = item.get('final_price', 0)
                original_price = item.get('original_price', 0)
                
                # Conditions strictes pour une vraie promotion gratuite
                if (discount_percent == 100 and 
                    final_price == 0 and 
                    original_price > 100):  # Plus de $1
                    
                    app_id = str(item.get('id', ''))
                    name = item.get('name', f'Jeu {app_id}')
                    original_price_dollars = original_price / 100
                    
                    if app_id and not self.is_game_already_sent(app_id):
                        if self._verify_real_promotion(app_id, name):
                            free_games.append({
                                'app_id': app_id,
                                'name': name,
                                'url': f'https://store.steampowered.com/app/{app_id}/',
                                'initial_price': original_price_dollars
                            })
        
        logger.info(f"Trouvé {len(free_games)} vraies promotions gratuites (API featured)")
        return free_games
    
    def _parse_xpaw_api(self, data: Dict) -> List[Dict]:
        """Parse les données de l'API xpaw Steam"""
        free_games = []
        
        # L'API xpaw retourne un dict avec app_id comme clés
        for app_id, item_data in data.items():
            if not isinstance(item_data, dict):
                continue
                
            price_data = item_data.get('data', {})
            if not price_data:
                continue
                
            # Vérifier s'il y a une promotion -100%
            discount = price_data.get('discount_percent', 0)
            final_price = price_data.get('final_price', 0)
            initial_price = price_data.get('initial_price', 0)
            
            if (discount == 100 and 
                final_price == 0 and 
                initial_price > 100):  # Plus de $1 initialement
                
                name = item_data.get('name', f'Jeu {app_id}')
                initial_price_dollars = initial_price / 100
                
                if not self.is_game_already_sent(app_id):
                    if self._verify_real_promotion(app_id, name):
                        free_games.append({
                            'app_id': app_id,
                            'name': name,
                            'url': f'https://store.steampowered.com/app/{app_id}/',
                            'initial_price': initial_price_dollars
                        })
        
        logger.info(f"Trouvé {len(free_games)} vraies promotions gratuites (API xpaw)")
        return free_games
    
    def _verify_real_promotion(self, app_id: str, game_name: str) -> bool:
        """Vérifie qu'il s'agit vraiment d'une promotion et pas d'un F2P"""
        # Liste étendue des jeux F2P connus à exclure
        known_f2p_games = {
            # Jeux populaires F2P
            '730',     # Counter-Strike 2
            '440',     # Team Fortress 2  
            '570',     # Dota 2
            '238960',  # Path of Exile
            '386360',  # SMITE
            '444090',  # Paladins
            '578080',  # PUBG (devenu F2P)
            '1222670', # Apex Legends
            '359550',  # Tom Clancy's Rainbow Six Siege (Starter Edition)
            '252490',  # Rust (version F2P)
            '813780',  # Age of Empires II: Definitive Edition (F2P weekends)
            '271590',  # Grand Theft Auto V (F2P Epic periods)
            '431960',  # Wallpaper Engine (souvent en promotion)
            '105600',  # Terraria (souvent en promotion mais pas F2P permanent)
            # MMO F2P
            '8500',    # EVE Online
            '1085660', # Destiny 2
            '582010',  # Monster Hunter: World (F2P weekends)
            '945360',  # Among Us (souvent en promotion)
            '1174180', # Red Dead Redemption 2 (F2P weekends sur Epic)
        }
        
        # Exclure les jeux F2P connus
        if app_id in known_f2p_games:
            logger.info(f"Jeu F2P exclu: {game_name} (ID: {app_id})")
            return False
        
        # Patterns de noms à exclure (souvent des F2P ou démos)
        exclude_patterns = [
            'free to play', 'f2p', 'demo', 'beta', 'prologue', 
            'playtest', 'benchmark', 'trailer', 'soundtrack',
            'wallpaper', 'theme', 'avatar', 'early access demo'
        ]
        
        game_name_lower = game_name.lower()
        for pattern in exclude_patterns:
            if pattern in game_name_lower:
                logger.info(f"Jeu exclu par pattern '{pattern}': {game_name}")
                return False
        
        # Accepter le jeu comme vraie promotion
        logger.debug(f"Jeu validé comme vraie promotion: {game_name} (ID: {app_id})")
        return True
    
    def is_game_already_sent(self, app_id: str) -> bool:
        """Vérifie si un jeu a déjà été envoyé"""
        return app_id in self.sent_games.get("sent_games", {})
    
    def mark_game_as_sent(self, app_id: str, game_name: str):
        """Marque un jeu comme envoyé"""
        if "sent_games" not in self.sent_games:
            self.sent_games["sent_games"] = {}
        
        self.sent_games["sent_games"][app_id] = {
            "name": game_name,
            "sent_at": datetime.now(TIMEZONE).isoformat()
        }
        self.save_sent_games()
    
    async def send_free_games(self, context: ContextTypes.DEFAULT_TYPE, manual_check: bool = False):
        """Envoie les nouvelles promotions -100% à tous les chats enregistrés"""
        free_games = self.get_free_games()
        
        if not free_games:
            if manual_check and self.chat_ids:
                for chat_id in self.chat_ids:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text="🎮 Aucune vraie promotion -100% trouvée actuellement sur Steam.\n\n"
                             "ℹ️ Je ne notifie que les jeux payants qui deviennent temporairement gratuits,\n"
                             "pas les jeux free-to-play de base (CS2, TF2, Dota 2, etc.)"
                    )
            return
        
        new_games = []
        for game in free_games:
            app_id = game['app_id']
            if not self.is_game_already_sent(app_id):
                new_games.append(game)
                self.mark_game_as_sent(app_id, game['name'])
        
        if not new_games:
            if manual_check and self.chat_ids:
                for chat_id in self.chat_ids:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text="🎮 Aucune nouvelle promotion -100% depuis la dernière vérification."
                    )
            return
        
        # Envoyer les nouveaux jeux à tous les chats enregistrés
        for chat_id in self.chat_ids:
            try:
                if len(new_games) == 1:
                    game = new_games[0]
                    message = (f"🎮 **Nouvelle promotion -100% sur Steam !**\n\n"
                             f"🎯 **{game['name']}**\n"
                             f"💰 Temporairement gratuit (normalement ${game['initial_price']:.2f})\n"
                             f"🔗 [Obtenir le jeu maintenant]({game['url']})\n\n"
                             f"⚡ **Promotion limitée dans le temps !**")
                else:
                    message = f"🎮 **{len(new_games)} nouvelles promotions -100% sur Steam !**\n\n"
                    for game in new_games:
                        message += (f"🎯 **{game['name']}**\n"
                                  f"💰 Temporairement gratuit (normalement ${game['initial_price']:.2f})\n"
                                  f"🔗 [Obtenir maintenant]({game['url']})\n\n")
                    message += "⚡ **Promotions limitées dans le temps !**"
                
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode='Markdown',
                    disable_web_page_preview=False
                )
                
            except Exception as e:
                logger.error(f"Erreur lors de l'envoi à {chat_id}: {e}")
        
        logger.info(f"Envoyé {len(new_games)} nouvelles promotions à {len(self.chat_ids)} chats")

# Instance globale du bot
steam_bot = SteamSalesBot()

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /start"""
    if not update.effective_chat or not update.message:
        return
        
    chat_id = update.effective_chat.id
    steam_bot.add_chat_id(chat_id)
    
    keyboard = [[InlineKeyboardButton("🔍 Vérifier maintenant", callback_data="check_games")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = """🎮 **Bienvenue sur Steam Sales Bot !**

Je vous notifierai automatiquement des jeux Steam en **vraie promotion -100%** (pas les jeux gratuits de base) tous les jours à 9h et 19h (heure de Paris).

⚡ **Ce que je surveille :**
• Jeux payants qui deviennent temporairement gratuits
• Promotions à -100% sur des jeux normalement payants
• Exclusion des jeux free-to-play de base (CS2, TF2, Dota 2, etc.)

🔍 **Vérification manuelle :** Utilisez le bouton ci-dessous ou `/check`

✅ Vous êtes maintenant inscrit aux notifications !"""
    
    await update.message.reply_text(
        message,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /check pour vérifier manuellement"""
    if not update.effective_chat or not update.message:
        return
        
    chat_id = update.effective_chat.id
    steam_bot.add_chat_id(chat_id)
    
    await update.message.reply_text("🔍 Vérification des promotions -100% en cours...")
    await steam_bot.send_free_games(context, manual_check=True)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestion des callbacks des boutons"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    if query.data == "check_games":
        if update.effective_chat:
            chat_id = update.effective_chat.id
            steam_bot.add_chat_id(chat_id)
        
        await query.edit_message_text("🔍 Vérification des promotions -100% en cours...")
        await steam_bot.send_free_games(context, manual_check=True)

def scheduled_check_sync():
    """Vérification programmée des jeux en promotion (version synchrone)"""
    logger.info("Vérification programmée des promotions -100%")
    try:
        free_games = steam_bot.get_free_games()
        if not free_games:
            logger.info("Aucune promotion disponible actuellement")
            return
            
        new_games = []
        for game in free_games:
            app_id = game['app_id']
            if not steam_bot.is_game_already_sent(app_id):
                new_games.append(game)
                steam_bot.mark_game_as_sent(app_id, game['name'])
        
        if not new_games:
            logger.info("Aucune nouvelle promotion trouvée")
            return
            
        if not steam_bot.chat_ids:
            logger.info("Aucun utilisateur inscrit pour recevoir les notifications")
            return
        
        # Envoyer les notifications automatiquement
        send_automatic_notifications(new_games)
        logger.info(f"Notifications envoyées pour {len(new_games)} nouveaux jeux")
        
    except Exception as e:
        logger.error(f"Erreur lors de la vérification programmée: {e}")

def send_automatic_notifications(new_games):
    """Envoie les notifications automatiques pour les nouveaux jeux"""
    import asyncio
    
    async def send_notifications():
        """Envoie les notifications de nouveaux jeux"""
        # Vérifier que le token existe
        if not TELEGRAM_TOKEN:
            logger.error("Token Telegram manquant pour les notifications automatiques")
            return

        bot = Bot(token=TELEGRAM_TOKEN)
        
        for chat_id in steam_bot.chat_ids:
            try:
                # Créer le message
                if len(new_games) == 1:
                    game = new_games[0]
                    message = (f"🎮 **Nouvelle promotion -100% sur Steam !**\n\n"
                             f"🎯 **{game['name']}**\n"
                             f"💰 Temporairement gratuit (normalement ${game['initial_price']:.2f})\n"
                             f"🔗 [Obtenir le jeu maintenant]({game['url']})\n\n"
                             f"⚡ **Promotion limitée dans le temps !**")
                else:
                    message = f"🎮 **{len(new_games)} nouvelles promotions -100% sur Steam !**\n\n"
                    for game in new_games:
                        message += (f"🎯 **{game['name']}**\n"
                                  f"💰 Temporairement gratuit (normalement ${game['initial_price']:.2f})\n"
                                  f"🔗 [Obtenir maintenant]({game['url']})\n\n")
                    message += "⚡ **Promotions limitées dans le temps !**"
                
                # Envoyer le message
                await bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode='Markdown',
                    disable_web_page_preview=False
                )
                
            except Exception as e:
                logger.error(f"Erreur lors de l'envoi à {chat_id}: {e}")
    
    # Exécuter les notifications
    try:
        asyncio.run(send_notifications())
        logger.info(f"Envoyé {len(new_games)} promotions à {len(steam_bot.chat_ids)} utilisateurs")
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi des notifications automatiques: {e}")

def main():
    """Fonction principale"""
    logger.info("Démarrage du Steam Sales Bot (vraies promotions uniquement)...")
    
    # Vérifier que le token est disponible
    if not TELEGRAM_TOKEN:
        logger.error("Token Telegram manquant - arrêt du service")
        return
    
    # Démarrer le serveur HTTP pour Render (en arrière-plan)
    http_thread = threading.Thread(target=start_http_server, daemon=True)
    http_thread.start()
    
    # Configuration et démarrage du bot Telegram
    telegram_working = False
    
    try:
        # Test simple de connexion sans créer l'application complète
        async def test_telegram_token():
            """Test rapide du token Telegram"""
            try:
                bot = Bot(token=TELEGRAM_TOKEN)
                bot_info = await bot.get_me()
                await bot.close()  # Fermer proprement la connexion
                logger.info(f"🤖 Bot Telegram disponible: @{bot_info.username}")
                logger.info(f"🔗 Lien du bot: https://t.me/{bot_info.username}")
                return True
            except Exception as e:
                logger.error(f"Erreur de test token: {e}")
                return False
        
        # Tester le token
        token_valid = asyncio.run(test_telegram_token())
        
        if token_valid:
            telegram_working = True
            logger.info("✅ Token Telegram validé")
            logger.info("� Commandes disponibles: /start, /check")
            logger.info("🌐 Interface web: https://steamsalesbot.onrender.com")
            logger.info("🔄 Bot Telegram sera démarré à la demande pour les commandes")
        else:
            raise Exception("Token Telegram invalide")
        
    except Exception as e:
        logger.warning(f"⚠️ Problème avec le bot Telegram: {e}")
        logger.info("🔔 Mode notifications automatiques uniquement")
        telegram_working = False
    
    # Configurer le scheduler pour les vérifications automatiques
    scheduler = BackgroundScheduler(timezone=TIMEZONE)
    
    # Programmer les vérifications à 9h et 19h (heure de Paris)
    scheduler.add_job(
        scheduled_check_sync,
        trigger=CronTrigger(hour=9, minute=0, timezone=TIMEZONE),
        id='morning_check',
        replace_existing=True
    )
    
    scheduler.add_job(
        scheduled_check_sync,
        trigger=CronTrigger(hour=19, minute=0, timezone=TIMEZONE),
        id='evening_check',
        replace_existing=True
    )

    # Démarrer le scheduler
    scheduler.start()
    logger.info("Scheduler démarré - Vérifications programmées à 9h et 19h (Europe/Paris)")

    # Initialiser l'application Telegram
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler('start', start_command))
    application.add_handler(CommandHandler('check', check_command))
    application.add_handler(CallbackQueryHandler(button_callback))

    try:
        logger.info("✅ Bot Steam Sales démarré avec succès !")
        logger.info("🔔 Les notifications automatiques sont actives")
        logger.info("📅 Prochaines vérifications: 9h et 19h (Europe/Paris)")

        if telegram_working:
            logger.info("📱 Bot Telegram opérationnel pour les notifications")
        else:
            logger.info("📱 Notifications uniquement (ajoutez votre chat_id manuellement)")

        # Faire une vérification initiale pour tester
        logger.info("🧪 Test initial de l'API Steam...")
        scheduled_check_sync()

        # Démarrer le bot Telegram
        application.run_polling()

    except KeyboardInterrupt:
        logger.info("Arrêt demandé par l'utilisateur")
    except Exception as e:
        logger.error(f"Erreur dans la boucle principale: {e}")
    finally:
        try:
            scheduler.shutdown()
        except Exception:
            pass
        logger.info("Bot arrêté proprement")

if __name__ == '__main__':
    main()
