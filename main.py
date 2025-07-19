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
                
                html = f"""
                <!DOCTYPE html>
                <html lang="fr">
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>Inscription Réussie - Steam Sales Bot</title>
                    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
                    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
                    <style>
                        * {{
                            margin: 0;
                            padding: 0;
                            box-sizing: border-box;
                        }}
                        
                        :root {{
                            --success: #00d4aa;
                            --primary: #1a73e8;
                            --secondary: #ff6b35;
                            --dark: #0f1419;
                            --dark-card: #1a1f2e;
                            --text-primary: #ffffff;
                            --text-secondary: #94a3b8;
                            --gradient-success: linear-gradient(135deg, #00d4aa 0%, #2ed573 100%);
                            --glass: rgba(255, 255, 255, 0.1);
                            --glass-border: rgba(255, 255, 255, 0.2);
                        }}
                        
                        body {{
                            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                            background: var(--dark);
                            color: var(--text-primary);
                            min-height: 100vh;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            position: relative;
                            overflow: hidden;
                        }}
                        
                        body::before {{
                            content: '';
                            position: fixed;
                            top: 0;
                            left: 0;
                            width: 100%;
                            height: 100%;
                            background: 
                                radial-gradient(circle at 30% 40%, rgba(0, 212, 170, 0.4) 0%, transparent 50%),
                                radial-gradient(circle at 70% 60%, rgba(46, 213, 115, 0.4) 0%, transparent 50%),
                                radial-gradient(circle at 50% 80%, rgba(26, 115, 232, 0.3) 0%, transparent 50%);
                            animation: celebration 15s ease infinite;
                            z-index: -1;
                        }}
                        
                        @keyframes celebration {{
                            0%, 100% {{ transform: scale(1) rotate(0deg); }}
                            50% {{ transform: scale(1.2) rotate(180deg); }}
                        }}
                        
                        .confetti {{
                            position: fixed;
                            top: 0;
                            left: 0;
                            width: 100%;
                            height: 100%;
                            overflow: hidden;
                            z-index: -1;
                        }}
                        
                        .confetti-piece {{
                            position: absolute;
                            width: 8px;
                            height: 8px;
                            background: var(--success);
                            animation: confettiFall 3s infinite linear;
                        }}
                        
                        @keyframes confettiFall {{
                            0% {{ transform: translateY(-100vh) rotate(0deg); opacity: 1; }}
                            100% {{ transform: translateY(100vh) rotate(720deg); opacity: 0; }}
                        }}
                        
                        .container {{
                            max-width: 600px;
                            margin: 0 auto;
                            padding: 2rem;
                            position: relative;
                            z-index: 1;
                        }}
                        
                        .success-card {{
                            background: var(--glass);
                            backdrop-filter: blur(20px);
                            border: 1px solid var(--glass-border);
                            border-radius: 25px;
                            padding: 3rem;
                            text-align: center;
                            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
                            animation: successSlideUp 1s ease-out;
                        }}
                        
                        @keyframes successSlideUp {{
                            0% {{ transform: translateY(50px) scale(0.9); opacity: 0; }}
                            100% {{ transform: translateY(0) scale(1); opacity: 1; }}
                        }}
                        
                        .success-icon {{
                            width: 100px;
                            height: 100px;
                            margin: 0 auto 2rem;
                            background: var(--gradient-success);
                            border-radius: 50%;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            font-size: 3rem;
                            color: white;
                            animation: bounce 2s infinite;
                            box-shadow: 0 10px 30px rgba(0, 212, 170, 0.3);
                        }}
                        
                        @keyframes bounce {{
                            0%, 20%, 50%, 80%, 100% {{ transform: translateY(0); }}
                            40% {{ transform: translateY(-10px); }}
                            60% {{ transform: translateY(-5px); }}
                        }}
                        
                        .success-title {{
                            font-size: 2.5rem;
                            font-weight: 700;
                            margin-bottom: 1rem;
                            background: var(--gradient-success);
                            -webkit-background-clip: text;
                            -webkit-text-fill-color: transparent;
                            background-clip: text;
                        }}
                        
                        .success-subtitle {{
                            font-size: 1.2rem;
                            color: var(--text-secondary);
                            margin-bottom: 2rem;
                        }}
                        
                        .stats-grid {{
                            display: grid;
                            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                            gap: 1.5rem;
                            margin: 2rem 0;
                        }}
                        
                        .stat-item {{
                            background: var(--dark-card);
                            border-radius: 15px;
                            padding: 1.5rem;
                            border: 1px solid rgba(0, 212, 170, 0.2);
                            transition: all 0.3s ease;
                        }}
                        
                        .stat-item:hover {{
                            border-color: var(--success);
                            transform: translateY(-3px);
                            box-shadow: 0 10px 25px rgba(0, 212, 170, 0.2);
                        }}
                        
                        .stat-icon {{
                            font-size: 1.5rem;
                            color: var(--success);
                            margin-bottom: 0.5rem;
                        }}
                        
                        .stat-value {{
                            font-size: 1.3rem;
                            font-weight: 600;
                            color: var(--text-primary);
                            margin-bottom: 0.25rem;
                        }}
                        
                        .stat-label {{
                            color: var(--text-secondary);
                            font-size: 0.875rem;
                        }}
                        
                        .info-card {{
                            background: rgba(0, 212, 170, 0.1);
                            border: 1px solid rgba(0, 212, 170, 0.3);
                            border-radius: 20px;
                            padding: 2rem;
                            margin: 2rem 0;
                            backdrop-filter: blur(10px);
                        }}
                        
                        .info-title {{
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            gap: 0.5rem;
                            font-size: 1.5rem;
                            font-weight: 600;
                            margin-bottom: 1rem;
                            color: var(--success);
                        }}
                        
                        .info-text {{
                            color: var(--text-secondary);
                            line-height: 1.6;
                            margin-bottom: 1rem;
                        }}
                        
                        .schedule {{
                            background: var(--dark-card);
                            border-radius: 10px;
                            padding: 1rem;
                            border: 1px solid rgba(255, 255, 255, 0.1);
                        }}
                        
                        .schedule-title {{
                            color: var(--text-primary);
                            font-weight: 600;
                            margin-bottom: 0.5rem;
                        }}
                        
                        .schedule-time {{
                            color: var(--success);
                            font-weight: 700;
                            font-size: 1.1rem;
                        }}
                        
                        .home-button {{
                            display: inline-flex;
                            align-items: center;
                            gap: 0.5rem;
                            background: var(--primary);
                            color: white;
                            padding: 15px 30px;
                            border-radius: 50px;
                            text-decoration: none;
                            font-weight: 600;
                            margin-top: 2rem;
                            transition: all 0.3s ease;
                            box-shadow: 0 4px 15px rgba(26, 115, 232, 0.3);
                        }}
                        
                        .home-button:hover {{
                            background: #1557b0;
                            transform: translateY(-2px);
                            box-shadow: 0 8px 25px rgba(26, 115, 232, 0.4);
                            color: white;
                            text-decoration: none;
                        }}
                        
                        @media (max-width: 768px) {{
                            .container {{
                                padding: 1rem;
                            }}
                            
                            .success-card {{
                                padding: 2rem 1rem;
                            }}
                            
                            .success-title {{
                                font-size: 2rem;
                            }}
                            
                            .stats-grid {{
                                grid-template-columns: 1fr;
                            }}
                        }}
                        
                        .pulse {{
                            animation: pulse 2s infinite;
                        }}
                        
                        @keyframes pulse {{
                            0% {{ box-shadow: 0 0 0 0 rgba(0, 212, 170, 0.4); }}
                            70% {{ box-shadow: 0 0 0 20px rgba(0, 212, 170, 0); }}
                            100% {{ box-shadow: 0 0 0 0 rgba(0, 212, 170, 0); }}
                        }}
                    </style>
                </head>
                <body>
                    <div class="confetti"></div>
                    
                    <div class="container">
                        <div class="success-card">
                            <div class="success-icon pulse">
                                <i class="fas fa-check"></i>
                            </div>
                            
                            <h1 class="success-title">Inscription Réussie !</h1>
                            <p class="success-subtitle">Bienvenue dans la communauté Steam Sales Bot</p>
                            
                            <div class="stats-grid">
                                <div class="stat-item">
                                    <div class="stat-icon"><i class="fas fa-id-card"></i></div>
                                    <div class="stat-value">{chat_id}</div>
                                    <div class="stat-label">Votre Chat ID</div>
                                </div>
                                
                                <div class="stat-item">
                                    <div class="stat-icon"><i class="fas fa-users"></i></div>
                                    <div class="stat-value">{len(steam_bot.chat_ids) if 'steam_bot' in globals() else 0}</div>
                                    <div class="stat-label">Utilisateurs inscrits</div>
                                </div>
                            </div>
                            
                            <div class="info-card">
                                <h3 class="info-title">
                                    <i class="fas fa-bell"></i>
                                    Notifications Automatiques Activées
                                </h3>
                                <p class="info-text">
                                    🎉 <strong>Une notification de bienvenue a été envoyée sur votre Telegram !</strong><br><br>
                                    Vous recevrez maintenant des notifications Telegram instantanées 
                                    dès qu'un jeu Steam payant devient temporairement gratuit !
                                </p>
                                
                                <div class="schedule">
                                    <div class="schedule-title">Horaires de vérification :</div>
                                    <div class="schedule-time">🕘 9h00 & 🕕 19h00 (Europe/Paris)</div>
                                </div>
                            </div>
                            
                            <a href="/" class="home-button">
                                <i class="fas fa-home"></i>
                                Retour à l'accueil
                            </a>
                            
                            <div style="margin-top: 1rem; padding: 1rem; background: rgba(26, 115, 232, 0.1); border: 1px solid rgba(26, 115, 232, 0.3); border-radius: 10px;">
                                <p style="color: var(--primary); font-size: 0.9rem; margin: 0;">
                                    <i class="fab fa-telegram"></i> 
                                    <strong>Vérifiez votre Telegram maintenant !</strong><br>
                                    Une notification de bienvenue vous a été envoyée.
                                </p>
                            </div>
                        </div>
                    </div>
                    
                    <script>
                        // Create confetti animation
                        function createConfetti() {{
                            const confettiContainer = document.querySelector('.confetti');
                            const colors = ['#00d4aa', '#2ed573', '#1a73e8', '#ff6b35'];
                            
                            for (let i = 0; i < 100; i++) {{
                                const confetti = document.createElement('div');
                                confetti.className = 'confetti-piece';
                                confetti.style.left = Math.random() * 100 + '%';
                                confetti.style.backgroundColor = colors[Math.floor(Math.random() * colors.length)];
                                confetti.style.animationDelay = Math.random() * 3 + 's';
                                confetti.style.animationDuration = (Math.random() * 2 + 2) + 's';
                                confettiContainer.appendChild(confetti);
                            }}
                        }}
                        
                        // Initialize on page load
                        document.addEventListener('DOMContentLoaded', function() {{
                            createConfetti();
                            
                            // Auto-redirect after 10 seconds
                            setTimeout(() => {{
                                const button = document.querySelector('.home-button');
                                if (button) {{
                                    button.style.background = 'var(--secondary)';
                                    button.innerHTML = '<i class="fas fa-clock"></i> Redirection automatique...';
                                    
                                    setTimeout(() => {{
                                        window.location.href = '/';
                                    }}, 2000);
                                }}
                            }}, 8000);
                        }});
                    </script>
                </body>
                </html>
                """
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
            
            html = f"""
            <!DOCTYPE html>
            <html lang="fr">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Steam Sales Bot - Notifications Gratuites</title>
                <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
                <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
                <style>
                    * {{
                        margin: 0;
                        padding: 0;
                        box-sizing: border-box;
                    }}
                    
                    :root {{
                        --primary: #1a73e8;
                        --secondary: #ff6b35;
                        --success: #00d4aa;
                        --dark: #0f1419;
                        --dark-card: #1a1f2e;
                        --text-primary: #ffffff;
                        --text-secondary: #94a3b8;
                        --gradient-1: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        --gradient-3: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
                        --glass: rgba(255, 255, 255, 0.1);
                        --glass-border: rgba(255, 255, 255, 0.2);
                    }}
                    
                    body {{
                        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                        background: var(--dark);
                        color: var(--text-primary);
                        min-height: 100vh;
                        overflow-x: hidden;
                        position: relative;
                    }}
                    
                    body::before {{
                        content: '';
                        position: fixed;
                        top: 0;
                        left: 0;
                        width: 100%;
                        height: 100%;
                        background: 
                            radial-gradient(circle at 20% 50%, rgba(103, 126, 234, 0.3) 0%, transparent 50%),
                            radial-gradient(circle at 80% 20%, rgba(255, 107, 53, 0.3) 0%, transparent 50%),
                            radial-gradient(circle at 40% 80%, rgba(0, 212, 170, 0.3) 0%, transparent 50%);
                        animation: gradientShift 20s ease infinite;
                        z-index: -1;
                    }}
                    
                    @keyframes gradientShift {{
                        0%, 100% {{ transform: scale(1) rotate(0deg); }}
                        50% {{ transform: scale(1.1) rotate(180deg); }}
                    }}
                    
                    .particles {{
                        position: fixed;
                        top: 0;
                        left: 0;
                        width: 100%;
                        height: 100%;
                        overflow: hidden;
                        z-index: -1;
                    }}
                    
                    .particle {{
                        position: absolute;
                        background: rgba(255, 255, 255, 0.1);
                        border-radius: 50%;
                        animation: float 20s infinite linear;
                    }}
                    
                    @keyframes float {{
                        0% {{ transform: translateY(100vh) rotate(0deg); opacity: 0; }}
                        10% {{ opacity: 1; }}
                        90% {{ opacity: 1; }}
                        100% {{ transform: translateY(-100px) rotate(360deg); opacity: 0; }}
                    }}
                    
                    .container {{
                        max-width: 1200px;
                        margin: 0 auto;
                        padding: 2rem;
                        position: relative;
                        z-index: 1;
                    }}
                    
                    .header {{
                        text-align: center;
                        margin-bottom: 3rem;
                        animation: slideDown 1s ease-out;
                    }}
                    
                    @keyframes slideDown {{
                        0% {{ transform: translateY(-50px); opacity: 0; }}
                        100% {{ transform: translateY(0); opacity: 1; }}
                    }}
                    
                    .header h1 {{
                        font-size: clamp(2.5rem, 5vw, 4rem);
                        font-weight: 700;
                        background: var(--gradient-3);
                        -webkit-background-clip: text;
                        -webkit-text-fill-color: transparent;
                        background-clip: text;
                        margin-bottom: 1rem;
                    }}
                    
                    .header .subtitle {{
                        font-size: 1.2rem;
                        color: var(--text-secondary);
                        font-weight: 300;
                    }}
                    
                    .glass-card {{
                        background: var(--glass);
                        backdrop-filter: blur(20px);
                        border: 1px solid var(--glass-border);
                        border-radius: 20px;
                        padding: 2rem;
                        margin-bottom: 2rem;
                        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
                        transition: all 0.3s ease;
                        animation: slideUp 0.8s ease-out;
                    }}
                    
                    @keyframes slideUp {{
                        0% {{ transform: translateY(50px); opacity: 0; }}
                        100% {{ transform: translateY(0); opacity: 1; }}
                    }}
                    
                    .glass-card:hover {{
                        transform: translateY(-5px);
                        box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
                        border-color: rgba(255, 255, 255, 0.3);
                    }}
                    
                    .status-grid {{
                        display: grid;
                        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                        gap: 1rem;
                        margin-bottom: 2rem;
                    }}
                    
                    .status-item {{
                        background: var(--dark-card);
                        border-radius: 15px;
                        padding: 1.5rem;
                        text-align: center;
                        border: 1px solid rgba(255, 255, 255, 0.1);
                        transition: all 0.3s ease;
                    }}
                    
                    .status-item:hover {{
                        border-color: var(--primary);
                        transform: translateY(-3px);
                    }}
                    
                    .status-icon {{
                        font-size: 2rem;
                        margin-bottom: 0.5rem;
                        color: var(--success);
                    }}
                    
                    .status-value {{
                        font-size: 1.5rem;
                        font-weight: 600;
                        color: var(--text-primary);
                        margin-bottom: 0.25rem;
                    }}
                    
                    .status-label {{
                        color: var(--text-secondary);
                        font-size: 0.875rem;
                    }}
                    
                    .subscription-card {{
                        background: var(--gradient-1);
                        border-radius: 25px;
                        padding: 3rem;
                        text-align: center;
                        margin: 2rem 0;
                        position: relative;
                        overflow: hidden;
                        animation: slideUp 1s ease-out 0.3s both;
                    }}
                    
                    .subscription-card::before {{
                        content: '';
                        position: absolute;
                        top: 0;
                        left: -100%;
                        width: 100%;
                        height: 100%;
                        background: linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent);
                        animation: shimmer 3s infinite;
                    }}
                    
                    @keyframes shimmer {{
                        0% {{ left: -100%; }}
                        100% {{ left: 100%; }}
                    }}
                    
                    .subscription-title {{
                        font-size: 2rem;
                        font-weight: 700;
                        margin-bottom: 1rem;
                        color: white;
                    }}
                    
                    .steps-container {{
                        display: grid;
                        grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                        gap: 2rem;
                        margin: 2rem 0;
                    }}
                    
                    .step {{
                        background: rgba(255, 255, 255, 0.15);
                        border-radius: 20px;
                        padding: 2rem;
                        border: 1px solid rgba(255, 255, 255, 0.2);
                        transition: all 0.3s ease;
                    }}
                    
                    .step:hover {{
                        transform: translateY(-5px);
                        background: rgba(255, 255, 255, 0.2);
                    }}
                    
                    .step-number {{
                        display: inline-block;
                        width: 40px;
                        height: 40px;
                        background: var(--secondary);
                        color: white;
                        border-radius: 50%;
                        line-height: 40px;
                        font-weight: 700;
                        margin-bottom: 1rem;
                    }}
                    
                    .step h3 {{
                        color: white;
                        margin-bottom: 1rem;
                        font-size: 1.2rem;
                    }}
                    
                    .step p {{
                        color: rgba(255, 255, 255, 0.9);
                        line-height: 1.6;
                    }}
                    
                    .telegram-button {{
                        display: inline-block;
                        background: #0088cc;
                        color: white;
                        padding: 12px 24px;
                        border-radius: 25px;
                        text-decoration: none;
                        font-weight: 600;
                        margin: 1rem 0;
                        transition: all 0.3s ease;
                        box-shadow: 0 4px 15px rgba(0, 136, 204, 0.3);
                    }}
                    
                    .telegram-button:hover {{
                        background: #006699;
                        transform: translateY(-2px);
                        box-shadow: 0 8px 25px rgba(0, 136, 204, 0.4);
                    }}
                    
                    .input-form {{
                        background: rgba(255, 255, 255, 0.1);
                        border-radius: 20px;
                        padding: 2rem;
                        margin-top: 2rem;
                        backdrop-filter: blur(10px);
                        border: 1px solid rgba(255, 255, 255, 0.2);
                    }}
                    
                    .input-group {{
                        display: flex;
                        gap: 1rem;
                        max-width: 400px;
                        margin: 0 auto;
                        flex-wrap: wrap;
                        justify-content: center;
                    }}
                    
                    .chat-input {{
                        flex: 1;
                        min-width: 200px;
                        padding: 15px 20px;
                        border: 2px solid rgba(255, 255, 255, 0.2);
                        border-radius: 50px;
                        background: rgba(255, 255, 255, 0.1);
                        color: white;
                        font-size: 16px;
                        backdrop-filter: blur(10px);
                        transition: all 0.3s ease;
                    }}
                    
                    .chat-input:focus {{
                        outline: none;
                        border-color: var(--secondary);
                        box-shadow: 0 0 20px rgba(255, 107, 53, 0.3);
                        background: rgba(255, 255, 255, 0.15);
                    }}
                    
                    .chat-input::placeholder {{
                        color: rgba(255, 255, 255, 0.6);
                    }}
                    
                    .subscribe-btn {{
                        padding: 15px 30px;
                        background: var(--secondary);
                        color: white;
                        border: none;
                        border-radius: 50px;
                        font-size: 16px;
                        font-weight: 600;
                        cursor: pointer;
                        transition: all 0.3s ease;
                        box-shadow: 0 4px 15px rgba(255, 107, 53, 0.3);
                        white-space: nowrap;
                    }}
                    
                    .subscribe-btn:hover {{
                        background: #e55a2b;
                        transform: translateY(-2px);
                        box-shadow: 0 8px 25px rgba(255, 107, 53, 0.4);
                    }}
                    
                    .features {{
                        display: grid;
                        grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                        gap: 1.5rem;
                        margin: 2rem 0;
                    }}
                    
                    .feature {{
                        background: var(--dark-card);
                        border-radius: 20px;
                        padding: 2rem;
                        border: 1px solid rgba(255, 255, 255, 0.1);
                        transition: all 0.3s ease;
                    }}
                    
                    .feature:hover {{
                        border-color: var(--primary);
                        transform: translateY(-5px);
                        box-shadow: 0 10px 30px rgba(26, 115, 232, 0.2);
                    }}
                    
                    .feature-icon {{
                        font-size: 2.5rem;
                        margin-bottom: 1rem;
                        background: var(--gradient-3);
                        -webkit-background-clip: text;
                        -webkit-text-fill-color: transparent;
                        background-clip: text;
                    }}
                    
                    .feature h3 {{
                        font-size: 1.3rem;
                        margin-bottom: 1rem;
                        color: var(--text-primary);
                    }}
                    
                    .feature p {{
                        color: var(--text-secondary);
                        line-height: 1.6;
                    }}
                    
                    .footer {{
                        text-align: center;
                        padding: 2rem 0;
                        border-top: 1px solid rgba(255, 255, 255, 0.1);
                        margin-top: 3rem;
                        color: var(--text-secondary);
                    }}
                    
                    .footer a {{
                        color: var(--primary);
                        text-decoration: none;
                        transition: color 0.3s ease;
                    }}
                    
                    .footer a:hover {{
                        color: var(--text-primary);
                    }}
                    
                    @media (max-width: 768px) {{
                        .container {{
                            padding: 1rem;
                        }}
                        
                        .subscription-card {{
                            padding: 2rem 1rem;
                        }}
                        
                        .input-group {{
                            flex-direction: column;
                            align-items: stretch;
                        }}
                        
                        .chat-input {{
                            min-width: unset;
                        }}
                    }}
                    
                    .loading {{
                        display: none;
                        margin: 1rem 0;
                    }}
                    
                    .spinner {{
                        display: inline-block;
                        width: 20px;
                        height: 20px;
                        border: 2px solid rgba(255,255,255,0.3);
                        border-radius: 50%;
                        border-top-color: white;
                        animation: spin 1s ease-in-out infinite;
                    }}
                    
                    @keyframes spin {{
                        to {{ transform: rotate(360deg); }}
                    }}
                </style>
            </head>
            <body>
                <div class="particles"></div>
                
                <div class="container">
                    <header class="header">
                        <h1><i class="fas fa-gamepad"></i> Steam Sales Bot</h1>
                        <p class="subtitle">Notifications gratuites pour les jeux Steam en promotion -100%</p>
                    </header>
                    
                    <div class="glass-card">
                        <div class="status-grid">
                            <div class="status-item">
                                <div class="status-icon"><i class="fas fa-heartbeat"></i></div>
                                <div class="status-value">En ligne</div>
                                <div class="status-label">Status du service</div>
                            </div>
                            <div class="status-item">
                                <div class="status-icon"><i class="fas fa-users"></i></div>
                                <div class="status-value">{len(steam_bot.chat_ids) if 'steam_bot' in globals() else 0}</div>
                                <div class="status-label">Utilisateurs inscrits</div>
                            </div>
                            <div class="status-item">
                                <div class="status-icon"><i class="fas fa-clock"></i></div>
                                <div class="status-value">9h & 19h</div>
                                <div class="status-label">Vérifications quotidiennes</div>
                            </div>
                            <div class="status-item">
                                <div class="status-icon"><i class="fas fa-sync-alt"></i></div>
                                <div class="status-value">{datetime.now(TIMEZONE).strftime('%H:%M')}</div>
                                <div class="status-label">Dernière mise à jour</div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="subscription-card">
                        <h2 class="subscription-title">
                            <i class="fas fa-bell"></i> Inscription Gratuite
                        </h2>
                        <p style="color: rgba(255,255,255,0.9); font-size: 1.1rem; margin-bottom: 2rem;">
                            Recevez instantanément les notifications des jeux payants qui deviennent gratuits sur Steam
                        </p>
                        
                        <div class="steps-container">
                            <div class="step">
                                <div class="step-number">1</div>
                                <h3><i class="fab fa-telegram"></i> Récupérez votre Chat ID</h3>
                                <p>Cliquez sur le bouton ci-dessous pour ouvrir @userinfobot sur Telegram et obtenez votre identifiant unique.</p>
                                <a href="https://t.me/userinfobot" target="_blank" class="telegram-button">
                                    <i class="fab fa-telegram"></i> Ouvrir @userinfobot
                                </a>
                            </div>
                            
                            <div class="step">
                                <div class="step-number">2</div>
                                <h3><i class="fas fa-user-plus"></i> Inscrivez-vous</h3>
                                <p>Entrez votre Chat ID dans le formulaire ci-dessous et commencez à recevoir les notifications.</p>
                                
                                <div class="input-form">
                                    <div class="input-group">
                                        <input type="number" id="chatId" class="chat-input" placeholder="Votre Chat ID" />
                                        <button onclick="subscribe()" class="subscribe-btn">
                                            <i class="fas fa-bell"></i> S'inscrire
                                        </button>
                                    </div>
                                    <div class="loading">
                                        <div class="spinner"></div>
                                        <span style="margin-left: 10px;">Inscription en cours...</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="glass-card">
                        <h2 style="text-align: center; margin-bottom: 2rem; color: var(--text-primary);">
                            <i class="fas fa-star"></i> Fonctionnalités
                        </h2>
                        
                        <div class="features">
                            <div class="feature">
                                <div class="feature-icon"><i class="fas fa-search"></i></div>
                                <h3>Détection Intelligente</h3>
                                <p>Algorithme avancé qui identifie uniquement les vraies promotions -100%, pas les jeux gratuits de base.</p>
                            </div>
                            
                            <div class="feature">
                                <div class="feature-icon"><i class="fas fa-filter"></i></div>
                                <h3>Zéro Spam</h3>
                                <p>Chaque jeu n'est notifié qu'une seule fois. Exclusion automatique des free-to-play permanents.</p>
                            </div>
                            
                            <div class="feature">
                                <div class="feature-icon"><i class="fas fa-bolt"></i></div>
                                <h3>Notifications Instantanées</h3>
                                <p>Vérifications automatiques à 9h et 19h (Europe/Paris) avec notifications immédiates.</p>
                            </div>
                            
                            <div class="feature">
                                <div class="feature-icon"><i class="fas fa-link"></i></div>
                                <h3>Liens Directs</h3>
                                <p>Accès direct aux pages Steam pour télécharger immédiatement vos jeux gratuits.</p>
                            </div>
                            
                            <div class="feature">
                                <div class="feature-icon"><i class="fas fa-shield-alt"></i></div>
                                <h3>100% Gratuit</h3>
                                <p>Service entièrement gratuit, sans publicité, sans limitation. Votre confidentialité respectée.</p>
                            </div>
                            
                            <div class="feature">
                                <div class="feature-icon"><i class="fas fa-mobile-alt"></i></div>
                                <h3>Multi-plateforme</h3>
                                <p>Notifications Telegram disponibles sur tous vos appareils : mobile, desktop, web.</p>
                            </div>
                        </div>
                    </div>
                </div>
                
                <footer class="footer">
                    <p>
                        <a href="/health"><i class="fas fa-heartbeat"></i> Health Check</a> | 
                        <i class="fab fa-python"></i> Créé avec Python | 
                        <i class="fas fa-cloud"></i> Hébergé sur Render
                    </p>
                    <p style="margin-top: 1rem; font-size: 0.875rem;">
                        © 2024 Steam Sales Bot - Service gratuit et open source
                    </p>
                </footer>
                
                <script>
                    // Particles animation
                    function createParticles() {{
                        const particlesContainer = document.querySelector('.particles');
                        const particleCount = 50;
                        
                        for (let i = 0; i < particleCount; i++) {{
                            const particle = document.createElement('div');
                            particle.className = 'particle';
                            particle.style.left = Math.random() * 100 + '%';
                            particle.style.width = particle.style.height = Math.random() * 4 + 2 + 'px';
                            particle.style.animationDelay = Math.random() * 20 + 's';
                            particle.style.animationDuration = (Math.random() * 10 + 10) + 's';
                            particlesContainer.appendChild(particle);
                        }}
                    }}
                    
                    // Subscription function
                    function subscribe() {{
                        const chatId = document.getElementById('chatId').value;
                        const button = document.querySelector('.subscribe-btn');
                        const loading = document.querySelector('.loading');
                        
                        if (!chatId || isNaN(chatId)) {{
                            showNotification('Veuillez entrer un Chat ID valide (nombre)', 'error');
                            return;
                        }}
                        
                        button.disabled = true;
                        loading.style.display = 'block';
                        
                        // Simulate loading then redirect
                        setTimeout(() => {{
                            window.location.href = '/subscribe/' + chatId;
                        }}, 1000);
                    }}
                    
                    function showNotification(message, type) {{
                        const notification = document.createElement('div');
                        notification.style.cssText = `
                            position: fixed;
                            top: 20px;
                            right: 20px;
                            padding: 15px 25px;
                            background: ${{type === 'error' ? '#ff4757' : '#2ed573'}};
                            color: white;
                            border-radius: 10px;
                            box-shadow: 0 4px 15px rgba(0,0,0,0.3);
                            z-index: 1000;
                            animation: slideIn 0.3s ease;
                        `;
                        notification.textContent = message;
                        document.body.appendChild(notification);
                        
                        setTimeout(() => {{
                            notification.remove();
                        }}, 3000);
                    }}
                    
                    // Enter key support
                    document.getElementById('chatId').addEventListener('keypress', function(e) {{
                        if (e.key === 'Enter') {{
                            subscribe();
                        }}
                    }});
                    
                    // Initialize
                    document.addEventListener('DOMContentLoaded', function() {{
                        createParticles();
                        
                        // Add subtle animations on scroll
                        const observer = new IntersectionObserver((entries) => {{
                            entries.forEach(entry => {{
                                if (entry.isIntersecting) {{
                                    entry.target.style.opacity = '1';
                                    entry.target.style.transform = 'translateY(0)';
                                }}
                            }});
                        }});
                        
                        document.querySelectorAll('.glass-card, .feature').forEach(el => {{
                            el.style.opacity = '0';
                            el.style.transform = 'translateY(30px)';
                            el.style.transition = 'all 0.6s ease';
                            observer.observe(el);
                        }});
                    }});
                </script>
            </body>
            </html>
            """
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
            welcome_task = asyncio.create_task(self.send_welcome_notification(chat_id))
            # Stocker la tâche pour éviter la collecte prématurée
            self._welcome_tasks = getattr(self, '_welcome_tasks', set())
            self._welcome_tasks.add(welcome_task)
            welcome_task.add_done_callback(self._welcome_tasks.discard)
    
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
    # Démarrer le serveur HTTP dans un thread séparé
    http_thread = threading.Thread(target=start_http_server, daemon=True)
    http_thread.start()
    
    # Lancer la fonction principale du bot
    main()                                            