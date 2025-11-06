import os
import re
import sys
import json
import time
import uuid
import random
import asyncio
import socket
import sqlite3
import requests
import datetime
import threading
import subprocess
from uuid import uuid4
from collections import deque, defaultdict
from datetime import timedelta
from typing import Dict, Any, Optional, List
from instagrapi import Client
from telethon.errors import FloodWaitError
from urllib.parse import urlparse, unquote, parse_qs
from telethon import TelegramClient, events, errors 
from rich import box
from rich.text import Text
from rich.table import Table
from rich.align import Align
from rich.panel import Panel
from rich.console import Console
import logging
logging.basicConfig(level=logging.CRITICAL)
from ts_driver import (lire_licence, get_device_infos_from_db, verifier_licence_en_ligne, afficher_temps_abonnement, supprimer_id, verrouillage)
from instagrapi.exceptions import (
    FeedbackRequired,
    LoginRequired,
    PleaseWaitFewMinutes,
    ChallengeRequired,
    TwoFactorRequired,
)
console = Console()

import importlib

n = "2"
c = "3"
d = int(c) + 1
q = int(n) - 1
module_name = f"ig_{q}"
module = importlib.import_module(module_name) 
save_device_settings = getattr(module, "save_device_settings")
profile = getattr(module, "generate_profile")

t = 4
follower_count = 1000
like_count = 1000

# --- Fonction pour récupérer le chemin du script ou executable ---
def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return Path(__file__).resolve().parent

BASE_DIR = os.path.join(os.environ.get("PREFIX", "/data/data/com.termux/files/usr"), "com.termux", "home", ".useuser", "unknown_folder")
CONFIG_DIR = os.path.join(BASE_DIR, "configuration")
SESSION_DIR = os.path.join(BASE_DIR, "ig_sessions")
IG_ERROR_DIR = os.path.join(SESSION_DIR, "all_error")
SETTING_DIR = os.path.join(SESSION_DIR, "settings")

IG_ACCOUNTS_FILE = os.path.join(CONFIG_DIR, f"ig{n}.json")
USER_SPACE_DIR = os.path.join(BASE_DIR, "utilisateurs")
SELECTED_USER_FILE = os.path.join(USER_SPACE_DIR, f"selected_user{n}.json")
TELEGRAM_DIR = os.path.join(BASE_DIR, f"telegram_user{n}")
TELEGRAM_SESSION_FILE = os.path.join(TELEGRAM_DIR, f"tg_session{n}")
TELEGRAM_API_FILE = os.path.join(TELEGRAM_DIR, f"telegram_api{n}.json")
BLOCK_FILE = os.path.join(IG_ERROR_DIR, f"blocked{c}.json")
BLOCK_FILE2 = os.path.join(IG_ERROR_DIR, f"blocked{d}.json")
VIP_DB_FILE = os.path.join(CONFIG_DIR, "vip_data.db") 

# --- Lecture du fichier set_ts.json si existant ---
SET_TS_DIR = os.path.join(BASE_DIR, "setting")
DB_PATH = os.path.join(SET_TS_DIR, "quota.db")
SET_TS_PATH = os.path.join(SET_TS_DIR, f"set_ts{n}.json")

def counter():
    global t, follower_count, like_count
    if os.path.exists(SET_TS_PATH):
        try:
            with open(SET_TS_PATH, "r") as f:
                config_data = json.load(f)
                # Utilisation du délai si existant
                t = float(config_data.get("speed_seconds", t))
                follower_count = int(config_data.get("followers_per_hour", follower_count))
                like_count = int(config_data.get("likes_per_hour", like_count))
        except Exception as e:
            console.print(f"[red]❌ Erreur lors de la lecture du JSON : {e}[/red]")
    return t, follower_count, like_count

last_username = None
last_bot_msg_time = None
pending_comment = None
send_lock = asyncio.Lock()
last_messages_sent = deque(maxlen=5)
last_back_time = None
insta_task_queue = asyncio.Queue()
processing_insta_task = False
waiting_for_username = False
last_completed_key = None
last_sent_type = None
last_sent_time = 0
MIN_MSG_INTERVAL = 0.03
BLOCK_DURATION_MINUTES = 24 * 3600
BLOCK_DURATION_MINUTES2 = 10080
max_retry = 5
last_action_time = {}
last_message_sent_to_bot = None
last_sent_time_to_bot = 0
last_account_print_time = 0
last_bot_message_text = ""
FIX_HISTORY_TIMEOUT = 3600 * 2
LAST_FIX_TIME_TABLE = "last_fix_time"
FIX_HISTORY_TABLE = "fix_history"
VIP_TABLE = "vip"

def init_directories():
    os.makedirs(SET_TS_DIR, exist_ok=True)
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(SESSION_DIR, exist_ok=True)
    os.makedirs(SETTING_DIR, exist_ok=True)
    os.makedirs(USER_SPACE_DIR, exist_ok=True)
    os.makedirs(TELEGRAM_DIR, exist_ok=True)
    os.makedirs(IG_ERROR_DIR, exist_ok=True)
    if not os.path.exists(IG_ACCOUNTS_FILE):
        with open(IG_ACCOUNTS_FILE, "w") as f:
            json.dump([], f)
    if not os.path.exists(SELECTED_USER_FILE):
        with open(SELECTED_USER_FILE, "w") as f:
            json.dump({}, f)

def horloge_ts():
    now = datetime.datetime.now()
    h = now.strftime("%H")
    m = now.strftime("%M")
    s = now.strftime("%S")
    ts = Text.assemble(("[", "bold magenta"), (f"TS-", "italic bold magenta"), (f"{n} ", "italic bold cyan"), (h, "italic bold blue"), (":", "italic bold cyan"), (m, "italic bold blue"), (":", "italic bold cyan"), (s, "italic bold blue"), ("]", "bold magenta"),)
    return ts
