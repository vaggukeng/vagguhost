

import asyncio, os, sys, subprocess, psutil, json, logging, time, platform, re, shutil, html, importlib.util
from datetime import datetime, timedelta, time as dt_time
from typing import Dict, List, Tuple, Optional
import requests

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, ApplicationBuilder,
    CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, filters
)
from telegram.constants import ParseMode
from telegram import Bot as _OrigBot

# ---------------------------------------------------------------------------
# FONT CONVERTER  (ꫝʙᥴᴅꫀꜰɢʜɪᴊᴋʟꪑꪀꪮᴘǫʀꜱᴛᴜᴠᴡꪛʏᴢ  style)
# ---------------------------------------------------------------------------
def fc(text: str) -> str:
    """Convert a-z/A-Z letters to fancy Unicode font.
    HTML tags (<b>, <code>, <pre>) are kept intact so Telegram parses them.
    Content inside <code>/<pre> is kept as-is so IDs/logs stay readable.
    """
    NORMAL = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
    FANCY  = 'ꫝʙᥴᴅꫀꜰɢʜɪᴊᴋʟꪑꪀꪮᴘǫʀꜱᴛᴜᴠᴡꪛʏᴢꫝʙᥴᴅꫀꜰɢʜɪᴊᴋʟꪑꪀꪮᴘǫʀꜱᴛᴜᴠᴡꪛʏᴢ'
    table  = str.maketrans(NORMAL, FANCY)
    result = []
    i = 0
    in_code = False
    in_pre  = False
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == '<':
            lo = text[i:].lower()
            if lo.startswith('</code>'):
                in_code = False
                result.append('</code>'); i += 7; continue
            if lo.startswith('</pre>'):
                in_pre = False
                result.append('</pre>'); i += 6; continue
            if lo.startswith('<code'):
                in_code = True
            elif lo.startswith('<pre'):
                in_pre = True
            end = text.find('>', i)
            if end == -1:
                result.append(ch); i += 1; continue
            result.append(text[i:end + 1])
            i = end + 1
            continue
        if in_code or in_pre:
            result.append(ch)
        else:
            result.append(ch.translate(table))
        i += 1
    return ''.join(result)


# ---------------------------------------------------------------------------
# FONT-AWARE BOT WRAPPER
# reply_text()         ->  bot.send_message()       [intercepted here]
# edit_message_text()  ->  bot.edit_message_text()  [intercepted here]
# All outgoing text is auto-converted to the fancy font.
# ---------------------------------------------------------------------------
class FontBot(_OrigBot):
    async def send_message(self, chat_id, text=None, **kwargs):
        if text is not None:
            text = fc(text)
        return await super().send_message(chat_id, text=text, **kwargs)

    async def edit_message_text(self, text, *args, **kwargs):
        return await super().edit_message_text(fc(text), *args, **kwargs)



# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    handlers=[logging.FileHandler('vaggu_bot.log', encoding='utf-8'), logging.StreamHandler()]
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
class Config:
    BOT_TOKEN = "
    "8833080766:AAGHUT_2UG_LcCevFdehZ2Ug9A2Mw-BkpDs"          # <-- replace with new token
    OWNER_ID = 7724838720
    BOT_NAME = "✨ vaggu ~ Token Hosting Pro ✨"
    PASS_FREE = "VAGGUXGOD"

    BASE_DIR = os.path.join(os.path.expanduser("~"), "Music", "vaggu_bot")
    HOSTED_DIR = os.path.join(BASE_DIR, "hosted_scripts")
    DATA_DIR = os.path.join(BASE_DIR, "data")
    BACKUP_DIR = os.path.join(BASE_DIR, "backups")

    USERS_FILE = os.path.join(DATA_DIR, "users.json")
    PROCESSES_FILE = os.path.join(DATA_DIR, "processes.json")
    PROMO_FILE = os.path.join(DATA_DIR, "promo.json")
    SUBSCRIPTIONS_FILE = os.path.join(DATA_DIR, "subscriptions.json")
    AUDIT_FILE = os.path.join(DATA_DIR, "audit_log.json")
    ADMINS_FILE = os.path.join(DATA_DIR, "admins.json")

# ---------------------------------------------------------------------------
# PERMISSIONS
# ---------------------------------------------------------------------------
class Permission:
    FULL_ADMIN = "full_admin"

# ---------------------------------------------------------------------------
# PLANS
# ---------------------------------------------------------------------------
PLANS = {
    "free":      {"name": "Free Trial (3 days)",  "price": 0,  "days": 3},
    "basic_2w":  {"name": "Basic 2 Weeks",         "price": 35, "days": 14,
                  "note": "Contact owner to pay ₹35"},
    "pro_4w":    {"name": "Pro 4 Weeks",           "price": 0,  "days": 28,
                  "note": "Contact @rdp_ruler for payment details"}
}

# ---------------------------------------------------------------------------
# DATA HELPERS
# ---------------------------------------------------------------------------
def load_json(path, default=None):
    if default is None: default = {}
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        log.error(f"Load error {path}: {e}")
    return default

def save_json(path, data):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        log.error(f"Save error {path}: {e}")

def audit_log(action: str, user_id: int, details: str = "", admin_id: int = None):
    logs = load_json(Config.AUDIT_FILE, [])
    logs.append({
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "user_id": user_id,
        "admin_id": admin_id or user_id,
        "details": details
    })
    if len(logs) > 1000: logs = logs[-1000:]
    save_json(Config.AUDIT_FILE, logs)

# ---------------------------------------------------------------------------
# FOLDER CREATION & INITIAL FILES
# ---------------------------------------------------------------------------
for d in [Config.HOSTED_DIR, Config.DATA_DIR, Config.BACKUP_DIR]:
    os.makedirs(d, exist_ok=True)

for file_path in [Config.PROMO_FILE, Config.SUBSCRIPTIONS_FILE, Config.AUDIT_FILE, Config.ADMINS_FILE]:
    if not os.path.exists(file_path):
        save_json(file_path, {} if file_path != Config.AUDIT_FILE else [])

# Owner always full admin
admins = load_json(Config.ADMINS_FILE, {})
if str(Config.OWNER_ID) not in admins:
    admins[str(Config.OWNER_ID)] = {
        "permissions": [Permission.FULL_ADMIN],
        "role": "Owner",
        "added_by": Config.OWNER_ID,
        "added_date": datetime.now().isoformat()
    }
    save_json(Config.ADMINS_FILE, admins)

# ---------------------------------------------------------------------------
# ADMIN HELPERS
# ---------------------------------------------------------------------------
def is_admin(user_id: int) -> bool:
    return user_id == Config.OWNER_ID or str(user_id) in load_json(Config.ADMINS_FILE, {})

def add_admin(admin_id: int, added_by: int):
    admins = load_json(Config.ADMINS_FILE, {})
    admins[str(admin_id)] = {
        "permissions": [Permission.FULL_ADMIN],
        "role": "Admin",
        "added_by": added_by,
        "added_date": datetime.now().isoformat()
    }
    save_json(Config.ADMINS_FILE, admins)
    audit_log("admin_added", admin_id, "Full admin access granted", added_by)

