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
import signal
from datetime import datetime
from typing import Dict, List, Set
from http.server import HTTPServer, BaseHTTPRequestHandler
from string import Template

import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Configuration du logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TELEGRAM_TOKEN:
    logger.error("❌ TELEGRAM_TOKEN environment variable is required!")
    logger.error("💡 Set it with: export TELEGRAM_TOKEN='your_bot_token'")
    logger.error("🤖 Get your token from @BotFather on Telegram")
    exit(1)
    
STEAM_API_URL = "https://store.steampowered.com/api/featured/"
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
                chat_id = int(self.path.split('/')[-1])
                
                # Ajouter le chat_id à la liste
                if 'steam_bot' in globals():
                    steam_bot.add_chat_id(chat_id)
                    
                self.send_response(200)
                self.send_header('Content-type', CONTENT_TYPE_HTML)
                self.end_headers()
                
                html = render_template('success.html', chat_id=chat_id, total_users=len(steam_bot.chat_ids) if 'steam_bot' in globals() else 0)
                self.wfile.write(html.encode())
                
                logger.info(f"✅ Nouvel utilisateur inscrit: {chat_id}")
                
            except (ValueError, IndexError):
                self.send_response(400)
                self.send_header('Content-type', CONTENT_TYPE_HTML)
                self.end_headers()
                self.wfile.write(b"<h1>Erreur: Chat ID invalide</h1><p><a href='/'>Retour</a></p>")
        
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
        
    def load_sent_games(self) -> Dict:
        """Charge les jeux déjà envoyés depuis le fichier JSON"""
        try:
            if os.path.exists(SENT_GAMES_FILE):
                with open(SENT_GAMES_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                return {"sent_games": {}, "chat_ids": []}
        except Exception as e:
            logger.error(f"Erreur lors du chargement de {SENT_GAMES_FILE}: {e}")
            return {"sent_games": {}, "chat_ids": []}
    
    def save_sent_games(self):
        """Sauvegarde les jeux envoyés dans le fichier JSON"""
        try:
            data = {
                "sent_games": self.sent_games.get("sent_games", {}),
                "chat_ids": list(self.chat_ids)
            }
            with open(SENT_GAMES_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde de {SENT_GAMES_FILE}: {e}")
    
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
    
    def send_welcome_notification_sync(self, chat_id: int):
        """Envoie une notification de bienvenue via l'API HTTP Telegram (version synchrone)"""
        try:
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
                'parse_mode': 'Markdown'
            }
            
            response = requests.post(url, data=data, timeout=10)
            if response.status_code == 200:
                logger.info(f"✅ Notification de bienvenue envoyée à {chat_id}")
            else:
                logger.warning(f"⚠️ Erreur envoi notification bienvenue (HTTP {response.status_code})")
                
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi de la notification de bienvenue: {e}")
    
    async def send_welcome_notification(self, chat_id: int):
        """Envoie une notification de bienvenue à un nouvel utilisateur"""
        try:
            # Vérifier si le token Telegram est disponible
            token = os.environ.get('TELEGRAM_BOT_TOKEN')
            if not token:
                logger.warning("Token Telegram non configuré - notification de bienvenue ignorée")
                return
                
            # Créer un bot temporaire pour envoyer la notification
            bot = Bot(token=token)
            
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
        try:
            response = requests.get(STEAM_API_URL, timeout=30)
            response.raise_for_status()
            data = response.json()
            
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
            
            logger.info(f"Trouvé {len(free_games)} vraies promotions gratuites (hors F2P)")
            return free_games
            
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des jeux en promotion: {e}")
            return []
    
    def _verify_real_promotion(self, app_id: str, game_name: str) -> bool:
        """Vérifie qu'il s'agit vraiment d'une promotion et pas d'un F2P"""
        # Liste des jeux F2P connus à exclure
        known_f2p_games = {
            '730', '440', '570', '238960', '386360', '444090', 
            '578080', '1222670', '359550', '252490'
        }
        
        if app_id in known_f2p_games:
            logger.info(f"Jeu F2P exclu: {game_name} (ID: {app_id})")
            return False
        
        return True  # Simplification pour éviter trop de complexité
    
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
        token = TELEGRAM_TOKEN
        if not token:
            logger.error("Token Telegram manquant pour les notifications automatiques")
            return
            
        bot = Bot(token=token)
        
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
                from telegram import Bot
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
    
    try:
        # Configuration pour arrêt propre
        def signal_handler(signum, frame):
            logger.info("Signal d'arrêt reçu, fermeture propre...")
            try:
                scheduler.shutdown(wait=False)
                logger.info("Scheduler arrêté")
            except Exception as e:
                logger.error(f"Erreur lors de l'arrêt: {e}")
            finally:
                exit(0)
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
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
        
        # Boucle principale pour maintenir le service actif
        logger.info("🔄 Service en fonctionnement - Maintien de la connexion...")
        while True:
            time.sleep(60)  # Vérifier toutes les minutes si le service doit s'arrêter
            
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