def save_json(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
        
def safe_load_json(filepath, default=None):
    if default is None:
        default = [] if f"ig{n}.json" in filepath else {}
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            content = f.read().strip()
            if not content:
                return default
            try:
                return json.loads(content)
            except (json.JSONDecodeError, IOError):
                afficher_erreur(f"ichier JSON corrompu : {filepath}")
                return default
    return default

def formatter_message(emoji, texte: Text):
    return Text.assemble((f"[{emoji}] ", ""), texte)
def afficher_succes(msg, emoji="✅"):
    ts = horloge_ts()
    if not isinstance(msg, Text):
        msg = Text(str(msg), style="bold italic green")
    else:
        msg.stylize("bold italic green")
    console.print(ts, formatter_message(emoji, msg))
def afficher_succes2(msg, emoji="✅"):
    if not isinstance(msg, Text):
        msg = Text(str(msg), style="italic green")
    else:
        msg.stylize("italic green")
    console.print(formatter_message(emoji, msg))
def afficher_erreur(msg, emoji="❌"):
    ts = horloge_ts()
    if not isinstance(msg, Text):
        msg = Text(str(msg), style="bold italic red")
    else:
        msg.stylize("bold italic red")
    console.print(ts, formatter_message(emoji, msg))
def afficher_erreur2(msg, emoji="❌"):
    if not isinstance(msg, Text):
        msg = Text(str(msg), style="bold italic red")
    else:
        msg.stylize("bold italic red")
    console.print(formatter_message(emoji, msg))
def afficher_info(msg, emoji="🔔"):
    ts = horloge_ts()
    if not isinstance(msg, Text):
        msg = Text(str(msg), style="italic yellow")
    else:
        msg.stylize("italic yellow")
    console.print(ts, formatter_message(emoji, msg))
def afficher_info2(msg, emoji="🔔"):
    if not isinstance(msg, Text):
        msg = Text(str(msg), style="bold italic yellow")
    else:
        msg.stylize("bold italic yellow")
    console.print(formatter_message(emoji, msg))
def afficher_info3(msg, emoji="🔔"):
    if not isinstance(msg, Text):
        msg = Text(str(msg), style="bold italic yellow")
    else:
        msg.stylize("bold italic yellow")
    console.print(formatter_message(emoji, msg))
def afficher_lien(txt):
    return Text(str(txt), style="underline italic cyan")
def afficher_id(txt):
    return Text(str(txt), style="underline italic blue")
def afficher_action(txt):
    return Text(str(txt), style="underline bold italic magenta")
def afficher_label(emoji, nom_label, contenu_richtext, couleur="bold white"):
    return Text.assemble((f"[{emoji}] ", ""), (f"{nom_label} : ", couleur), contenu_richtext)
def titre_section2(titre):
    table = Table.grid(expand=True)
    table.add_column(justify="center")
    table.add_row(Text(titre, style="bold magenta on green", justify="center"))
    panel = Panel.fit(table, border_style="magenta")
    console.print(panel)
def titre_section(titre):
    panel = Panel(Text(titre, style="bold magenta on green", justify="center"), border_style="bold cyan", expand=True)
    console.print(panel)
def titre_section3(titre):
    texte = Text(titre, style="bold blue on green", justify="center")
    console.print(texte, justify="center")
def load_accounts():
    return safe_load_json(IG_ACCOUNTS_FILE, [])
def load_ig_accounts():
    data = safe_load_json(IG_ACCOUNTS_FILE, [])
    return {acc['username']: acc for acc in data if 'username' in acc}
def get_account_password_vip(username):
    accounts = load_ig_accounts()
    return accounts.get(username, {}).get("password")
def clear():
    os.system('clear' if os.name == 'posix' else 'cls')
def save_selected_user(account):
    with open(SELECTED_USER_FILE, "w") as f:
        json.dump(account, f)
def delete_selected_user():
    if os.path.exists(SELECTED_USER_FILE):
        os.remove(SELECTED_USER_FILE)
    with open(SELECTED_USER_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f)
def ig_session_path(username):
    return os.path.join(SESSION_DIR, f"{username}.json")
def remove_ig_session(username):
    session_path = ig_session_path(username)
    if os.path.exists(session_path):
        os.remove(session_path)
def load_blocked_accounts():
    return safe_load_json(BLOCK_FILE, default={})
def save_blocked_accounts(data):
    save_json(BLOCK_FILE, data)
def is_account_blocked(username):
    blocked = load_blocked_accounts()
    if username in blocked:
        try:
            blocked_time = float(blocked[username]["blocked_time"])
            if time.time() - blocked_time < BLOCK_DURATION_MINUTES * 60:
                return True
        except Exception:
            return False
    return False
QUOTA_DB = os.path.join(SET_TS_DIR, "quota.db")
def delete_from_quota(username):
    try:
        if not os.path.exists(QUOTA_DB):
            return
        conn = sqlite3.connect(QUOTA_DB)
        cur = conn.cursor()
        # Vérifie si la colonne existe (sécurité)
        cur.execute("PRAGMA table_info(quotas)")
        columns = [c[1] for c in cur.fetchall()]
        if "username" not in columns:
            conn.close()
            return
        # Supprime les lignes liées à ce username
        cur.execute("DELETE FROM quotas WHERE username = ?", (username,))
        conn.commit()
        conn.close()
    except Exception as e:
        pass
      
def get_setting_file(username):
    return os.path.join(SESSION_DIR, "settings", f"set_{username}.json")
def rm_user(username, password):
    try:
        accounts = safe_load_json(IG_ACCOUNTS_FILE, [])
        file_set = get_setting_file(username)
        account = [acc for acc in accounts if acc["username"] != username]
        with open(IG_ACCOUNTS_FILE, "w") as f:
            json.dump(account, f, indent=4)
        if os.path.exists(file_set):
            os.remove(file_set)
        remove_ig_session(username)
        delete_selected_user()
        delete_from_quota(username)
        
        console.print(f"[bold red][🧹] Compte {username} supprimer[/bold red]")
        return None
    except Exception as e:
        console.print(f"[bold red][×] Erreur lors de la supppression:{e}[/bold red]")
        return None
        
def block_account(username, password):
    try:
        with open(IG_ACCOUNTS_FILE, "r") as f:
            accounts = json.load(f)
        accounts = [acc for acc in accounts if acc["username"] != username]
        with open(IG_ACCOUNTS_FILE, "w") as f:
            json.dump(accounts, f, indent=4)
        try:
            with open(BLOCK_FILE, "r") as f:
                blocked = json.load(f)
        except FileNotFoundError:
            blocked = {}
        blocked[username] = {"password": password, "blocked_time": str(time.time())}
        with open(BLOCK_FILE, "w") as f:
            json.dump(blocked, f, indent=4)
        remove_ig_session(username)
        delete_selected_user()
        delete_from_quota(username)
    except Exception as e:
        afficher_erreur(f"Erreur lors du blocage de {username} : {e}", emoji="❌")

def block_account2(username, password):
    try:
        with open(IG_ACCOUNTS_FILE, "r") as f:
            accounts = json.load(f)
        accounts = [acc for acc in accounts if acc["username"] != username]
        with open(IG_ACCOUNTS_FILE, "w") as f:
            json.dump(accounts, f, indent=4)
        try:
            with open(BLOCK_FILE2, "r") as f:
                blocked = json.load(f)
        except FileNotFoundError:
            blocked = {}
        blocked[username] = {
            "password": password,
            "blocked_time": str(time.time())
        }
        with open(BLOCK_FILE2, "w") as f:
            json.dump(blocked, f, indent=4)
        remove_ig_session(username)
        delete_selected_user()
        delete_from_quota(username)
        
        console.print(f"[red][xx] Le compte {username} est en etape supplementaire[/red]")
    except Exception as e:
        afficher_erreur(f"Erreur lors du blocage de {username} : {e}", emoji="❌")
def restore_unblocked_accounts():
    try:
        with open(BLOCK_FILE, "r") as f:
            blocked = json.load(f)
    except FileNotFoundError:
        blocked = {}
    try:
        with open(IG_ACCOUNTS_FILE, "r") as f:
            active_accounts = json.load(f)
    except FileNotFoundError:
        active_accounts = []
    to_unblock = []
    updated = False
    now = time.time()
    for username, info in list(blocked.items()):
        if now - float(info["blocked_time"]) > BLOCK_DURATION_MINUTES * 60:
            to_unblock.append(username)
            active_accounts.append({
                "username": username,
                "password": info["password"]
            })
            updated = True
    for username in to_unblock:
        blocked.pop(username, None)
    if updated:
        with open(IG_ACCOUNTS_FILE, "w") as f:
            json.dump(active_accounts, f, indent=4)
        with open(BLOCK_FILE, "w") as f:
            json.dump(blocked, f, indent=4)
    try:
        with open(BLOCK_FILE, "r") as f:
            blocked = json.load(f)
    except FileNotFoundError:
        blocked = {}
    try:
        with open(IG_ACCOUNTS_FILE, "r") as f:
            active_accounts = json.load(f)
    except FileNotFoundError:
        active_accounts = []
    to_unblock = []
    updated = False
    now = time.time()
    for username, info in list(blocked.items()):
        if now - float(info["blocked_time"]) > BLOCK_DURATION_MINUTES2 * 60:
            to_unblock.append(username)
            active_accounts.append({
                "username": username,
                "password": info["password"]
            })
            updated = True
    for username in to_unblock:
        blocked.pop(username, None)
    if updated:
        with open(IG_ACCOUNTS_FILE, "w") as f:
            json.dump(active_accounts, f, indent=4)
        with open(BLOCK_FILE, "w") as f:
            json.dump(blocked, f, indent=4)
def analyse_error(e, username, password):
    err = str(e).lower()
    if "login_required" in err or "user_has_logged_out" in err:
        console.print(Text.assemble(("[‼️] ",),("Ups !", "italic cyan"), (f" {username}", "bold italic yellow"), (" est deconnecté", "italic cyan")))
        try:
            remove_ig_session(username)
        except Exception as e:
            afficher_erreur(f"Impossible de réinitialiser {username}", emoji="❌")
        return None
    elif "nous pouvons également vous envoyer un e-mail" in err or "challengeresolve" in err:
        console.print(Text.assemble(("[‼️] ",), ("Ups !", "bold italic red"), (f" {username}", "bold italic yellow"), (" n'est pas vérifié coté instagram", "bold italic red")))
        block_account2(username, password)
        return None
    elif "bad_password" in err or "mot de passe" in err or "password" in err:
        console.print(Text.assemble(("[🔐] ",), ("Mot de passe incorrect pour", "italic yellow"), (f" {username}", "bold italic yellow")))
        rm_user(username, password)
        return None
        
    elif any(x in err for x in ["challenge_required", "challengeresolve", "challenge_resolve", "choose a method", "challengechoice", "challenge_choice"]) or isinstance(e, ChallengeRequired):
        console.print(Text.assemble(("[🧩] ",), ("Hey! Challenge sur", "italic yellow"), (f" {username}", "bold italic yellow"), (" vérifier l'application", "italic yellow")))
        return None
    elif "try another phone number or email" in err:
        console.print(f"[~] [red]Le compte {username} est introuvable sur instagram[/red]")
        rm_user(username, password)
        return None
    return False

async def analyse_error2(e, username, password, client):
    err = str(e).lower()
    if "not found for url" in err:
        afficher_erreur(f"Utilisateur introuvable sur instagram", emoji="❌")
        return None
    if "nous ne trouvons pas de compte" in err:
        afficher_erreur(f"Erreur: compte {username} introuvable", emoji="❌")
        rm_user(username, password)
        await asyncio.sleep(0.5)
        return None
    if "feedback_required" in err:
        afficher_erreur(f"Ups ! compte {username}: feedback_required", emoji="‼️")
        time.sleep(0.5)
        return None
    elif "nous pouvons egalement vous envoyer un e-mail" in err or "le mot de passe que vous avez entre est incorrect" in err or "mot de passe" in err or "password" in err:
        afficher_erreur(f"Ups ! {username} mot de passe incorrect", emoji="‼️")
        rm_user(username, password)
        time.sleep(0.5)
        return None
    elif "sorry, this media has been deleted" in err:
        afficher_erreur("Ups ! Publication déjà supprimée par l'auteur", emoji="🗑️ ")
        await asyncio.sleep(0.5)
        return None
    elif "you cannot like this media" in err:
        save_device_settings(SESSION_DIR, username, profile)
        return None
    elif any(x in err for x in ["chalenge_choice", "challengechoice", "choose a method", "choice"]):
        block_account2(username, password)
        await asyncio.sleep(0.5)
        return None
    else:
        afficher_erreur(f"Erreur: {e}")
        return None

def get_password_for_username(username):
    if not os.path.exists(SELECTED_USER_FILE):
        return None
    with open(SELECTED_USER_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if data.get("username") == username:
        return data.get("password")
    return None
def load_and_patch_device_settings(SETTING_DIR, username):
    BASE_DIR = os.path.join(os.environ.get("PREFIX", "/data/data/com.termux/files/usr"), "com.termux", "home", ".useuser", "unknown_folder")
    CONFIG_DIR = os.path.join(BASE_DIR, "configuration")
    SESSION_DIR = os.path.join(BASE_DIR, "ig_sessions")
    IG_ERROR_DIR = os.path.join(SESSION_DIR, "all_error")
    SETTING_DIR = os.path.join(SESSION_DIR, "settings")
    setting_path = os.path.join(SETTING_DIR, f"set_{username}.json")
    if not os.path.exists(setting_path):
        return (None, None, None, None, None, None, None)
    connection_types = [
        {"type": "WIFI", "sub": ["802.11n", "802.11ac", "802.11ax"], "speed": (20000,100000), "quality": "EXCELLENT"},
        {"type": "MOBILE", "sub": ["5G","NR"], "speed": (15000,50000), "quality": "VERY_GOOD"},
        {"type": "MOBILE", "sub": ["LTE","4G","LTE+"], "speed": (5000,20000), "quality": "GOOD"},
        {"type": "MOBILE", "sub": ["HSPA","HSPA+","3G"], "speed": (800,3000), "quality": "MODERATE"},
        {"type": "MOBILE", "sub": ["EDGE","GPRS","2G"], "speed": (50,250), "quality": "POOR"},
    ]

    datas = random.choice(connection_types)
    conn_type = datas["type"]
    conn_subtype = random.choice(datas["sub"])
    speed_kbps = random.randint(*datas["speed"])
    total_bytes = random.randint(speed_kbps * 50, speed_kbps * 300)
    total_time = random.randint(2000,9000)
    quality_score = random.randint(40,99)
    
    data = safe_load_json(setting_path, {})
    uuids = data.get("uuids", {})
    device_settings = data.get("device_settings", {})
    user_agent = data.get("user_agent")
    country = data.get("country")
    locale_str = data.get("locale")
    country_code = data.get("country_code")
    tz_offset = data.get("timezone_offset")
    try:
        for k in uuids:
            if k in ["client_session_id", "request_id", "tray_session_id"]:
                uuids[k] = str(uuid.uuid4())
        for k, v in uuids.items():
            device_settings[k] = v
        device_settings.update({
            "X-IG-Connection-Type": conn_type,
            "X-IG-Connection-SubType": conn_subtype,
            "X-IG-Bandwidth-Speed-KBPS": str(speed_kbps),
            "X-IG-Bandwidth-TotalBytes-B": str(total_bytes),
            "X-IG-Bandwidth-TotalTime-MS": str(total_time),
            "X-IG-Connection-Quality": f"{data['quality']} {quality_score}/{quality_score}",
            "X-FB-HTTP-Engine": random.choices(["OkHttp", "Liger"], weights=[0.85, 0.15])[0]
        })
        data["uuids"] = uuids
        data["device_settings"] = device_settings
        with open(setting_path, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        console.print(f"[red]Erreur de configuration pour {username} : {e}[/red]")
        return
    return (uuids, device_settings, user_agent, country, country_code, locale_str, tz_offset)

async def connect_instagram(username, password, client):
    BASE_DIR = os.path.join(os.environ.get("PREFIX", "/data/data/com.termux/files/usr"), "com.termux", "home", ".useuser", "unknown_folder")
    CONFIG_DIR = os.path.join(BASE_DIR, "configuration")
    SESSION_DIR = os.path.join(BASE_DIR, "ig_sessions")
    IG_ERROR_DIR = os.path.join(SESSION_DIR, "all_error")
    SETTING_DIR = os.path.join(SESSION_DIR, "settings")
    session_path = os.path.join(SESSION_DIR, f"{username}.json")
    setting_path = os.path.join(SETTING_DIR, f"set_{username}.json")
    uuids, device_settings, user_agent, country, country_code, locale_str, tz_offset = load_and_patch_device_settings(SETTING_DIR, username)
    if not all([uuids, device_settings, user_agent, country, country_code, locale_str, tz_offset]):
        afficher_erreur(f"Config manquante ou incomplète pour {username}", emoji="❌")
        rm_user(username, password)
        return None
    cl = Client()
    if os.path.exists(session_path):
        try:
            cl.load_settings(session_path)
            try:
                cl.get_timeline_feed()
                afficher_succes(f"Reconnexion réussie pour {username}", emoji="🔛")
            except LoginRequired:
                remove_ig_session(username)
        except ChallengeRequired:
            try:
                remove_ig_session(username)
                block_account2(username, password)
                return None
            except Exception as e:
                pass
        except Exception as e:
            err = str(e).lower()
            if any(x in err for x in ["chalenge_choice", "challengechoice", "choose a method", "choice", "challenge_resolve"]):
                afficher_erreur("Erreuer: challenge_resolve")
                block_account2(username, password)
                delete_selected_user()
                await asyncio.sleep(0.5)
                return None
            elif "Unknown step_name" in err or "ufac_www_bloks" in err:
                afficher_erreur("Erreuer: Verification de compte exigé par Instagram")
                block_account2(username, password)
                await asyncio.sleep(0.5)
                return None
            else:
                return None
            return None
    else:
        try:
            afficher_info(f"Première connexion pour {username}", emoji="🔵")
            cl.set_uuids(uuids)
            cl.set_device(device_settings)
            cl.set_user_agent(user_agent)
            cl.set_country(country)
            cl.set_locale(locale_str)
            cl.set_country_code(int(country_code))
            cl.set_timezone_offset(tz_offset)
            cl.login(username, password)
            cl.dump_settings(session_path)
        except ChallengeRequired as e:
            try:
                remove_ig_session(username)
                block_account2(username, password)
                return None
            except Exception as e:
                pass
        except TwoFactorRequired as e:
            rm_user(username)
            afficher_info(f"Retourner au ajout compte puis reajouter {username} et preparer avant de relancer cette tache car ça besoin code verification")
            return None
        except Exception as e:
            err = str(e).lower()
            if any(x in err for x in ["chalenge_choice", "challengechoice", "choose a method", "choice", "challenge_resolve"]):
                afficher_erreur("Erreuer: challenge_resolve")
                block_account2(username, password)
                delete_selected_user()
                await asyncio.sleep(0.5)
                return None
            elif "Unknown step_name" in err or "ufac_www_bloks" in err:
                afficher_erreur("Erreuer: Verification de compte exigé par Instagram")
                block_account2(username, password)
                await asyncio.sleep(0.5)
                return None
            else:
                return None
            return None
    return cl
# --- SYNC: Connexion stricte avec settings ---
def connexion(username, password):
    
    BASE_DIR = os.path.join(os.environ.get("PREFIX", "/data/data/com.termux/files/usr"), "com.termux", "home", ".useuser", "unknown_folder")
    CONFIG_DIR = os.path.join(BASE_DIR, "configuration")
    SESSION_DIR = os.path.join(BASE_DIR, "ig_sessions")
    IG_ERROR_DIR = os.path.join(SESSION_DIR, "all_error")
    SETTING_DIR = os.path.join(SESSION_DIR, "settings")
    session_path = os.path.join(SESSION_DIR, f"{username}.json")
    setting_path = os.path.join(SETTING_DIR, f"set_{username}.json")

    uuids, device_settings, user_agent, country, country_code, locale_str, tz_offset = load_and_patch_device_settings(SETTING_DIR, username)
    if not all([uuids, device_settings, user_agent, country, country_code, locale_str, tz_offset]):
        afficher_erreur2(f"Configuration pour {username} manquant ou incomplet")
        rm_user(username, password)
        return None
    cl = Client()
    if not os.path.exists(session_path):
        try:
            cl.set_uuids(uuids)
            cl.set_device(device_settings)
            cl.set_user_agent(user_agent)
            cl.set_country(country)
            cl.set_locale(locale_str)
            cl.set_country_code(int(country_code))
            cl.set_timezone_offset(tz_offset)
            cl.login(username, password)
            cl.dump_settings(session_path)
            console.print(Text.assemble(("[🔜] ",), ("session créée pour ", "italic cyan"), (f"{username}", "bold italic yellow")))
        except Exception as e:
            if analyse_error(e, username, password):
                return
    else:
        try:
            cl.load_settings(session_path)
            cl.get_timeline_feed()
            console.print(Text.assemble(("[🔜] ",), ("session à jour pour ", "italic cyan"), (f"{username}", "bold italic yellow")))
        except Exception as e:
            if analyse_error(e, username, password):
                return
    return cl

# --- ASYNC: Restaure toutes les sessions en mode strict settings ---
def restore_all_sessions():
    BASE_DIR = os.path.join(os.environ.get("PREFIX", "/data/data/com.termux/files/usr"), "com.termux", "home", ".useuser", "unknown_folder")
    CONFIG_DIR = os.path.join(BASE_DIR, "configuration")
    SESSION_DIR = os.path.join(BASE_DIR, "ig_sessions")
    IG_ERROR_DIR = os.path.join(SESSION_DIR, "all_error")
    SETTING_DIR = os.path.join(SESSION_DIR, "settings")
    
    titre_section(f"PREPARATION DES COMPTES TS-{n}")
    INSTAGRAM_SESSIONS = {}
    try:
        accounts = safe_load_json(IG_ACCOUNTS_FILE, [])
    except Exception as e:
        afficher_erreur2(f"Erreur lecture du fichier : {e}")
        return {}
    for account in accounts:
        username = account.get("username")
        password = account.get("password")
        session_path = os.path.join(SESSION_DIR, f"{username}.json")
        uuids, device_settings, user_agent, country, country_code, locale_str, tz_offset = load_and_patch_device_settings(SETTING_DIR, username)

        if not all([uuids, device_settings, user_agent, country, country_code, locale_str, tz_offset]):
            afficher_erreur2(f"Configuration pour {username} manquante ou incomplète")
            rm_user(username, password)
            continue

        cl = Client()
        if os.path.exists(session_path):
            try:
                cl.load_settings(session_path)
                afficher_succes2(f"Compte à jour pour {username}")
                INSTAGRAM_SESSIONS[username] = cl
            except LoginRequired:
                try:
                    remove_ig_session(username)
                    connexion(username, password)
                    INSTAGRAM_SESSIONS[username] = cl
                except Exception as e:
                    INSTAGRAM_SESSIONS[username] = cl
            except ChallengeRequired:
                try:
                    remove_ig_session(username)
                    block_account2(username, password)
                except Exception as e:
                    pass
            except Exception as e:
                if analyse_error(e, username, password):
                    continue
        else:
            try:
                cl.set_uuids(uuids)
                cl.set_device(device_settings)
                cl.set_user_agent(user_agent)
                cl.set_country(country)
                cl.set_locale(locale_str)
                cl.set_country_code(int(country_code))
                cl.set_timezone_offset(tz_offset)
                cl.login(username, password)
                cl.dump_settings(session_path)
                afficher_succes2(f"Session créée pour {username}")
                INSTAGRAM_SESSIONS[username] = cl
            except ChallengeRequired:
                try:
                    remove_ig_session(username)
                    block_account2(username, password)
                except Exception as e:
                    pass
            except Exception as e:
                if analyse_error(e, username, password):
                    continue

    return INSTAGRAM_SESSIONS

async def send_message_with_retry(client, entity, message, max_retries=1, timeout=7):
    async with send_lock:
        for attempt in range(max_retries + 1):
            try:
                await asyncio.sleep(0)  # Yield control to avoid event loop starvation
                await client.send_message(entity, message)
                break
            except FloodWaitError as e:
                wait_time = int(e.seconds)
                afficher_info(f"FloodWaitError : pause {wait_time}s", emoji="🕗")
                await asyncio.sleep(wait_time)
            except Exception as e:
                afficher_erreur(f"Erreur envoi message ({attempt+1}/{max_retries+2}) : {e}", emoji="❌")
                await asyncio.sleep(0.5)
                
async def ainput(prompt: str = ""):
    return await asyncio.get_event_loop().run_in_executor(None, input, prompt)                

async def connect_telegram():
    titre_section(f"LANCEMENT DES TACHES TELEGRAM - INSTAGRAM TS-{n}")
    afficher_info2("🥰 Raha hiala na hanajanona ny asa ianao dia tsindrio ny CTRL+C")
    
    cfg = safe_load_json(TELEGRAM_API_FILE)
    api_id = cfg["api_id"]
    api_hash = cfg["api_hash"]
    phone = cfg["phone"]
    client = TelegramClient(TELEGRAM_SESSION_FILE, api_id, api_hash)
    try:
        if os.path.exists(TELEGRAM_SESSION_FILE + ".session"):
            await client.connect()
            if not await client.is_user_authorized():
                await client.send_code_request(phone)
                code = await ainput("Code reçu par Telegram : ")
                time.sleep(15*60)
                await client.sign_in(phone, code)
        else:
            await client.start(phone=lambda: phone)
            afficher_succes("Connexion Telegram réussie !", emoji="✅")
        me = await client.get_me()
        if me.username:
            identite = me.username
        elif me.last_name:
            identite = me.last_name
        elif me.first_name:
            identite = me.first_name
        else:
            identite = "(aucune information)"
        phone_number = me.phone or "(aucun numéro récupéré)"
        # Affichage sous forme de tableau centré
        table = Table(show_header=False, box=box.ROUNDED, expand=False, style="bold yellow")
        table.add_row(f"[bold italic green][🤵] Telegram dans TS-{n}[/bold italic green]", f"[bold italic magenta]{identite}[/bold italic magenta]")
        table.add_row(f"[bold italic green][📞] Téléphone dans TS-{n}[/bold italic green]", f"[bold italic magenta]+{phone_number}[/bold italic magenta]")
        console.print(Align.center(table))
        sys.stdout.write(f'\x1b]2;𓆩【⚡ TS-{n} > [{identite}] EN COURS】𓆪 \x07')
    except errors.PhoneCodeInvalidError:
        afficher_erreur("Code incorrect. Revenez au ajout de compte puis verifier le.", emoji="❌")
        time.sleep(5)
        os._exit(1)
    except errors.ApiIdInvalidError:
        afficher_erreur("API_ID ou API_HASH invalide. retourner au ajout de compte puis deconnecte le", emoji="❌")
        time.sleep(5)
        os._exit(1)
    except Exception as e:
        err = str(e).lower()
        if "database" in err:
            afficher_info(f"Verifieo sao lancer @ session ny TS-{n}, Raha tsy izay dia deconnecteo @ mampiditra compte ao dia connecteo avieo")
        else:
            afficher_erreur(f"Erreur: {err}")
        time.sleep(5)
        os._exit(1)
    return client
    

# === INITIALISATION BASE DE DONNÉES ===
def init_db():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with sqlite3.connect(VIP_DB_FILE, timeout=30, isolation_level=None) as conn:
        conn.execute(f'''
            CREATE TABLE IF NOT EXISTS {VIP_TABLE} (
                username TEXT PRIMARY KEY,
                password TEXT,
                nb_post INTEGER,
                nb_story INTEGER,
                nb_public INTEGER,
                donor TEXT,
                donor_link TEXT
            )
        ''')
        conn.execute(f'''
            CREATE TABLE IF NOT EXISTS {FIX_HISTORY_TABLE} (
                username TEXT PRIMARY KEY,
                timestamp REAL
            )
        ''')
        conn.execute(f'''
            CREATE TABLE IF NOT EXISTS {LAST_FIX_TIME_TABLE} (
                username TEXT PRIMARY KEY,
                timestamp REAL
            )
        ''')

init_db()
init_directories()

# === CONNEXION DB ===
def get_conn():
    return sqlite3.connect(VIP_DB_FILE, timeout=30, isolation_level=None)

# === PARSING DES MESSAGES ===
def should_extract_vip(message: str) -> bool:
    message_lower = message.lower()
    return (
        re.search(r"[❗️🔴]*\s*account", message_lower, re.IGNORECASE | re.MULTILINE)
        and ("required" in message_lower or "fix_" in message_lower)
    )

def extract_username(message: str) -> Optional[str]:
    account_line_match = re.search(
        r"[❗️🔴]?\s*Account\s+([^\n(]+)",
        message,
        re.IGNORECASE | re.MULTILINE
    )
    if not account_line_match:
        return None
    account_line = account_line_match.group(1).strip()
    username_match = re.match(r"([^\s\(\)]+)", account_line)
    if not username_match:
        return None
    return username_match.group(1).strip()

def parse_vip_block(message: str) -> Optional[Dict[str, Any]]:
    if not should_extract_vip(message):
        return None

    username = extract_username(message)
    if username is None:
        return None

    nb_post = len(re.findall(r"new post is required", message, re.IGNORECASE))
    nb_story = len(re.findall(r"new story is required", message, re.IGNORECASE))
    nb_public = len(re.findall(r"account must be public", message, re.IGNORECASE))

    donor = ""
    donor_link = ""
    donor_match = re.search(r'source account\s*:\s*(https?://(?:www\.)?instagram\.com/([^/?#\s)]+))', message, re.IGNORECASE)
    
    if donor_match:
        donor_link = donor_match.group(1).strip().rstrip(").,")
        donor = donor_match.group(2).strip().rstrip(").,")

    DOWNLOAD_DIR = "/storage/emulated/0/TS images"
    if username is not None:
        try:
            user_dir = os.path.join(DOWNLOAD_DIR, username)
            url_dir = os.path.join(user_dir, "url")
            story_dir = os.path.join(user_dir, "story")
            os.makedirs(user_dir, exist_ok=True)
            os.makedirs(url_dir, exist_ok=True)
            os.makedirs(story_dir, exist_ok=True)
            if donor and donor_link:
                donor_file = os.path.join(url_dir, f"{donor}.txt")
                if not os.path.exists(donor_file):
                    with open(donor_file, "w") as f:
                        f.write(donor_link)
        except Exception as e:
            pass
            return
    return {
        "username": username,
        "password": get_account_password_vip(username),
        "nb_post": nb_post,
        "nb_story": nb_story,
        "nb_public": nb_public,
        "donor": donor,
        "donor_link": donor_link
    }

def parse_all_vip_message(full_message: str) -> List[Dict[str, Any]]:
    blocks = re.split(r"={3,}", full_message)
    return [parsed for block in blocks if (parsed := parse_vip_block(block.strip()))]

# === GESTION TABLE VIP ===
def add_to_vip_file(entries: List[Dict[str, Any]]):
    with get_conn() as conn:
        cur = conn.execute(f"SELECT username FROM {VIP_TABLE}")
        usernames_in_vip = {row[0] for row in cur.fetchall()}

        cur = conn.execute(f"SELECT username FROM {FIX_HISTORY_TABLE}")
        usernames_in_fix = {row[0] for row in cur.fetchall()}

        ig_accounts = load_ig_accounts()
        usernames_ig = set(ig_accounts.keys())

        new_data = [
            entry for entry in entries
            if entry["username"] not in usernames_in_vip
            and entry["username"] not in usernames_in_fix
            and entry["username"] in usernames_ig
        ]

        for entry in new_data:
            conn.execute(
                f'''
                INSERT OR IGNORE INTO {VIP_TABLE}
                (username, password, nb_post, nb_story, nb_public, donor, donor_link)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    entry["username"],
                    entry.get("password"),
                    entry.get("nb_post", 0),
                    entry.get("nb_story", 0),
                    entry.get("nb_public", 0),
                    entry.get("donor"),
                    entry.get("donor_link")
                )
            )

def load_vip_list() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.execute(f"SELECT * FROM {VIP_TABLE}")
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

def save_vip_list(data: List[Dict[str, Any]]):
    with get_conn() as conn:
        conn.execute(f"DELETE FROM {VIP_TABLE}")
        for entry in data:
            conn.execute(
                f'''INSERT OR IGNORE INTO {VIP_TABLE}
                (username, password, nb_post, nb_story, nb_public, donor, donor_link)
                VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (
                    entry["username"],
                    entry.get("password"),
                    entry.get("nb_post", 0),
                    entry.get("nb_story", 0),
                    entry.get("nb_public", 0),
                    entry.get("donor"),
                    entry.get("donor_link"),
                )
            )

# === FIX HISTORY ===
def clean_fix_history():
    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(f"SELECT username, timestamp FROM {FIX_HISTORY_TABLE}")
        history = {row[0]: row[1] for row in cur.fetchall()}
    cleaned = {user: ts for user, ts in history.items() if now - ts < FIX_HISTORY_TIMEOUT}
    if len(cleaned) != len(history):
        with get_conn() as conn:
            conn.execute(f"DELETE FROM {FIX_HISTORY_TABLE}")
            for user, ts in cleaned.items():
                conn.execute(
                    f"INSERT OR REPLACE INTO {FIX_HISTORY_TABLE} (username, timestamp) VALUES (?, ?)", (user, ts))
    return cleaned

def load_last_fix_time():
    with get_conn() as conn:
        cur = conn.execute(f"SELECT username, timestamp FROM {LAST_FIX_TIME_TABLE}")
        return {row[0]: row[1] for row in cur.fetchall()}

def save_last_fix_time(data: Dict[str, float]):
    with get_conn() as conn:
        conn.execute(f"DELETE FROM {LAST_FIX_TIME_TABLE}")
        for username, ts in data.items():
            conn.execute(
                f"INSERT OR REPLACE INTO {LAST_FIX_TIME_TABLE} (username, timestamp) VALUES (?, ?)", (username, ts))

# === EXTRACTION PRINCIPALE ===
def extract_vip_from_message(message_text: str):
    data_list = parse_all_vip_message(message_text)
    if data_list:
        add_to_vip_file(data_list)
def is_username_only_vip(entry: Dict[str, Any]):
    return (isinstance(entry, dict) and "username" in entry and all(k == "username" or not entry[k] for k in entry.keys()))
async def surveillance_auto_vip(client):
    while True:
        vip_data = load_vip_list()
        last_fix_time = load_last_fix_time()
        fix_history = clean_fix_history()
        ig_accounts = load_ig_accounts()
        now = time.time()
        data_changed = False
        usernames_to_remove = set()

        for entry in vip_data:
            username = entry.get("username")
            if not username:
                continue
            if is_username_only_vip(entry) and username in ig_accounts:
                last_time = last_fix_time.get(username, 0)
                if now - last_time >= FIX_HISTORY_TIMEOUT:
                    fix_command = f"/fix_{username}"
                    try:
                        await client.send_message("SmmKingdomTasksBot", fix_command)
                        afficher_info(f"Envoyé: {fix_command}")
                        last_fix_time[username] = now
                        fix_history[username] = now
                        data_changed = True
                        usernames_to_remove.add(username)
                    except Exception as e:
                        afficher_info(f"Erreur envoi /fix_{username}: {e}")
                continue
        if usernames_to_remove or data_changed:
            with get_conn() as conn:
                for username in usernames_to_remove:
                    conn.execute(f"DELETE FROM {VIP_TABLE} WHERE username = ?", (username,))
                # Fix history et last_fix_time
                conn.execute(f"DELETE FROM {LAST_FIX_TIME_TABLE}")
                for username, ts in last_fix_time.items():
                    conn.execute(
                        f"INSERT OR REPLACE INTO {LAST_FIX_TIME_TABLE} (username, timestamp) VALUES (?, ?)",
                        (username, ts)
                    )
                conn.execute(f"DELETE FROM {FIX_HISTORY_TABLE}")
                for username, ts in fix_history.items():
                    conn.execute(
                        f"INSERT OR REPLACE INTO {FIX_HISTORY_TABLE} (username, timestamp) VALUES (?, ?)",
                        (username, ts)
                    )

        await asyncio.sleep(5)

def remove_exact_duplicates(filename):
    with open(filename, "r", encoding="utf-8") as f:
        data = json.load(f)

    seen = set()
    new_data = [] 
    for entry in data:
        key = (entry["username"], entry["password"])
        if key not in seen:
            new_data.append(entry)
            seen.add(key)

    if len(new_data) != len(data):
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(new_data, f, indent=4)

def monitor_file(filename):
    last_mtime = None
    try:
        mtime = os.path.getmtime(filename)
        if mtime != last_mtime:
            remove_exact_duplicates(filename)
            last_mtime = mtime
    except Exception:
        pass
# --- Initialisation SQLite ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS quota (
            username TEXT PRIMARY KEY,
            start REAL,
            follow INTEGER,
            like INTEGER,
            follow_blocked_until REAL,
            like_blocked_until REAL
        )
    ''')
    conn.commit()
    conn.close()

# --- Chargement d'un quota ---
def load_quota(username):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM quota WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()

    if row:
        return {
            "start": row[1],
            "follow": row[2],
            "like": row[3],
            "follow_blocked_until": row[4],
            "like_blocked_until": row[5]
        }
    else:
        return {
            "start": 0,
            "follow": 0,
            "like": 0,
            "follow_blocked_until": 0,
            "like_blocked_until": 0
        }

# --- Sauvegarde d’un quota ---
def save_quota(username, quota):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO quota (username, start, follow, like, follow_blocked_until, like_blocked_until)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(username) DO UPDATE SET
            start=excluded.start,
            follow=excluded.follow,
            like=excluded.like,
            follow_blocked_until=excluded.follow_blocked_until,
            like_blocked_until=excluded.like_blocked_until
    ''', (username, quota["start"], quota["follow"], quota["like"], quota["follow_blocked_until"], quota["like_blocked_until"]))
    conn.commit()
    conn.close()

# --- Mémoire temporaire ---
account_quota = defaultdict(lambda: {
    "start": 0,
    "follow": 0,
    "like": 0,
    "follow_blocked_until": 0,
    "like_blocked_until": 0
})

# --- Chargement automatique ---
def get_quota(username):
    if username not in account_quota or account_quota[username]["start"] == 0:
        account_quota[username] = load_quota(username)
    return account_quota[username]

# --- Vérification des actions ---
def can_do_action_separated(username, action_type, max_follow, max_like):
    now = time.time()
    q = get_quota(username)

    # Réinitialisation chaque heure
    if q["start"] == 0 or now - q["start"] >= 3600:
        q["start"] = now
        q["follow"] = 0
        q["like"] = 0
        q["follow_blocked_until"] = 0
        q["like_blocked_until"] = 0

    # Blocage spécifique
    if action_type == "follow" and now < q["follow_blocked_until"]:
        wait_time = int(q["follow_blocked_until"] - now)
        return False, wait_time
    if action_type == "like" and now < q["like_blocked_until"]:
        wait_time = int(q["like_blocked_until"] - now)
        return False, wait_time

    # Test follow
    if action_type == "follow" and q["follow"] >= max_follow:
        q["follow_blocked_until"] = q["start"] + 3600
        save_quota(username, q)
        wait_time = int(q["follow_blocked_until"] - now)
        return False, wait_time

    # Test like
    if action_type == "like" and q["like"] >= max_like:
        q["like_blocked_until"] = q["start"] + 3600
        save_quota(username, q)
        wait_time = int(q["like_blocked_until"] - now)
        return False, wait_time

    return True, 0

# --- Enregistrement d'une action ---
def register_action_separated(username, action_type):
    q = get_quota(username)
    if action_type == "follow":
        q["follow"] += 1
    elif action_type == "like":
        q["like"] += 1
    save_quota(username, q)

# --- Initialisation au lancement ---
init_db()
# --- VOTRE CODE ORIGINAL CI-DESSOUS ---
used_accounts_session = set()
last_used_username = None 

def load_last_username():
    if os.path.exists(SELECTED_USER_FILE):
        with open(SELECTED_USER_FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                return data 
            except json.JSONDecodeError:
                return None
    return None
def load_username():
    if os.path.exists(SELECTED_USER_FILE):
        with open(SELECTED_USER_FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                return data.get("username")
            except json.JSONDecodeError:
                return None
    return None

def select_next_account():
    global used_accounts_session, last_used_username
    max_attempts = 3
    attempts = 0
    accounts = load_accounts()
    if not accounts:
        return None
    try:
        if len(accounts) == 1:
            last_used_username = accounts[0]["username"]
            save_selected_user(accounts[0])
            return accounts[0]
    
        if len(used_accounts_session) >= len(accounts):
            used_accounts_session.clear()
    
        for acc in accounts:
            username = acc["username"]
            if username not in used_accounts_session:
                used_accounts_session.add(username)
                last_used_username = username
                save_selected_user(acc)
                return acc
        
        used_accounts_session.clear()
        acc = accounts[0]
        used_accounts_session.add(acc["username"])
        last_used_username = acc["username"]
        save_selected_user(acc)
        return acc
    except Exception as e:
        delete_selected_user()
        attempts += 1
def parameter():
    t, follower_count, like_count = counter()
    
    table = Table(title="📊 Paramètres reglable du Bot TS", box=box.ROUNDED, show_edge=True, border_style="cyan", title_style="bold magenta")
    
    table.add_column("Paramètre", justify="center", style="bold yellow")
    table.add_column("Valeur", justify="center", style="bold white")
    
    table.add_row("⏱️ Délai entre actions =", f"{t} secondes")
    table.add_row("👥 Followers / heure =", f"{follower_count} follow")
    table.add_row("❤️ Likes / heure =", f"{like_count} Like")
    
    console.print(Align.center(table))   
    
def extraire_cashcoins(message):
    message = message.replace("**", "").replace("\u200b", "").replace("\xa0", " ").replace("\n", " ")
    match = re.search(r"replenished with\s+([\d.]+)\s+cashcoins", message, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return None

def extract_link_and_action(message):
    link = None
    action = None

    match = re.search(r'https?://(?:www\.)?instagram\.com/[^\s)]+', message, re.IGNORECASE)
    if match:
        link = resolve_instagram_link(match.group(0).strip())

    action_match = re.search(r"Action\s*:\s*([^\n\r]+)", message, re.IGNORECASE)
    if action_match:
        action = normalize_action(action_match.group(1).strip())

    return link, action
    
def resolve_instagram_link(link: str) -> str:
    parsed_url = urlparse(link)
    path_parts = parsed_url.path.strip("/").split("/")
    if not path_parts:
        return link
    if path_parts[0] in ["p", "reel", "tv"] and len(path_parts) >= 2:
        shortcode = path_parts[1]
        return f"https://www.instagram.com/{path_parts[0]}/{shortcode}/"
    if path_parts[0] == "stories" and len(path_parts) >= 2:
        user = path_parts[1]
        return f"https://www.instagram.com/stories/{user}/"
    if len(path_parts) == 1:
        return f"https://www.instagram.com/{path_parts[0]}/"
    return link

def normalize_action(action: str) -> str:
    if not action:
        return None
    act = action.lower().strip()

    if "like" in act:
        return "like the post below"
    if "follow" in act:
        return "follow the profile"
    if "comment" in act or "leave the comment" in act:
        return "leave the comment"
    if "video" in act or "open the video" in act:
        return "open the video"
    if "stories" in act or "view all stories" in act or "reels" in act or "reel" in act:
        return "view all stories"
    return action

def extract_instagram_ids(cl, link, message):
    link, _ = extract_link_and_action(message)
    user_id = media_id = user = user2 = None
    m = re.search(r"instagram\.com/stories/([^/]+)/?", link)
    if m:
        try:
            user = m.group(1)
            user_id = cl.user_id_from_username(user)
        except Exception:
            user_id = None
        return user_id, None, user or None, None
    m = re.search(r"instagram\.com/(p|reel|tv)/([^/]+)/", link)
    if m:
        try:
            media_id = cl.media_pk_from_url(link)
        except Exception:
            pass
        return None, media_id, None, None
    m = re.search(r"instagram\.com/([^/]+)/?", link)
    if m and not any(x in link for x in ("/p/", "/reel/", "/tv/", "/stories/")):
        try:
            user = link.rstrip('/').split("/")[-1]
            user_id = cl.user_id_from_username(user)
        except Exception:
            try:
                user2 = m.group(1)
                user_id = cl.user_id_from_username(user2 + "/")
            except Exception:
                user_id = None
        return user_id, None, user or None, user2 or None
    return None, None, None, None

def print_compte(username):
    t, _, _ = counter()
    global last_account_print_time
    now = time.time()
    if now - last_account_print_time < t:
        time.sleep(t - (now - last_account_print_time))
    console.print(Text.assemble(horloge_ts(), (" [🤵] ",), ("Compte: ", "italic bold cyan"), (f"{username}", "italic yellow")))
    last_account_print_time = time.time()

# --- Charger ---
def load_blocked():
    if not os.path.exists(BLOCK_FILE):
        return {}
    with open(BLOCK_FILE, "r") as f:
        try:
            return json.load(f)
        except:
            return {}
def save_blocked(data):
    with open(BLOCK_FILE, "w") as f:
        json.dump(data, f, indent=2)
def block_account_action(username, password, action_type):
    blocked_data = load_blocked()
    unblock_time = int(time.time()) + BLOCK_DURATION_MINUTES
    if username not in blocked_data:
        blocked_data[username] = {"password": password}
    else:
        blocked_data[username]["password"] = password
    blocked_data[username][action_type] = unblock_time
    save_blocked(blocked_data)
def format_remaining_time(until_ts: int):
    now = int(time.time())
    remaining = until_ts - now
    if remaining <= 0:
        return None
    td = timedelta(seconds=remaining)
    days = td.days
    hours, remainder = divmod(td.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{days}j {hours}h {minutes}m {seconds}s"
def is_account_block(username, action_type):
    blocked_data = load_blocked()
    if username in blocked_data and action_type in blocked_data[username]:
        until_ts = blocked_data[username][action_type]
        remaining = format_remaining_time(until_ts)
        if remaining:  # encore bloqué
            afficher_info(f"ACTION: {action_type.upper()} TEMPS: {remaining}", emoji="🕑")
            return True
        else:
            del blocked_data[username][action_type]
            if not blocked_data[username]:
                del blocked_data[username]
            save_blocked(blocked_data)
    return False

async def traiter_message(message_text, client):
    global last_username, last_bot_msg_time, pending_comment, last_messages_sent, waiting_for_username
    global last_sent_type, last_sent_time, processing_insta_task, last_completed_key, last_bot_message_text
    now = time.time()
    last_messages_sent.clear()
    last_bot_msg_time = now
    message_lower = message_text.lower().strip()
    
    def reset_completed_flag():
        global last_completed_sent
        last_completed_sent = not None
    if pending_comment is not None:
        if not re.search(r'https://www\.instagram\.com/[^\s\)]+', message_text) and "action" not in message_lower:
            reset_completed_flag()
            comment_text = message_text.strip()
            account = load_last_username()
            link = pending_comment['link']
            cl = pending_comment["client"]
            media_id = pending_comment["media_id"]
            action = "leave the comment"
            console.print(Text.assemble(horloge_ts(), (" [💬] ",), ("Commentaire reçu: ", "bold yellow"), (f"{comment_text}", "italic cyan")))
            for try_login in range(2):
                try:
                    processing_insta_task = True
                    if not cl:
                        pending_comment = None
                        return
                    if not media_id:
                        media_id = cl.midia_pk_fom_url(link)
                    try:
                        cl.media_comment(media_id, comment_text)
                    except LoginRequired:
                        remove_ig_session(account["username"])
                        cl = await connect_instagram(account["username"], account["password"], client)
                        if not media_id:
                            media_id = cl.midia_pk_fom_url(link)
                        cl.media_comment(media_id, comment_text)
                    console.print(Text.assemble(horloge_ts(), (" [💬] ",), ("Commentaire posté:", "bold green"), (f"{comment_text}", "italic bright_cyan")))
                    key = f"{account['username']}|{link}|{action}|{comment_text}"
                    if last_completed_key != key:
                        if "no active task" not in last_bot_message_text.lower():
                            await send_message_with_retry(client, "SmmKingdomTasksBot", "✅Completed")
                        last_completed_key = key
                    break
                except Exception as e:
                    password = get_password_for_username(last_username)
                    should_skip = await analyse_error2(e, last_username, password, client)
                    if should_skip:
                        return None
                    else:
                        await send_message_with_retry(client, "SmmKingdomTasksBot", "❌Skip")
                        raise
                finally:
                    pending_comment = None
                    await asyncio.sleep(0.5)
                    processing_insta_task = False
            return
    
    # --- DEMANDE D'UN USERNAME ---
    if ("please give us your profile's username" in message_lower or
        "choose account from the list" in message_lower or
        "select user from list" in message_lower or
        "on review now" in message_lower or
        ("🔴 account" in message_lower and "required" in message_lower)):

        if last_sent_type == "instagram" and (now - last_sent_time) < MIN_MSG_INTERVAL:
            afficher_info("Username ignoré car Instagram vient d'être envoyé.", emoji="⚠️")
            return

        accounte = select_next_account()
        if not accounte:
            afficher_erreur("Aucun compte Instagram.", emoji="❌")
            return

        last_username = accounte["username"]
        await send_message_with_retry(client, "SmmKingdomTasksBot", last_username)
        print_compte(last_username)
        waiting_for_username = False
        last_sent_type = "username"
        last_sent_time = now
        return

    if message_lower == "instagram":
        waiting_for_username = True
        return

    # --- DETECTION ACTION INSTAGRAM ---
    link, action = extract_link_and_action(message_text)
    if link and action:
        reset_completed_flag()
        account = load_last_username()
        _, follower_count, like_count = counter()
        
        if "follow the profile" in action:
            can_do, wait_time = can_do_action_separated(account["username"], "follow", follower_count, like_count)
            if is_account_block(account["username"], "follow"):
                time.sleep(1)
                await send_message_with_retry(client, "SmmKingdomTasksBot", "❌Skip")
                return
            if not can_do:
                afficher_info(f"FOLLOW dépassé pour {account['username']}. Attends {int(wait_time//60)}min {int(wait_time%60)}s", emoji="🕑")
                time.sleep(1)
                await send_message_with_retry(client, "SmmKingdomTasksBot", "❌Skip")
                return
            
        if "like the post below" in action:
            can_do, wait_time = can_do_action_separated(account["username"], "like", follower_count, like_count)
            if is_account_block(account["username"], "like"):
                time.sleep(1)
                await send_message_with_retry(client, "SmmKingdomTasksBot", "❌Skip")
                return
            if not can_do:
                afficher_info(f"LIKE dépassé pour {account['username']}. Attends {int(wait_time//60)}min {int(wait_time%60)}s", emoji="🕑")
                time.sleep(1)
                await send_message_with_retry(client, "SmmKingdomTasksBot", "❌Skip")
                return
            
        if not account:
            if last_sent_type == "instagram" and (now - last_sent_time) < MIN_MSG_INTERVAL:
                afficher_info("Username ignoré car Instagram vient d'être envoyé.", emoji="⚠️")
                return

            accounte = select_next_account()
            if not accounte:
                afficher_erreur("Aucun compte Instagram.", emoji="❌")
                return
    
            last_username = accounte["username"]
            await send_message_with_retry(client, "SmmKingdomTasksBot", last_username)
            print_compte(last_username)
            waiting_for_username = False
            last_sent_type = "username"
            last_sent_time = now
            return
        for try_login in range(2):
            try:
                processing_insta_task = True
                cl = await connect_instagram(account["username"], account["password"], client)
                if not cl:
                    return
                user_id, media_id, user, user2 = extract_instagram_ids(cl, link, message_text)
                id_to_show = user_id or media_id or "???"
                console.print(Text.assemble(horloge_ts(), (" [🌍] ",), ("Lien : ", "bold bright_cyan"), afficher_lien(link)))
                console.print(Text.assemble(horloge_ts(), (" [🆔] ",), ("Id : ", "bold bright_blue"), afficher_id(id_to_show)))
                console.print(Text.assemble(horloge_ts(), (" [🔧] ",), ("Action : ", "bold bright_magenta"), afficher_action(action)))
                last_username = account['username']
                last_password = account['password']
                key = f"{account['username']}|{link}|{action}"
                # --- LIKE ---
                if "like the post below" in action:
                    if not media_id:
                        media_id = cl.media_pk_from_url(link)
                    try:
                        cl.media_like(media_id)
                        afficher_succes(f"Post liké par {account['username']}", emoji="👍")
                        register_action_separated(account["username"], "like")
                        if last_completed_key != key:
                            if "no active task" not in last_bot_message_text.lower():
                                await send_message_with_retry(client, "SmmKingdomTasksBot", "✅Completed")
                            last_completed_key = key
                        break
                    except LoginRequired:
                        remove_ig_session(account["username"])
                        cl = await connect_instagram(account["username"], account["password"], client)
                        media_id = cl.media_pk_from_url(link)
                        cl.media_like(media_id)
                        afficher_succes(f"Post liké par {account['username']}", emoji="👍")
                        register_action_separated(account["username"], "like")
                        if last_completed_key != key:
                            if "no active task" not in last_bot_message_text.lower():
                                await send_message_with_retry(client, "SmmKingdomTasksBot", "✅Completed")
                            last_completed_key = key
                        break
                    except FeedbackRequired:
                        try:
                            save_device_settings(SESSION_DIR, (account["username"]), profile)
                            remove_ig_session(account["username"])
                            
                            cl = await connect_instagram(account["username"], account["password"], client)
                            media_id = cl.media_pk_from_url(link)
                            cl.media_like(media_id)
                            afficher_succes(f"Post liké par {account['username']}", emoji="👍")
                            register_action_separated(account["username"], "like")
                            if last_completed_key != key:
                                if "no active task" not in last_bot_message_text.lower():
                                    await send_message_with_retry(client, "SmmKingdomTasksBot", "✅Completed")
                                last_completed_key = key
                            break
                        except FeedbackRequired:
                            remove_ig_session(account["username"])
                            block_account_action(account["username"], account["password"], "like")
                            afficher_erreur("Like feedback_required")
                            await send_message_with_retry(client, "SmmKingdomTasksBot", "❌Skip")
                            break
                        break
                    break
                # --- FOLLOW ---
                elif "follow the profile" in action or "follow" in action:
                    try:
                        cl.user_follow(user_id)
                        afficher_succes(f"{account['username']} suit {user or user2}", emoji="❤️ ")
                        register_action_separated(account["username"], "follow")
                        if last_completed_key != key:
                            if "no active task" not in last_bot_message_text.lower():
                                await send_message_with_retry(client, "SmmKingdomTasksBot", "✅Completed")
                            last_completed_key = key
                        break
                    except LoginRequired:
                        remove_ig_session(account["username"])
                        cl = await connect_instagram(account["username"], account["password"], client)
                        cl.user_follow(user_id)
                        afficher_succes(f"{account['username']} suit {user or user2}", emoji="❤️ ")
                        register_action_separated(account["username"], "follow")
                        if last_completed_key != key:
                            if "no active task" not in last_bot_message_text.lower():
                                await send_message_with_retry(client, "SmmKingdomTasksBot", "✅Completed")
                            last_completed_key = key
                        break
                    except FeedbackRequired:
                        try:
                            save_device_settings(SESSION_DIR, (account["username"]), profile)
                            remove_ig_session(account["username"])
                            cl = await connect_instagram(account["username"], account["password"], client)
                            cl.user_follow(user_id)
                            afficher_succes(f"{account['username']} suit {user or user2}", emoji="❤️ ")
                            register_action_separated(account["username"], "follow")
                            if last_completed_key != key:
                                if "no active task" not in last_bot_message_text.lower():
                                    await send_message_with_retry(client, "SmmKingdomTasksBot", "✅Completed")
                                last_completed_key = key
                            break
                        except FeedbackRequired:
                            remove_ig_session(account["username"])
                            block_account_action(account["username"], account["password"], "follow")
                            afficher_erreur("Follow feedback_required")
                            await send_message_with_retry(client, "SmmKingdomTasksBot", "❌Skip")
                            break
                        break
                    break
                # --- VIDEO ---
                elif "open the video" in action or ("open the video" in action and "wait until the video ends" in action):
                    if not media_id:
                        media_id = cl.media_pk_from_url(link)
                    try:
                        video = cl.media_seen([media_id])
                    except LoginRequired:
                        remove_ig_session(account["username"])
                        cl = await connect_instagram(account["username"], account["password"], client)
                        video = cl.media_seen([media_id])
                    await asyncio.sleep(10)
                    if video:
                        afficher_succes(f"Vidéo vue par {account['username']}", emoji="🎬")
                        if last_completed_key != key:
                            if "no active task" not in last_bot_message_text.lower():
                                await send_message_with_retry(client, "SmmKingdomTasksBot", "✅Completed")
                            last_completed_key = key
                    break
                # --- STORIES ---
                elif any(k in action for k in ["stories view", "view story", "view all stories"]):
                    all_stories = []
                    try:
                        stories = cl.user_stories([user_id])
                        all_stories.extend(stories)
                    except Exception as e:
                        pass
                    try:
                        reels = cl.user_reel_feed([user_id])
                        if reels and hasattr(reels, 'items'):
                            for story in reels.items:
                                if story not in all_stories:
                                    all_stories.append(story)
                    except Exception:
                        pass
                    story_pks = [getattr(story, 'pk', None) for story in all_stories if hasattr(story, 'pk')]
                    story_pks = [pk for pk in story_pks if pk is not None]
                    if story_pks:
                        try:
                            cl.story_seen(story_pks)
                            for _ in story_pks:
                                await asyncio.sleep(random.uniform(1.2, 2.3))
                        except LoginRequired:
                            remove_ig_session(account["username"])
                            cl = await connect_instagram(account["username"], account["password"], client)
                            cl.story_seen(story_pks)
                            for _ in story_pks:
                                await asyncio.sleep(random.uniform(1.2, 2.3))
                        except Exception as e:
                            afficher_erreur(f"Erreur vue stories: {e}", emoji="⚠️")
                    key = f"{account['username']}|{link}|{action}"
                    if last_completed_key != key:
                        if "no active task" not in last_bot_message_text.lower():
                            afficher_succes(f"Stories de {user or user2} vues par {account['username']}", emoji="👀")
                            await send_message_with_retry(client, "SmmKingdomTasksBot", "✅Completed")
                        last_completed_key = key
                    break
                # --- COMMENTAIRE ---
                elif "leave the comment" in action:
                    pending_comment = {"link": link, "client": cl, "media_id": media_id}
                    processing_insta_task = False
                    break
                else:
                    afficher_info(f"Action non reconnue : {action}", emoji="⁉️")
                    break
            except Exception as e:
                password = get_password_for_username(last_username)
                await analyse_error2(e, last_username, last_password, client)
                await send_message_with_retry(client, "SmmKingdomTasksBot", "❌Skip")
                return 
            
            finally:
                await asyncio.sleep(2)
                processing_insta_task = False
        return

    if "no active tasks" in message_lower or "all condition" in message_lower or "choose social network" in message_lower:
        if last_sent_type == "username" and (now - last_sent_time) < MIN_MSG_INTERVAL:
            afficher_info("Instagram ignoré car username vient d'être envoyé.", emoji="⚠️")
            return
        if not waiting_for_username:
            await asyncio.sleep(0.5)
            await send_message_with_retry(client, "SmmKingdomTasksBot", "Instagram")
            waiting_for_username = True
            last_sent_type = "instagram"
            last_sent_time = now
        return

    if "balance" in message_lower and "invite your friend" in message_lower:
        match_cash = re.search(r"\s*Balance\s*[:：]?\s*\*?\*?([\d.,kK]+)\s*cashCoins", message_text, re.IGNORECASE)
        match_dollar = re.search(r"=\s*?\s*([\d.,]+)\s*\$??", message_text)
        cashcoins = match_cash.group(1) if match_cash else "???"
        dollars = match_dollar.group(1) if match_dollar else "???"
        console.print(Text.assemble(horloge_ts(), (" 💲 My Balance: ",), (f"{cashcoins}", "bold bright_magenta"), (" cashCoins = ", "italic white"), (f"{dollars}", "bold bright_green"), ("$",)))
        await asyncio.sleep(0.5)
        await client.send_message("SmmKingdomTasksBot", "📝Tasks📝")
        return

    if ("promo codes" in message_lower or
        "invite your friend to our service" in message_lower or
        "use this link to enter the system for managing" in message_lower or
        "do not complete previous task" in message_lower):
        await client.send_message("SmmKingdomTasksBot", "📝Tasks📝")
        return

    if ("list of available methods to withdraw" in message_lower or
        "to withdraw money you should have" in message_lower or
        "please write to our manager" in message_lower or
        "☑️ Add new account" in message_lower):
        await client.send_message("SmmKingdomTasksBot", "🔙Back")
        return

async def restore_loop(stop_event):
    while not stop_event.is_set():
        restore_unblocked_accounts()
        await asyncio.sleep(300)

async def surveillance(client, stop_event):
    CHECK_INTERVAL = 15 * 60  # 15 minutes
    while not stop_event.is_set():
        idu = lire_licence()
        machine_id, model, device = get_device_infos_from_db()
        status_code, api_status, message, temps_restant, _ = verifier_licence_en_ligne(idu, machine_id, model, device)
        if idu and cle:
            try:
                afficher_temps_abonnement(temps_restant)
            except Exception:
                pass
        if status_code in [2, 3, 5]:
            console.print(f"\n[red]{message or '⛔ Accès bloqué ou clé expirée.'}\n[/red]")
            await asyncio.sleep(2)
            try:
                await client.disconnect()
            except Exception:
                pass
            threading.Thread(target=verrouillage).start()
            stop_event.set()
            os._exit(99)
            break
        if api_status in ["expired", "forbidden", "error"] or (message and ("expiré" in (message.lower() or "") or "expired" in (message.lower() or ""))):
            console.print(f"\n[red]{message or '⛔ Abonnement expirée.'}\n[/red]")
            await asyncio.sleep(60)
            try:
                await client.disconnect()
            except Exception:
                pass
            threading.Thread(target=verrouillage).start()
            stop_event.set()
            os._exit(99)
            break
        await asyncio.sleep(CHECK_INTERVAL)
        
async def gestion_probleme_reseau(client, stop_event):
    while not stop_event.is_set():
        try:
            sock = socket.create_connection(("8.8.8.8", 53), timeout=10)
            sock.close()
            await asyncio.sleep(25)
        except OSError:
            console.print("[red]Réseau coupé. Arrêt du bot.[/red]")
            await client.disconnect()
            stop_event.set()
            os._exit(0)

def is_idle():
    global pending_comment, last_bot_msg_time
    if pending_comment is not None:
        return False
    if last_bot_msg_time is not None and time.time() - last_bot_msg_time < 10:
        return False
    return True
    
async def boucle_automatique(client, stop_event):
    global last_back_time, processing_insta_task, pending_comment, last_bot_msg_time
    global last_message_sent_to_bot, last_sent_time_to_bot
    retry_delay = [random.randint(5, 40) for _ in range(3)]  # * secondes d’attente entre chaque relance
    MAX_RETRIES = 3
    @client.on(events.NewMessage(chats="SmmKingdomTasksBot"))
    async def handler(event):
        global last_bot_msg_time, last_bot_message_text
        message_text = event.message.message
        last_bot_msg_time = time.time()
        last_bot_message_text = message_text.lower()
        message_text_lower = message_text.lower()
        # Utilisation :
        if should_extract_vip(message_text):
            extract_vip_from_message(message_text.lower())
        mtext = message_text.lower()
        if ("thank you for completing the task" in mtext or "thank you for using our" in mtext):
            last_bot_msg_time = time.time()
            cashcoins = extraire_cashcoins(message_text)
            if cashcoins:
                console.print(Text.assemble(horloge_ts(), (" [🎁] ",), ("Le bot vous remercie:", "italic green"), (f" +{cashcoins}", "bold italic bright_magenta"), ("cashCoins", "italic green")))
            else:
                afficher_succes("Le bot vous remercie.", emoji="🎁")
        elif "🟢🟢🟢🟢🟢" in mtext:
            last_bot_msg_time = time.time()
            try:
                username = message_text.split("🟢🟢🟢🟢🟢 ")[1].strip()
                afficher_succes(f"Un compte est déjà utilisable", emoji="🟢")
            except IndexError:
                afficher_erreur("Erreur : nom d'utilisateur non trouvé.")
        elif "on review now" in mtext:
            m = re.search(r'Account (\w+)', mtext)
            if m:
                username = m.group(1)
                password = get_account_password_vip(username)
                if "🟢 account" in mtext:
                    afficher_succes(f"Compte approuvé ou utilisable", emoji="🟩")
                    return True
                elif "🟡 account" in mtext:
                    afficher_erreur(f"{username} est en review, non utilisable", emoji="🟨")
                    block_account(username, password)
                    return True
        await insta_task_queue.put(event.message.message)
    while not stop_event.is_set():
        await asyncio.sleep(2)
        now = time.time()
        if not processing_insta_task and pending_comment is None and insta_task_queue.empty():
            # Boucle de relance selon dernier message (simplifiée)
            if last_bot_msg_time is not None and now - last_bot_msg_time > 40:
                time_before = last_bot_msg_time
                last_msg = (last_message_sent_to_bot or "").strip().lower()
                se_path = SELECTED_USER_FILE
                username = ""
                try:
                    with open(se_path, "r") as f:
                        data = json.load(f)
                        username = data.get("username", "").lower()
                except Exception:
                    username = ""
                # CAS 1: Si dernier message = "instagram"
                if last_msg == "instagram":
                    for retry in range(MAX_RETRIES):
                        if last_bot_msg_time != time_before:
                            break
                        relance_msg = username if retry < MAX_RETRIES - 1 else "Instagram"
                        await client.send_message("SmmKingdomTasksBot", relance_msg)
                        await asyncio.sleep(retry_delay[min(retry, len(retry_delay)-1)])
                    if last_bot_msg_time == time_before:
                        afficher_info("reprise de la boucle", emoji="🔄")
                        await asyncio.sleep(25)
                elif last_msg == username and username != "":
                    for retry in range(MAX_RETRIES):
                        if last_bot_msg_time != time_before:
                            break
                        relance_msg = "Instagram"
                        await client.send_message("SmmKingdomTasksBot", relance_msg)
                        await asyncio.sleep(retry_delay[min(retry, len(retry_delay)-1)])
                    if last_bot_msg_time == time_before:
                        afficher_info("reprise de la boucle", emoji="🔄")
                        await asyncio.sleep(25)
                else:
                    afficher_info("Message inattendu,'Instagram'", emoji="⚡")
                    await client.send_message("SmmKingdomTasksBot", "Instagram")
                    await asyncio.sleep(30)
                    if last_bot_msg_time == time_before:
                        afficher_info("Toujours aucune réponse, reprise de la boucle", emoji="🔄")
                        await asyncio.sleep(10)
        # Gestion du back automatique si idle
        if is_idle() and (last_back_time is None or now - last_back_time > 1800):
            if "balance" not in (last_bot_message_text or "").lower():
                await client.send_message("SmmKingdomTasksBot", "🔙Back")
            last_back_time = now

async def process_insta_tasks(client, stop_event):
    global processing_insta_task
    while not stop_event.is_set():
        try:
            task_message = await insta_task_queue.get()
            await traiter_message(task_message, client)
        except Exception as e:
            pass
        insta_task_queue.task_done()

def run_bot():
    while True:
        try:
            asyncio.run(main1())
        except Exception as e:
            err = str(e).lower()
            if "object is not subscriptable" in err:
                afficher_info(f"Tompoko tsy misy compte telegram connecté ilay TS-{n}, Connecteo @ mampiditra compte ao")
            else:
                afficher_info(f"Mialatsiny miverena @ mampiditra compte ao dia hamarino raha connecté ilay telegram TS-{n}anao na contacteo admin")
            time.sleep(10)
            os._exit(1)
        except SystemExit:
            pass
        except KeyboardInterrupt:
            return
        except asyncio.CancelledError:
            pass
async def main1():
    stop_event = asyncio.Event()
    sys.stdout.write(f'\x1b]2;𓆩【⚡ TASK TS-{n} DEMARRÉ】𓆪 \x07')
    init_directories()
    parameter()
    monitor_file(IG_ACCOUNTS_FILE)
    restore_all_sessions()
    telegram_client = await connect_telegram()
    tasks = [
        asyncio.create_task(surveillance(telegram_client, stop_event)),
        asyncio.create_task(gestion_probleme_reseau(telegram_client, stop_event)),
        asyncio.create_task(restore_loop(stop_event)),
        asyncio.create_task(boucle_automatique(telegram_client, stop_event)),
        asyncio.create_task(process_insta_tasks(telegram_client, stop_event)),
        asyncio.create_task(surveillance_auto_vip(telegram_client))
    ]
    try:
        while not stop_event.is_set():
            await asyncio.sleep(1)
    finally:
        for t in tasks:
            t.cancel()
        try:
            await telegram_client.disconnect()
        except Exception:
            pass
        except SystemExit:
            pass
        except KeyboardInterrupt:
            return
        except asyncio.CancelledError:
            pass
if __name__ == "__main__":
    while True:
        try:
            asyncio.run(main1())
        except Exception as e:
            afficher_erreur(f"Redémarrage du bot suite à une erreur", emoji="⚠️")
            time.sleep(2)
            os._exit(1)