def remove_admin(admin_id: int, removed_by: int):
    admins = load_json(Config.ADMINS_FILE, {})
    admins.pop(str(admin_id), None)
    save_json(Config.ADMINS_FILE, admins)
    audit_log("admin_removed", admin_id, "Admin removed", removed_by)

# ---------------------------------------------------------------------------
# SUBSCRIPTION MANAGEMENT
# ---------------------------------------------------------------------------
def check_subscription(user_id: int) -> dict:
    subs = load_json(Config.SUBSCRIPTIONS_FILE, {})
    uid = str(user_id)
    if uid not in subs:
        return assign_free_trial(user_id)
    sub = subs[uid]
    expiry = datetime.fromisoformat(sub["expiry_date"])
    if datetime.now() > expiry:
        return {"active": False, "plan": "expired", "expiry": sub["expiry_date"]}
    return {"active": True, "plan": sub.get("plan_name", sub.get("plan")), "expiry": sub["expiry_date"]}

def assign_free_trial(user_id: int) -> dict:
    if is_admin(user_id):
        return {"active": True, "plan": "Unlimited (Owner/Admin)", "expiry": "Never"}
    subs = load_json(Config.SUBSCRIPTIONS_FILE, {})
    expiry = datetime.now() + timedelta(days=3)
    subs[str(user_id)] = {
        "plan": "free",
        "plan_name": PLANS["free"]["name"],
        "price": 0,
        "start_date": datetime.now().isoformat(),
        "expiry_date": expiry.isoformat()
    }
    save_json(Config.SUBSCRIPTIONS_FILE, subs)
    audit_log("free_trial_assigned", user_id, "Free 3‑day trial")
    return {"active": True, "plan": "free", "expiry": expiry.isoformat()}

def activate_subscription(user_id: int, plan_key: str, admin_id: int) -> bool:
    if plan_key not in PLANS:
        return False
    plan = PLANS[plan_key]
    subs = load_json(Config.SUBSCRIPTIONS_FILE, {})
    expiry = datetime.now() + timedelta(days=plan["days"])
    subs[str(user_id)] = {
        "plan": plan_key,
        "plan_name": plan["name"],
        "price": plan["price"],
        "start_date": datetime.now().isoformat(),
        "expiry_date": expiry.isoformat(),
        "activated_by": admin_id,
        "note": plan.get("note", "")
    }
    save_json(Config.SUBSCRIPTIONS_FILE, subs)
    audit_log("subscription_activated", user_id,
              f"Plan: {plan['name']} (₹{plan['price'] if plan['price']>0 else 'Contact'})", admin_id)
    return True

def remove_subscription(user_id: int, removed_by: int) -> bool:
    subs = load_json(Config.SUBSCRIPTIONS_FILE, {})
    if str(user_id) in subs:
        del subs[str(user_id)]
        save_json(Config.SUBSCRIPTIONS_FILE, subs)
        audit_log("subscription_removed", user_id, "Subscription revoked", removed_by)
        ProcessManager.kill(user_id)
        return True
    return False

def has_claimed_free(user_id: int) -> bool:
    users = load_json(Config.USERS_FILE, {})
    return "free_claimed" in users.get(str(user_id), {})

def mark_free_claimed(user_id: int):
    users = load_json(Config.USERS_FILE, {})
    uid = str(user_id)
    if uid not in users:
        users[uid] = {}
    users[uid]["free_claimed"] = True
    save_json(Config.USERS_FILE, users)

# ---------------------------------------------------------------------------
# USER FOLDER HELPERS
# ---------------------------------------------------------------------------
def get_user_folder(user) -> str:
    users = load_json(Config.USERS_FILE)
    uid = str(user.id)
    name = user.username or f"user_{user.id}"
    if uid in users and isinstance(users[uid], dict):
        name = users[uid].get("folder", name)
    folder = os.path.join(Config.HOSTED_DIR, name)
    os.makedirs(folder, exist_ok=True)
    os.makedirs(os.path.join(folder, "logs"), exist_ok=True)
    return folder

def get_script_path(user) -> str:
    folder_name = os.path.basename(get_user_folder(user))
    return os.path.join(get_user_folder(user), f"{folder_name}.py")

def get_log_path(user) -> str:
    return os.path.join(get_user_folder(user), "logs", "output.log")

def get_error_log_path(user) -> str:
    return os.path.join(get_user_folder(user), "logs", "error.log")

# ---------------------------------------------------------------------------
# PACKAGE DETECTION (SAFE)
# ---------------------------------------------------------------------------
def get_imported_packages(script_path: str) -> List[str]:
    """Scan a Python script for imported top‑level packages."""
    imports = set()
    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
        for match in re.finditer(r'(?:from|import)\s+(\S+)', content):
            pkg = match.group(1).split('.')[0]
            if pkg.isidentifier() and pkg not in sys.stdlib_module_names:
                imports.add(pkg)
    except Exception as e:
        log.error(f"Error scanning imports: {e}")
    return list(imports)

def get_missing_packages(packages: List[str]) -> List[str]:
    """Check which packages are not installed using importlib.util."""
    missing = []
    for pkg in packages:
        if importlib.util.find_spec(pkg) is None:
            missing.append(pkg)
    return missing

# ---------------------------------------------------------------------------
# PROCESS MANAGER
# ---------------------------------------------------------------------------
class ProcessManager:
    @staticmethod
    def _all():
        return load_json(Config.PROCESSES_FILE)

    @staticmethod
    def _save(user_id, pid, script, folder):
        procs = ProcessManager._all()
        procs[str(user_id)] = {"pid": pid, "script": script, "folder": folder,
                                "started": datetime.now().isoformat()}
        save_json(Config.PROCESSES_FILE, procs)

    @staticmethod
    def _remove(user_id):
        procs = ProcessManager._all()
        procs.pop(str(user_id), None)
        save_json(Config.PROCESSES_FILE, procs)

    @staticmethod
    def is_running(user_id) -> Tuple[bool, Optional[Dict]]:
        procs = ProcessManager._all()
        data = procs.get(str(user_id))
        if not data: return False, None
        try:
            proc = psutil.Process(data["pid"])
            if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                return True, data
        except:
            pass
        ProcessManager._remove(user_id)
        return False, None

    @staticmethod
    def get_status(user_id) -> dict:
        running, data = ProcessManager.is_running(user_id)
        if not running: return {"running": False}
        try:
            proc = psutil.Process(data["pid"])
            with proc.oneshot():
                uptime = datetime.now() - datetime.fromisoformat(data["started"])
                return {
                    "running": True,
                    "pid": data["pid"],
                    "uptime": str(uptime).split('.')[0],
                    "cpu": round(proc.cpu_percent(), 1),
                    "ram_mb": round(proc.memory_info().rss / (1024**2), 1)
                }
        except:
            return {"running": False}

    @staticmethod
    def kill(user_id) -> int:
        killed = 0
        procs = ProcessManager._all()
        if str(user_id) in procs:
            try:
                proc = psutil.Process(procs[str(user_id)]["pid"])
                for child in proc.children(recursive=True):
                    child.kill(); killed += 1
                proc.kill(); killed += 1
            except: pass
            ProcessManager._remove(user_id)
        folder = get_user_folder(type('U', (), {'id': user_id, 'username': None}))
        for p in psutil.process_iter(['pid', 'cmdline', 'cwd']):
            try:
                cmd = ' '.join(p.info['cmdline'] or [])
                if folder in cmd or (p.info['cwd'] and folder in p.info['cwd']):
                    p.kill(); killed += 1
            except: continue
        return killed

    @staticmethod
    def start(user_id, script, folder) -> Tuple[bool, any]:
        if platform.system() == "Windows":
            # Remove "&& pause" so CMD closes after script ends (good for debugging)
            cmd = f'start "vaggu ~ User {user_id}" /min cmd /c "python "{script}""'
            subprocess.Popen(cmd, shell=True)
            time.sleep(5)  # wait a bit for process to appear (or fail)
            pid = None
            for p in psutil.process_iter(['pid', 'cmdline']):
                try:
                    if script in ' '.join(p.info['cmdline'] or []):
                        pid = p.info['pid']; break
                except: continue
            if pid:
                ProcessManager._save(user_id, pid, script, folder)
                return True, pid
            # No PID found – likely script crashed instantly; capture error output
            error_log = os.path.join(folder, "logs", "error.log")
            error_msg = ""
            if os.path.exists(error_log):
                with open(error_log, 'r', errors='ignore') as f:
                    error_msg = f.read()[-1000:]
            return False, f"Script crashed immediately. Error:\n{error_msg}" if error_msg else "Script crashed immediately (no error output)"
        else:
            proc = subprocess.Popen(
                [sys.executable, script],
                stdout=open(os.path.join(folder, "logs", "output.log"), 'a'),
                stderr=open(os.path.join(folder, "logs", "error.log"), 'a'),
                cwd=folder, start_new_session=True
            )
            pid = proc.pid
            if pid:
                ProcessManager._save(user_id, pid, script, folder)
                return True, pid
            return False, "No PID"

# ---------------------------------------------------------------------------
# EXPIRY CHECKER
# ---------------------------------------------------------------------------
async def check_expired_subscriptions(context: ContextTypes.DEFAULT_TYPE):
    subs = load_json(Config.SUBSCRIPTIONS_FILE, {})
    now = datetime.now()
    backup_needed = False
    for uid_str, sub in list(subs.items()):
        uid = int(uid_str)
        if is_admin(uid):
            continue
        expiry = datetime.fromisoformat(sub["expiry_date"])
        if now > expiry:
            running, _ = ProcessManager.is_running(uid)
            if running:
                killed = ProcessManager.kill(uid)
                log.info(f"Expired subscription – killed {killed} processes for user {uid}")
                backup_needed = True
                try:
                    await context.bot.send_message(
                        chat_id=uid,
                        text="⏰ <b>Your plan has expired!</b>\n\n"
                             "Your hosting has been stopped.\n"
                             "📌 Upgrade to continue:\n"
                             "• Basic 2 Weeks – ₹35 (contact owner)\n"
                             "• Pro 4 Weeks – contact @rdp_ruler\n\n"
                             "Contact the owner to renew.",
                        parse_mode=ParseMode.HTML)
                except: pass
    if backup_needed:
        await backup_and_send(context.bot, Config.OWNER_ID)

# ---------------------------------------------------------------------------
# PROMO + BACKUP
# ---------------------------------------------------------------------------
def get_promo_settings(): return load_json(Config.PROMO_FILE)
def save_promo_settings(data): save_json(Config.PROMO_FILE, data)

async def promo_broadcast_job(context: ContextTypes.DEFAULT_TYPE):
    promo = get_promo_settings()
    if not promo.get("enabled") or not promo.get("message", "").strip():
        return
    users = load_json(Config.USERS_FILE, {})
    sent = 0
    for uid in users:
        try:
            await context.bot.send_message(chat_id=int(uid), text=promo["message"])
            sent += 1
        except:
            pass
    log.info(f"Promo broadcast sent to {sent} users")

async def manage_promo_job(app_or_context):
    if isinstance(app_or_context, Application):
        job_queue = app_or_context.job_queue
    else:
        job_queue = app_or_context.job_queue
    for job in job_queue.jobs():
        if job.name == "promo_broadcast":
            job.schedule_removal()
    promo = get_promo_settings()
    if promo.get("enabled") and promo.get("message", "").strip():
        interval_hours = promo.get("interval_hours", 6)
        job_queue.run_repeating(promo_broadcast_job, interval=interval_hours*3600, first=10, name="promo_broadcast")

async def send_promo_now(context: ContextTypes.DEFAULT_TYPE):
    await promo_broadcast_job(context)

def create_backup():
    backup_dir = Config.BACKUP_DIR
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    zip_name = os.path.join(backup_dir, f"backup_{timestamp}")
    shutil.make_archive(zip_name, 'zip', Config.DATA_DIR)
    log.info(f"Backup created: {zip_name}.zip")
    backups = sorted([f for f in os.listdir(backup_dir) if f.endswith('.zip')])
    for old in backups[:-10]:
        os.remove(os.path.join(backup_dir, old))
    return zip_name + ".zip"

async def daily_backup_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        zip_path = create_backup()
        await context.bot.send_document(
            chat_id=Config.OWNER_ID,
            document=open(zip_path, 'rb'),
            caption="📦 Daily backup"
        )
    except Exception as e:
        log.error(f"Daily backup failed: {e}")

async def backup_and_send(bot, chat_id):
    loop = asyncio.get_running_loop()
    zip_path = await loop.run_in_executor(None, create_backup)
    try:
        await bot.send_document(
            chat_id=chat_id,
            document=open(zip_path, 'rb'),
            caption="📦 Backup after hosting session ended"
        )
    except Exception as e:
        log.error(f"Failed to send backup: {e}")

# ---------------------------------------------------------------------------
# KEYBOARDS
# ---------------------------------------------------------------------------
def welcome_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎁 Claim Free Trial", callback_data="claim_free")]
    ])

def user_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Upload Script (.py)", callback_data="upload_script")],
        [InlineKeyboardButton("📦 Install Packages", callback_data="install_pkgs")],
        [InlineKeyboardButton("▶️ Start Hosting", callback_data="start")],
        [InlineKeyboardButton("⏹️ Stop", callback_data="stop"),
         InlineKeyboardButton("🔄 Restart", callback_data="restart")],
        [InlineKeyboardButton("📊 Status", callback_data="status"),
         InlineKeyboardButton("📜 Logs", callback_data="logs")],
        [InlineKeyboardButton("💳 My Plan", callback_data="my_plan")],
        [InlineKeyboardButton("📡 Latency", callback_data="user_latency")],
    ])

def admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Statistics", callback_data="adm_stats"),
         InlineKeyboardButton("👥 Users", callback_data="adm_users")],
        [InlineKeyboardButton("🔍 Search User", callback_data="adm_search")],
        [InlineKeyboardButton("💳 Subscription Mgmt", callback_data="adm_subscriptions")],
        [InlineKeyboardButton("👑 Team Mgmt", callback_data="adm_team")],
        [InlineKeyboardButton("⚡ Bulk Operations", callback_data="adm_bulk")],
        [InlineKeyboardButton("🎯 Promo Controls", callback_data="adm_promo_menu")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="adm_broadcast")],
        [InlineKeyboardButton("📋 Audit Log", callback_data="adm_audit")],
        [InlineKeyboardButton("📡 Latency Test", callback_data="adm_latency")],
        [InlineKeyboardButton("📦 Backup Now", callback_data="adm_backup")],
        [InlineKeyboardButton("🔙 Close", callback_data="adm_close")],
    ])

def team_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Admin", callback_data="team_add")],
        [InlineKeyboardButton("➖ Remove Admin", callback_data="team_remove")],
        [InlineKeyboardButton("👁️ View Admins", callback_data="team_view")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_admin")],
    ])

def bulk_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ Start All", callback_data="bulk_start")],
        [InlineKeyboardButton("⏹️ Stop All", callback_data="bulk_stop")],
        [InlineKeyboardButton("🔄 Restart All", callback_data="bulk_restart")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_admin")],
    ])

def subscription_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ Activate Basic 2W", callback_data="sub_activate_basic")],
        [InlineKeyboardButton("💎 Activate Pro 4W", callback_data="sub_activate_pro")],
        [InlineKeyboardButton("🗑️ Remove Subscription", callback_data="sub_remove")],
        [InlineKeyboardButton("👁️ View All", callback_data="sub_view")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_admin")],
    ])

def promo_menu():
    promo = get_promo_settings()
    enabled = promo.get("enabled", False)
    status = "✅ ON" if enabled else "❌ OFF"
    interval = promo.get("interval_hours", 6)
    msg = promo.get("message", "")
    preview = (msg[:60] + "...") if len(msg) > 60 else (msg or "<i>No message set</i>")
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Status: {status}", callback_data="promo_toggle")],
        [InlineKeyboardButton(f"Interval: {interval}h", callback_data="promo_interval")],
        [InlineKeyboardButton(f"Msg: {preview}", callback_data="promo_set_msg")],
        [InlineKeyboardButton("📤 Send Now", callback_data="promo_send_now")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_admin")],
    ])

# ---------------------------------------------------------------------------
# ERROR HANDLER
# ---------------------------------------------------------------------------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("Exception while handling an update:", exc_info=context.error)
    try:
        await context.bot.send_message(
            Config.OWNER_ID,
            text=f"⚠️ Bot error:\n<pre>{html.escape(str(context.error))}</pre>",
            parse_mode=ParseMode.HTML
        )
    except:
        pass

# ---------------------------------------------------------------------------
# HANDLERS
# ---------------------------------------------------------------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    users = load_json(Config.USERS_FILE)
    disp_name = html.escape(user.first_name or f"User_{user.id}")

    if str(user.id) not in users:
        welcome_text = (
            f"✨ <b>Welcome to {html.escape(Config.BOT_NAME)}</b> ✨\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🚀 <b>Professional Bot Hosting</b>\n"
            "• Upload your Python script\n"
            "• Auto‑detect missing pip packages\n"
            "• Install & run your bot 24/7\n"
            "• See live terminal output\n\n"
            "👇 <b>Get started:</b>\n"
            "• 🎁 Claim your Free Trial (3 days)\n\n"
            "For paid plans, contact the owner."
        )
        await update.message.reply_text(
            welcome_text,
            reply_markup=welcome_keyboard(),
            parse_mode=ParseMode.HTML
        )
        return

    is_owner = (user.id == Config.OWNER_ID)
    is_admin_user = is_admin(user.id)

    if is_owner or is_admin_user:
        status = ProcessManager.get_status(user.id)
        if status["running"]:
            txt = f"🟢 <b>Live</b> | PID <code>{status['pid']}</code> | Uptime <code>{status['uptime']}</code>"
        else:
            txt = "🔴 <b>Offline</b>"
        role = "Owner" if is_owner else "Admin"
        await update.message.reply_text(
            f"👑 <b>{html.escape(role)} Access</b>\n\n"
            f"👤 {disp_name}\n"
            f"📊 {txt}\n"
            f"💳 Plan: <b>Unlimited</b> (never expires)\n\n"
            f"Use /admin for full panel.",
            reply_markup=user_menu(),
            parse_mode=ParseMode.HTML
        )
        return

    status = ProcessManager.get_status(user.id)
    sub = check_subscription(user.id)
    plan_text = f"💳 Plan: <b>{html.escape(sub.get('plan', 'N/A'))}</b> | Expires: {sub.get('expiry', 'N/A')[:10]}"
    if not sub["active"]:
        plan_text += "\n⚠️ <b>EXPIRED</b> – hosting disabled"
    if status["running"]:
        txt = f"🟢 <b>Live</b> | PID <code>{status['pid']}</code> | Uptime <code>{status['uptime']}</code>"
    else:
        txt = "🔴 <b>Offline</b>"
    await update.message.reply_text(
        f"✨ <b>{html.escape(Config.BOT_NAME)}</b>\n\n"
        f"👤 {disp_name}\n"
        f"📊 {txt}\n"
        f"{plan_text}\n\n"
        f"Select an option:",
        reply_markup=user_menu(),
        parse_mode=ParseMode.HTML
    )

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("❌ Access denied.")
        return
    await update.message.reply_text(
        "👑 <b>Admin Panel</b>\n\nChoose a function:",
        reply_markup=admin_menu(),
        parse_mode=ParseMode.HTML
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    data = query.data

    admin_user = is_admin(user.id)

    # ---- Free trial claim ----
    if data == "claim_free":
        users = load_json(Config.USERS_FILE)
        if str(user.id) in users:
            await query.answer("You are already registered.", show_alert=True)
            return
        if has_claimed_free(user.id):
            await query.edit_message_text("❌ You have already claimed your free trial.")
            return
        context.user_data['awaiting_claim_password'] = True
        await query.edit_message_text("🔐 Send the free trial password:")
        return

    if data == "back_admin":
        await query.edit_message_text("👑 <b>Admin Panel</b>", reply_markup=admin_menu(), parse_mode=ParseMode.HTML)
        return

    # ========== ADMIN CALLBACKS ==========
    if data.startswith("adm_") or data.startswith("team_") or data.startswith("bulk_") or \
       data.startswith("sub_") or data.startswith("promo_"):
        if not admin_user:
            await query.answer("⛔ Admin only", show_alert=True)
            return

        if data == "adm_stats":
            users = load_json(Config.USERS_FILE, {})
            running = sum(1 for uid in ProcessManager._all() if ProcessManager.is_running(int(uid))[0])
            subs = load_json(Config.SUBSCRIPTIONS_FILE, {})
            active_subs = sum(1 for s in subs.values() if datetime.fromisoformat(s["expiry_date"]) > datetime.now())
            text = (
                "📊 <b>Overall Statistics</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👥 Users: <code>{len(users)}</code>\n"
                f"⚡ Running: <code>{running}</code>\n"
                f"💳 Active Plans: <code>{active_subs}</code>"
            )
            await query.edit_message_text(text, parse_mode=ParseMode.HTML)

        elif data == "adm_users":
            users = load_json(Config.USERS_FILE, {})
            if not users:
                await query.edit_message_text("👥 No users.")
                return
            text = "👥 <b>User List</b>\n\n"
            for uid, info in users.items():
                status = ProcessManager.get_status(int(uid))
                emoji = "🟢" if status["running"] else "🔴"
                sub = check_subscription(int(uid))
                plan = sub.get("plan", "free") if sub else "free"
                text += f"{emoji} <code>{uid}</code> - {info.get('first_name', uid)} | Plan: {plan}\n"
            await query.edit_message_text(text, parse_mode=ParseMode.HTML)

        elif data == "adm_search":
            await query.edit_message_text("🔍 Send the user ID or username to search:")
            context.user_data['expect_search'] = True

        elif data == "adm_latency":
            start = time.time()
            await query.edit_message_text("📡 Testing...")
            await context.bot.send_message(chat_id=user.id, text="🏓 Ping")
            latency = round((time.time() - start) * 1000, 2)
            await query.edit_message_text(f"📡 Latency: <code>{latency} ms</code>", parse_mode=ParseMode.HTML)

        elif data == "adm_broadcast":
            await query.edit_message_text("📢 Send the message to broadcast:")
            context.user_data['expect_broadcast'] = True

        elif data == "adm_promo_menu":
            await query.edit_message_text("🎯 <b>Promo Controls</b>", reply_markup=promo_menu(), parse_mode=ParseMode.HTML)

        elif data == "promo_toggle":
            promo = get_promo_settings()
            promo["enabled"] = not promo.get("enabled", False)
            save_promo_settings(promo)
            await manage_promo_job(context)
            await query.edit_message_text("🎯 Promo updated", reply_markup=promo_menu())

        elif data == "promo_interval":
            await query.edit_message_text("⏱️ Send new interval in hours:")
            context.user_data['expect_promo_interval'] = True

        elif data == "promo_set_msg":
            await query.edit_message_text("📝 Send new promo message:")
            context.user_data['expect_promo_msg'] = True

        elif data == "promo_send_now":
            await query.edit_message_text("📤 Sending promo now...")
            await send_promo_now(context)
            await query.edit_message_text("✅ Promo broadcast sent!", reply_markup=promo_menu())

        elif data == "adm_team":
            await query.edit_message_text("👑 <b>Team Management</b>", reply_markup=team_menu(), parse_mode=ParseMode.HTML)

        elif data == "team_add":
            await query.edit_message_text("➕ Send the user ID to add as admin (full access):")
            context.user_data['expect_add_admin'] = True

        elif data == "team_remove":
            await query.edit_message_text("Send user ID to remove from admins:")
            context.user_data['expect_remove_admin'] = True

        elif data == "team_view":
            admins = load_json(Config.ADMINS_FILE, {})
            text = "👑 <b>Admins</b>\n\n"
            for aid, info in admins.items():
                text += (
                    f"<code>{aid}</code> - {info.get('role','N/A')}\n"
                    f"Added by: {info.get('added_by','?')}\n"
                    f"Date: {info.get('added_date','?')[:10]}\n\n"
                )
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=team_menu())

        elif data == "adm_bulk":
            await query.edit_message_text("⚡ <b>Bulk Operations</b>", reply_markup=bulk_menu(), parse_mode=ParseMode.HTML)

        elif data == "bulk_start":
            users = load_json(Config.USERS_FILE, {})
            started = 0
            for uid in users:
                uid_int = int(uid)
                if not ProcessManager.is_running(uid_int)[0]:
                    script = get_script_path(type('U', (), {'id': uid_int, 'username': None}))
                    if os.path.exists(script):
                        folder = get_user_folder(type('U', (), {'id': uid_int, 'username': None}))
                        success, _ = await asyncio.get_running_loop().run_in_executor(None, ProcessManager.start, uid_int, script, folder)
                        if success: started += 1
            await query.edit_message_text(f"✅ Started {started} users.", reply_markup=bulk_menu())
            audit_log("bulk_start", user.id, f"Started {started} users")

        elif data == "bulk_stop":
            users = load_json(Config.USERS_FILE, {})
            stopped = 0
            for uid in users:
                stopped += ProcessManager.kill(int(uid))
            await query.edit_message_text(f"✅ Stopped {stopped} processes.", reply_markup=bulk_menu())
            audit_log("bulk_stop", user.id, f"Stopped {stopped} processes")
            await backup_and_send(context.bot, user.id)

        elif data == "bulk_restart":
            users = load_json(Config.USERS_FILE, {})
            restarted = 0
            for uid in users:
                uid_int = int(uid)
                ProcessManager.kill(uid_int)
                await asyncio.sleep(0.5)
                script = get_script_path(type('U', (), {'id': uid_int, 'username': None}))
                if os.path.exists(script):
                    folder = get_user_folder(type('U', (), {'id': uid_int, 'username': None}))
                    success, _ = await asyncio.get_running_loop().run_in_executor(None, ProcessManager.start, uid_int, script, folder)
                    if success: restarted += 1
            await query.edit_message_text(f"✅ Restarted {restarted} users.", reply_markup=bulk_menu())
            audit_log("bulk_restart", user.id, f"Restarted {restarted} users")
            await backup_and_send(context.bot, user.id)

        elif data == "adm_subscriptions":
            await query.edit_message_text("💳 <b>Subscription Management</b>", reply_markup=subscription_menu(), parse_mode=ParseMode.HTML)

        elif data in ("sub_activate_basic", "sub_activate_pro"):
            plan_code = "basic_2w" if data == "sub_activate_basic" else "pro_4w"
            context.user_data['pending_sub_plan'] = plan_code
            await query.edit_message_text(
                f"💳 Activate <b>{html.escape(PLANS[plan_code]['name'])}</b>\n\n"
                "Please send the <b>user ID</b> of the recipient:",
                parse_mode=ParseMode.HTML
            )
            context.user_data['expect_activate_sub_user'] = True

        elif data == "sub_remove":
            await query.edit_message_text("🗑️ Send the user ID whose subscription you want to remove:")
            context.user_data['expect_remove_sub'] = True

        elif data == "sub_view":
            subs = load_json(Config.SUBSCRIPTIONS_FILE, {})
            text = "💳 <b>All Subscriptions</b>\n\n"
            for uid, sub in subs.items():
                status_icon = "🟢" if datetime.fromisoformat(sub["expiry_date"]) > datetime.now() else "🔴"
                text += (
                    f"{status_icon} <code>{uid}</code> - {sub.get('plan_name','?')}\n"
                    f"Expires: {sub['expiry_date'][:10]}\n"
                    f"Price: ₹{sub.get('price',0)}{' (contact)' if sub.get('note') else ''}\n\n"
                )
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=subscription_menu())

        elif data == "adm_audit":
            logs = load_json(Config.AUDIT_FILE, [])
            text = "📋 <b>Last 20 Audit Entries</b>\n\n"
            for entry in logs[-20:]:
                text += f"🕒 {entry['timestamp'][:19]}\n🔹 {entry['action']} (by {entry['admin_id']})\n📝 {entry['details']}\n\n"
            await query.edit_message_text(text, parse_mode=ParseMode.HTML)

        elif data == "adm_backup":
            await query.edit_message_text("📦 Creating backup...")
            zip_path = await asyncio.get_running_loop().run_in_executor(None, create_backup)
            await query.edit_message_text("📤 Sending backup...")
            with open(zip_path, 'rb') as f:
                await context.bot.send_document(
                    chat_id=user.id,
                    document=f,
                    caption="📦 Manual backup"
                )
            await query.edit_message_text("✅ Backup sent!", reply_markup=admin_menu())

        elif data == "adm_close":
            await query.message.delete()
        return

    # ========== USER CALLBACKS ==========
    if data == "user_latency":
        start = time.time()
        await query.edit_message_text("📡 Testing...")
        await context.bot.send_message(chat_id=user.id, text="🏓 Ping")
        latency = round((time.time() - start) * 1000, 2)
        await query.edit_message_text(f"📡 Latency: <code>{latency} ms</code>", reply_markup=user_menu(), parse_mode=ParseMode.HTML)

    elif data == "upload_script":
        await query.edit_message_text("📤 Please send your Python (.py) file.")
        context.user_data['expect_script'] = True

    elif data == "install_pkgs":
        await query.edit_message_text("📦 Send the packages to install, separated by spaces (e.g. <code>requests telethon</code>)", parse_mode=ParseMode.HTML)
        context.user_data['expect_pip_packages'] = True

    elif data == "my_plan":
        sub = check_subscription(user.id)
        text = (
            "💳 <b>Your Plan</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Name: {sub.get('plan','free')}\n"
            f"Expires: {sub.get('expiry','?')[:10]}\n"
            f"Status: {'Active' if sub['active'] else 'Expired'}"
        )
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=user_menu())

    elif data == "start":
        sub = check_subscription(user.id)
        if not sub["active"]:
            await query.edit_message_text(
                "⛔ <b>Your plan has expired!</b>\n\n"
                "Upgrade to continue hosting:\n"
                "• Basic 2 Weeks – ₹35 (contact owner)\n"
                "• Pro 4 Weeks – contact @rdp_ruler",
                reply_markup=user_menu(),
                parse_mode=ParseMode.HTML
            )
            return
        script = get_script_path(user)
        if not os.path.exists(script):
            await query.edit_message_text("❌ No script found. Upload your .py file first.", reply_markup=user_menu())
            return
        if ProcessManager.is_running(user.id)[0]:
            await query.edit_message_text("⚠️ Already running.", reply_markup=user_menu())
            return

        # Scan for missing packages and offer to install
        imports = get_imported_packages(script)
        missing = get_missing_packages(imports)
        if missing:
            context.user_data['auto_install_missing'] = missing
            context.user_data['auto_start_after_install'] = True
            await query.edit_message_text(
                f"🔍 Missing packages detected: <code>{', '.join(missing)}</code>\n\n"
                "Do you want me to install them automatically and then start your script?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Install & Start", callback_data="install_missing_and_start")],
                    [InlineKeyboardButton("❌ Skip", callback_data="skip_install_start")]
                ])
            )
            return

        # No missing packages, start directly
        loop = asyncio.get_running_loop()
        success, pid = await loop.run_in_executor(None, ProcessManager.start, user.id, script, get_user_folder(user))
        if success:
            # Show initial output (both stdout and stderr)
            stdout = ""
            stderr = ""
            out_path = get_log_path(user)
            err_path = get_error_log_path(user)
            if os.path.exists(out_path):
                with open(out_path, 'r', errors='ignore') as f:
                    stdout = f.read()[-1500:]
            if os.path.exists(err_path):
                with open(err_path, 'r', errors='ignore') as f:
                    stderr = f.read()[-500:]
            combined = stdout
            if stderr.strip():
                combined += f"\n\n<b>Errors:</b>\n{stderr}"
            await query.edit_message_text(
                f"✅ Started (PID <code>{pid}</code>).\n\n<b>Terminal Output:</b>\n<pre>{html.escape(combined) or 'No output yet.'}</pre>",
                reply_markup=user_menu(),
                parse_mode=ParseMode.HTML
            )
        else:
            # Start failed – show error details
            await query.edit_message_text(
                f"❌ <b>Script did not start!</b>\n{html.escape(str(pid))}",
                reply_markup=user_menu(),
                parse_mode=ParseMode.HTML
            )

    elif data == "install_missing_and_start":
        missing = context.user_data.get('auto_install_missing', [])
        if not missing:
            await query.edit_message_text("❌ Nothing to install.", reply_markup=user_menu())
            return
        await query.edit_message_text(f"⏳ Installing {', '.join(missing)}...")
        cmd = [sys.executable, "-m", "pip", "install"] + missing
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                output = stdout.decode()
                await query.edit_message_text(
                    f"✅ Packages installed.\n<pre>{html.escape(output[-500:])}</pre>",
                    parse_mode=ParseMode.HTML
                )
                # Now start the script
                script = get_script_path(user)
                if not os.path.exists(script):
                    await query.edit_message_text("❌ Script file not found after install.", reply_markup=user_menu())
                    return
                loop = asyncio.get_running_loop()
                success, pid = await loop.run_in_executor(None, ProcessManager.start, user.id, script, get_user_folder(user))
                if success:
                    stdout = ""
                    stderr = ""
                    out_path = get_log_path(user)
                    err_path = get_error_log_path(user)
                    if os.path.exists(out_path):
                        with open(out_path, 'r', errors='ignore') as f:
                            stdout = f.read()[-1500:]
                    if os.path.exists(err_path):
                        with open(err_path, 'r', errors='ignore') as f:
                            stderr = f.read()[-500:]
                    combined = stdout
                    if stderr.strip():
                        combined += f"\n\n<b>Errors:</b>\n{stderr}"
                    await query.edit_message_text(
                        f"✅ Started (PID <code>{pid}</code>).\n\n<b>Terminal Output:</b>\n<pre>{html.escape(combined) or 'No output yet.'}</pre>",
                        reply_markup=user_menu(),
                        parse_mode=ParseMode.HTML
                    )
                else:
                    await query.edit_message_text(
                        f"❌ <b>Script did not start!</b>\n{html.escape(str(pid))}",
                        reply_markup=user_menu(),
                        parse_mode=ParseMode.HTML
                    )
            else:
                error = stderr.decode()
                await query.edit_message_text(
                    f"❌ Installation failed:\n<pre>{html.escape(error[-500:])}</pre>",
                    reply_markup=user_menu(),
                    parse_mode=ParseMode.HTML
                )
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {html.escape(str(e))}", reply_markup=user_menu())
        finally:
            context.user_data.pop('auto_install_missing', None)
            context.user_data.pop('auto_start_after_install', None)

    elif data == "skip_install_start":
        context.user_data.pop('auto_install_missing', None)
        context.user_data.pop('auto_start_after_install', None)
        script = get_script_path(user)
        if not os.path.exists(script):
            await query.edit_message_text("❌ No script found.", reply_markup=user_menu())
            return
        loop = asyncio.get_running_loop()
        success, pid = await loop.run_in_executor(None, ProcessManager.start, user.id, script, get_user_folder(user))
        if success:
            stdout = ""
            stderr = ""
            out_path = get_log_path(user)
            err_path = get_error_log_path(user)
            if os.path.exists(out_path):
                with open(out_path, 'r', errors='ignore') as f:
                    stdout = f.read()[-1500:]
            if os.path.exists(err_path):
                with open(err_path, 'r', errors='ignore') as f:
                    stderr = f.read()[-500:]
            combined = stdout
            if stderr.strip():
                combined += f"\n\n<b>Errors:</b>\n{stderr}"
            await query.edit_message_text(
                f"✅ Started (PID <code>{pid}</code>).\n\n<b>Terminal Output:</b>\n<pre>{html.escape(combined) or 'No output yet.'}</pre>",
                reply_markup=user_menu(),
                parse_mode=ParseMode.HTML
            )
        else:
            await query.edit_message_text(
                f"❌ <b>Script did not start!</b>\n{html.escape(str(pid))}",
                reply_markup=user_menu(),
                parse_mode=ParseMode.HTML
            )

    elif data == "stop":
        killed = ProcessManager.kill(user.id)
        await query.edit_message_text(f"✅ Stopped ({killed} processes).", reply_markup=user_menu())
        if killed > 0:
            await backup_and_send(context.bot, Config.OWNER_ID)

    elif data == "restart":
        sub = check_subscription(user.id)
        if not sub["active"]:
            await query.edit_message_text("⛔ Plan expired. Cannot restart.", reply_markup=user_menu())
            return
        killed = ProcessManager.kill(user.id)
        await asyncio.sleep(2)
        script = get_script_path(user)
        if os.path.exists(script):
            loop = asyncio.get_running_loop()
            success, pid = await loop.run_in_executor(None, ProcessManager.start, user.id, script, get_user_folder(user))
            await query.edit_message_text(
                f"✅ Restarted (PID <code>{pid}</code>)" if success else f"❌ Failed: {pid}",
                reply_markup=user_menu(),
                parse_mode=ParseMode.HTML
            )
            if killed > 0:
                await backup_and_send(context.bot, Config.OWNER_ID)
        else:
            await query.edit_message_text("❌ No script.", reply_markup=user_menu())

    elif data == "status":
        s = ProcessManager.get_status(user.id)
        if s["running"]:
            txt = (
                f"🟢 <b>Running</b>\n"
                f"├ PID: <code>{s['pid']}</code>\n"
                f"├ Uptime: <code>{s['uptime']}</code>\n"
                f"├ CPU: <code>{s['cpu']}%</code>\n"
                f"└ RAM: <code>{s['ram_mb']} MB</code>"
            )
        else:
            txt = "🔴 <b>Stopped</b>"
        await query.edit_message_text(txt, reply_markup=user_menu(), parse_mode=ParseMode.HTML)

    elif data == "logs":
        out_path = get_log_path(user)
        err_path = get_error_log_path(user)
        logs = ""
        if os.path.exists(out_path):
            with open(out_path, 'r', errors='ignore') as f:
                logs = f.read()[-2000:]
        if os.path.exists(err_path):
            with open(err_path, 'r', errors='ignore') as f:
                err_logs = f.read()[-500:]
                if err_logs.strip():
                    logs += f"\n\n<b>Errors:</b>\n{err_logs}"
        if not logs.strip(): logs = "No logs."
        await query.edit_message_text(f"📜 <b>Terminal Output:</b>\n<pre>{html.escape(logs)}</pre>", reply_markup=user_menu(), parse_mode=ParseMode.HTML)

# ---------------------------------------------------------------------------
# MESSAGE HANDLER
# ---------------------------------------------------------------------------
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text or ""
    users = load_json(Config.USERS_FILE)

    if context.user_data.get('awaiting_claim_password'):
        if text == Config.PASS_FREE:
            if str(user.id) not in users:
                users[str(user.id)] = {
                    "first_name": user.first_name,
                    "username": user.username,
                    "joined": datetime.now().isoformat(),
                    "folder": user.username or f"user_{user.id}"
                }
                save_json(Config.USERS_FILE, users)
            if has_claimed_free(user.id):
                await update.message.reply_text("❌ You have already claimed your free trial.")
            else:
                assign_free_trial(user.id)
                mark_free_claimed(user.id)
                expiry = (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d')
                await update.message.reply_text(
                    f"✅ <b>Free Trial Activated!</b>\n\n"
                    f"🎉 Your plan: <b>Free Trial (3 days)</b>\n"
                    f"📅 Expires on: {expiry}\n\n"
                    f"Now upload your script and start hosting.",
                    reply_markup=user_menu(),
                    parse_mode=ParseMode.HTML
                )
        else:
            await update.message.reply_text("❌ Incorrect password. Try again or /start")
        context.user_data.pop('awaiting_claim_password', None)
        return

    if str(user.id) not in users:
        await update.message.reply_text("👋 Please use /start to claim your free trial.")
        return

    # ---- Script upload (with automatic package detection) ----
    if context.user_data.get('expect_script'):
        if update.message.document and update.message.document.file_name.endswith('.py'):
            file = await update.message.document.get_file()
            script_path = get_script_path(user)
            await file.download_to_drive(script_path)
            await update.message.reply_text("✅ Script uploaded successfully!", reply_markup=user_menu())

            # Automatically scan for missing packages
            imports = get_imported_packages(script_path)
            missing = get_missing_packages(imports)
            if missing:
                context.user_data['auto_install_missing'] = missing
                context.user_data['auto_start_after_install'] = True
                await update.message.reply_text(
                    f"🔍 Missing packages detected: <code>{', '.join(missing)}</code>\n\n"
                    "Do you want me to install them automatically and then start your script?",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ Install & Start", callback_data="install_missing_and_start")],
                        [InlineKeyboardButton("❌ Skip", callback_data="skip_install_start")]
                    ])
                )
        else:
            await update.message.reply_text("❌ Please send a valid .py file.")
        context.user_data['expect_script'] = False
        return

    # ---- Pip packages ----
    if context.user_data.get('expect_pip_packages'):
        packages = text.strip().split()
        if not packages:
            await update.message.reply_text("❌ No packages provided.")
            context.user_data.pop('expect_pip_packages', None)
            return
        msg = await update.message.reply_text("⏳ Installing packages...")
        cmd = [sys.executable, "-m", "pip", "install"] + packages
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                output = stdout.decode()
                await msg.edit_text(
                    f"✅ Packages installed successfully:\n<pre>{html.escape(output[-1000:])}</pre>",
                    parse_mode=ParseMode.HTML
                )
            else:
                error = stderr.decode()
                await msg.edit_text(
                    f"❌ Installation failed:\n<pre>{html.escape(error[-1000:])}</pre>",
                    parse_mode=ParseMode.HTML
                )
        except Exception as e:
            await msg.edit_text(f"❌ Error: {html.escape(str(e))}")
        context.user_data.pop('expect_pip_packages', None)
        return

    # Admin: search user
    if context.user_data.get('expect_search'):
        if not is_admin(user.id):
            await update.message.reply_text("⛔ Admin only.")
        else:
            query = text.strip().lower()
            found = False
            for uid, info in users.items():
                if (query in uid or
                    query in (info.get('first_name', '') or '').lower() or
                    query in (info.get('username', '') or '').lower()):
                    status = ProcessManager.get_status(int(uid))
                    emoji = "🟢" if status["running"] else "🔴"
                    sub = check_subscription(int(uid))
                    plan = sub.get("plan", "free") if sub else "free"
                    expiry = sub.get("expiry", "?")[:10] if sub else "?"
                    await update.message.reply_text(
                        f"🔍 <b>User Found:</b>\n"
                        f"ID: <code>{uid}</code>\n"
                        f"Name: {info.get('first_name', 'N/A')}\n"
                        f"Username: @{info.get('username', 'N/A')}\n"
                        f"Status: {emoji} {'Running' if status['running'] else 'Stopped'}\n"
                        f"Plan: {plan}\n"
                        f"Expires: {expiry}",
                        parse_mode=ParseMode.HTML
                    )
                    found = True
                    break
            if not found:
                await update.message.reply_text("❌ No user found matching that query.")
        context.user_data['expect_search'] = False
        return

    # Admin: add admin
    if context.user_data.get('expect_add_admin'):
        if user.id != Config.OWNER_ID:
            await update.message.reply_text("⛔ Only owner can add admins.")
        else:
            try:
                new_admin_id = int(text.strip())
                add_admin(new_admin_id, user.id)
                await update.message.reply_text(f"✅ User <code>{new_admin_id}</code> is now admin with full access.", parse_mode=ParseMode.HTML)
            except ValueError:
                await update.message.reply_text("❌ Invalid user ID.")
        context.user_data['expect_add_admin'] = False
        return

    # Admin: remove admin
    if context.user_data.get('expect_remove_admin'):
        if user.id != Config.OWNER_ID:
            await update.message.reply_text("⛔ Only owner can remove admins.")
        else:
            try:
                remove_id = int(text.strip())
                remove_admin(remove_id, user.id)
                await update.message.reply_text(f"✅ Admin <code>{remove_id}</code> removed.", parse_mode=ParseMode.HTML)
            except ValueError:
                await update.message.reply_text("❌ Invalid user ID.")
        context.user_data['expect_remove_admin'] = False
        return

    # Subscription activation (admin)
    if context.user_data.get('expect_activate_sub_user'):
        plan_code = context.user_data.get('pending_sub_plan')
        if not plan_code:
            await update.message.reply_text("❌ Session expired. Start again.")
        elif not is_admin(user.id):
            await update.message.reply_text("⛔ Admin only.")
        else:
            try:
                target_id = int(text.strip())
                if activate_subscription(target_id, plan_code, user.id):
                    plan = PLANS[plan_code]
                    expiry_date = (datetime.now() + timedelta(days=plan['days'])).strftime('%Y-%m-%d')
                    await update.message.reply_text(
                        f"✅ <b>{html.escape(plan['name'])}</b> activated for user <code>{target_id}</code>.\n"
                        f"Expires: {expiry_date}",
                        parse_mode=ParseMode.HTML
                    )
                    try:
                        await context.bot.send_message(
                            chat_id=target_id,
                            text=f"💳 <b>Subscription Activated!</b>\n\n"
                                 f"Your plan: <b>{html.escape(plan['name'])}</b>\n"
                                 f"Expires on: {expiry_date}\n\n"
                                 f"Happy hosting! 🚀",
                            parse_mode=ParseMode.HTML
                        )
                    except:
                        await update.message.reply_text("⚠️ Couldn't notify the user (they may not have started the bot).")
                else:
                    await update.message.reply_text("❌ Activation failed. Invalid plan code.")
            except ValueError:
                await update.message.reply_text("❌ Invalid user ID.")
            finally:
                context.user_data['expect_activate_sub_user'] = False
                context.user_data.pop('pending_sub_plan', None)
        return

    # Subscription removal (admin)
    if context.user_data.get('expect_remove_sub'):
        if not is_admin(user.id):
            await update.message.reply_text("⛔ Admin only.")
        else:
            try:
                target_id = int(text.strip())
                if remove_subscription(target_id, user.id):
                    await update.message.reply_text(f"✅ Subscription for user <code>{target_id}</code> has been removed.", parse_mode=ParseMode.HTML)
                    try:
                        await context.bot.send_message(
                            chat_id=target_id,
                            text="🗑️ <b>Your subscription has been revoked.</b>\n\n"
                                 "You no longer have an active plan. Please /start to see options.",
                            parse_mode=ParseMode.HTML
                        )
                    except:
                        pass
                else:
                    await update.message.reply_text("ℹ️ That user doesn't have an active subscription.")
            except ValueError:
                await update.message.reply_text("❌ Invalid user ID.")
        context.user_data['expect_remove_sub'] = False
        return

    # Other admin inputs
    if context.user_data.get('expect_broadcast'):
        if not is_admin(user.id):
            await update.message.reply_text("⛔ Admin only.")
        else:
            users_list = load_json(Config.USERS_FILE, {})
            success = 0
            for uid in users_list:
                try:
                    await context.bot.send_message(chat_id=int(uid), text=f"📢 {text}", parse_mode=ParseMode.HTML)
                    success += 1
                except: pass
            await update.message.reply_text(f"✅ Broadcast sent to {success}/{len(users_list)} users.")
        context.user_data['expect_broadcast'] = False
        return

    if context.user_data.get('expect_promo_interval'):
        if user.id != Config.OWNER_ID:
            await update.message.reply_text("⛔ Admin only.")
        else:
            try:
                interval = int(text.strip())
                if interval < 1: raise ValueError
                promo = get_promo_settings()
                promo["interval_hours"] = interval
                save_promo_settings(promo)
                await manage_promo_job(context)
                await update.message.reply_text(f"✅ Promo interval set to {interval}h.")
            except:
                await update.message.reply_text("❌ Invalid number.")
        context.user_data['expect_promo_interval'] = False
        return

    if context.user_data.get('expect_promo_msg'):
        if user.id != Config.OWNER_ID:
            await update.message.reply_text("⛔ Admin only.")
        else:
            promo = get_promo_settings()
            promo["message"] = text.strip()
            save_promo_settings(promo)
            await manage_promo_job(context)
            await update.message.reply_text("✅ Promo message updated.")
        context.user_data['expect_promo_msg'] = False
        return

    await update.message.reply_text("Use the menu.", reply_markup=user_menu())

# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    print("Starting vaggu ~ Token Hosting Pro (Music Edition)...")
    app = ApplicationBuilder().token(Config.BOT_TOKEN).bot_class(FontBot).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.ALL, message_handler))
    app.add_error_handler(error_handler)

    app.job_queue.run_repeating(check_expired_subscriptions, interval=3600, first=60, name="expiry_check")
    app.job_queue.run_daily(daily_backup_job, time=dt_time(hour=0, minute=0), name="daily_backup")

    async def post_init(application: Application):
        await manage_promo_job(application)

    app.post_init = post_init

    log.info("✅ vaggu ~ Token Hosting Pro started (Music folder)")
    print("✅ Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
