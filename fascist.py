import telebot
import threading
import time
import re
import json
import random
from datetime import datetime
from flask import Flask

# ---------------- Flask setup for 24/7 uptime ----------------
app = Flask(__name__)

@app.route('/')
def home():
    # You may need to replace the URL with your actual bot/repo link
    return "Bot is running 24/7! (v2.2)" 

def run_flask():
    app.run(host="0.0.0.0", port=3000)

threading.Thread(target=run_flask).start()
# ------------------------------------------------------------

# 🛑 1. BOT TOKEN ကို ဤနေရာတွင် အစားထိုးပါ
API_TOKEN = '8303335168:AAE5djB43m-TuXJaJhRCwZRIztyYaqfX9KQ' 
# ပြင်ဆင်ချက်: skip_pending=True ကို ထည့်သွင်းခြင်း (Bot ပိတ်ထားစဉ်အတွင်း ရောက်လာသော မက်ဆေ့ခ်ျ/Command များကို ကျော်ဖျက်ရန်)
bot = telebot.TeleBot(API_TOKEN, parse_mode="HTML", skip_pending=True)

# 🛑 2. MAIN OWNER IDs များကို ဤနေရာတွင် အစားထိုးပါ (ID တစ်ခု သို့မဟုတ် နှစ်ခု)
# NOTE: ဤ ID များကို File မရှိလျှင် ပထမဆုံးအကြိမ် စတင်အသုံးပြုရန်အတွက်သာ သုံးသည်။
INITIAL_OWNER_TUPLE = (8201358407, 7690724545) 

GROUPS_FILE = "groups.json"
USERS_FILE = "users.json"
REPLIES_FILE = "replies.txt"
OWNERS_FILE = "owners.json" # New file for persistent owners

# ---------------- Global Variables ----------------
data_lock = threading.Lock()
SAVE_GROUPS_NEEDED = threading.Event()
SAVE_USERS_NEEDED = threading.Event()

# Key: (chat_id, user_id), Value: {"ghost": True/False, "reply": True/False, "ghost_admin": admin_id, "reply_admin": admin_id}
active_targets = {} 
active_users = {}  # Attack: key: (chat_id, user_id), value: {"active": True, "owner": admin_id}
target_nicknames = {}
message_speed = 0.6
sent_messages = []

# Reply Management
dm_listen_mode = set() 
# ---------------------------------------------------------------------------

# ---------------- File I/O Functions ----------------
def load_owners(initial_owners_tuple):
    """owners.json မှ Owners များကို Load လုပ်သည်။ မရှိပါက hardcoded list ကို သုံးသည်။"""
    try:
        with open(OWNERS_FILE, "r") as f:
            # Use a set for efficient checking
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        # Fallback to the initial hardcoded list (as a set)
        print(f"Warning: {OWNERS_FILE} not found or corrupted. Using hardcoded initial owners.")
        return set(initial_owners_tuple)

def save_owners():
    """လက်ရှိ Owner များ၏ စာရင်းကို owners.json သို့ Save လုပ်သည်"""
    global BOT_OWNERS
    try:
        with open(OWNERS_FILE, "w") as f:
            # Save as a list for JSON
            json.dump(list(BOT_OWNERS), f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving owners file: {e}")
        return False

def load_groups():
    try:
        with open(GROUPS_FILE, "r") as f:
            return set(json.load(f))
    except:
        return set()

def save_groups():
    with open(GROUPS_FILE, "w") as f:
        json.dump(list(groups), f)

def load_users():
    try:
        with open(USERS_FILE, "r") as f:
            return set(json.load(f))
    except:
        return set()

def save_users():
    with open(USERS_FILE, "w") as f:
        json.dump(list(users), f)

def load_auto_messages():
    """replies.txt မှ Messages များကို Load လုပ်ပါသည်"""
    try:
        with open(REPLIES_FILE, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
            return lines
    except FileNotFoundError:
        # File မရှိရင် Default စာသား အနည်းငယ်ကို ပြန်ပေးခြင်း
        return [
            "ဟိုင်းဖာသည်မသားဘာဖြစ်တာလည်း မင်းအမေနောက်လင်ယူသွားလို့လား😂👌",
            "ငါလိုးမဖာသည်မသားမင်းအမေဘယ်သူလိုးသွားသလဲ😂👌",
            "အေးတပည့် ဘာဖြစ်တာတုန်းအဲ့တာ မျက်ရည်မချူနဲ့မသနားဘူးကွ😂👌",
            "ဖာသည်မသားလေးကိုက်စရာရှိကိုက်ပါဟ ဘယ်ငေးနေတာလည်း😂👌",
            "မင်းအမေစဖုတ်ဘာလို့မဲတာလည်း အဖြေရှာမရဖြစ်နေတာလား😂👌"
        ]
    except Exception as e:
        print(f"Error loading replies.txt: {e}")
        return []

def save_auto_messages(messages_list):
    """Messages များကို replies.txt သို့ Save လုပ်ပါသည်"""
    try:
        with open(REPLIES_FILE, "w", encoding="utf-8") as f:
            for msg in messages_list:
                f.write(msg + "\n")
        return True
    except Exception as e:
        print(f"Error saving replies.txt: {e}")
        return False

# Initialize Data
groups = load_groups()
users = load_users()
BOT_OWNERS = load_owners(INITIAL_OWNER_TUPLE) # The actual mutable owner list
banned_users = set()
auto_messages = load_auto_messages()
if not auto_messages:
    # ensure default messages are saved if replies.txt was empty/not found
    auto_messages = load_auto_messages() 
    if auto_messages:
        save_auto_messages(auto_messages)

# ---------------- Logger ----------------
def log_command(user, chat, command, details=""):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user_info = f"{user.first_name or ''} {user.last_name or ''}".strip()
    username = f"@{user.username}" if user.username else "NoUsername"
    chat_name = chat.title if hasattr(chat, "title") and chat.title else "Private"
    log_text = (
        f"🪵 Bot Command Log\n\n"
        f"⏰ Time: {timestamp}\n"
        f"👤 User: {user_info} ({username}) (ID: {user.id})\n"
        f"💬 Chat: {chat_name} (ID: {chat.id})\n"
        f"🔧 Command: {command}\n"
        f"📝 Details: {details}"
    )
    print(log_text)
    # Send log to all current owners
    for owner in BOT_OWNERS: 
        try:
            bot.send_message(owner, log_text)
        except:
            pass

# ---------------- Helper Functions ----------------
def escape_html(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def is_owner(user_id):
    """Bot Owner ကိုသာ စစ်ဆေးသည်"""
    global BOT_OWNERS
    return user_id in BOT_OWNERS

def get_admin_status(user_id, chat_id):
    """
    user_id သည် Owner ဟုတ်မဟုတ်၊
    သို့မဟုတ် Group Admin ဟုတ်မဟုတ် စစ်ဆေးသည်။
    Private Chat များတွင် Owner ကိုသာ Admin အဖြစ် သတ်မှတ်သည်။
    """
    if is_owner(user_id):
        return "owner"

    if chat_id < 0: # Group Chat
        try:
            member = bot.get_chat_member(chat_id, user_id)
            if member.status in ['administrator', 'creator']:
                # Bot သည် group admin ဖြစ်မှသာ group admin ၏ command ကို ခွင့်ပြုမည်
                bot_member = bot.get_chat_member(chat_id, bot.get_me().id)
                if bot_member.status in ['administrator', 'creator']:
                    return "group_admin"
        except Exception:
            pass

    return "user"

def send_auto_messages(chat_id, user_id, user_name, messages_list):
    display_name = target_nicknames.get(user_id, user_name)
    mention = f'<a href="tg://user?id={user_id}">{escape_html(display_name)}</a>'
    while active_users.get((chat_id, user_id), {}).get("active", False):
        if not messages_list:
            time.sleep(5)
            continue

        for msg in messages_list:
            if not active_users.get((chat_id, user_id), {}).get("active", False):
                break
            try:
                full_message = f"{mention} {escape_html(msg)}"
                bot.send_chat_action(chat_id, 'typing')
                bot.send_message(chat_id, full_message, parse_mode="HTML")
                sent_messages.append(full_message)
                time.sleep(message_speed)
            except Exception as e:
                if "Too Many Requests" in str(e):
                    m = re.search(r"retry after (\d+)", str(e))
                    if m:
                        time.sleep(int(m.group(1)) + 1)
                    continue
                break

# ---------------- Advanced Forwarding Job ----------------
def _forward_broadcast_job(chat_id_to_reply, from_chat_id, message_id, groups_set, users_set, log_command_func):

    BASE_DELAY = 0.04 

    # 1. Forward to Groups
    group_sent_count = 0
    group_failed_ids = set()
    with data_lock:
        target_group_ids = list(groups_set)

    for target_id in target_group_ids:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                bot.forward_message(target_id, from_chat_id, message_id)
                group_sent_count += 1
                time.sleep(BASE_DELAY)
                break 
            except telebot.apihelper.ApiTelegramException as e:
                if e.error_code == 429: 
                    retry_after = e.result_json.get('parameters', {}).get('retry_after', 5)
                    print(f"Group 429 Error. Retrying in {retry_after}s.")
                    time.sleep(retry_after + 1) 
                elif e.error_code in [403, 400]: 
                    group_failed_ids.add(target_id)
                    print(f"Group {target_id} failed: {e.error_code}. Removing.")
                    break 
                else: 
                    print(f"Group {target_id} Unknown Error: {e}")
                    time.sleep(2)
            except Exception:
                group_failed_ids.add(target_id)
                break

    # Update global groups set
    if group_failed_ids:
        with data_lock:
            for failed_id in group_failed_ids:
                groups_set.discard(failed_id)
            SAVE_GROUPS_NEEDED.set() 

    # 2. Forward to Users
    user_sent_count = 0
    user_failed_ids = set()
    with data_lock:
        target_user_ids = list(users_set)

    for target_id in target_user_ids:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                bot.forward_message(target_id, from_chat_id, message_id)
                user_sent_count += 1
                time.sleep(BASE_DELAY)
                break 
            except telebot.apihelper.ApiTelegramException as e:
                if e.error_code == 429: 
                    retry_after = e.result_json.get('parameters', {}).get('retry_after', 5)
                    print(f"User 429 Error. Retrying in {retry_after}s.")
                    time.sleep(retry_after + 1) 
                elif e.error_code in [403, 400]: 
                    user_failed_ids.add(target_id)
                    print(f"User {target_id} failed: {e.error_code}. Removing.")
                    break
                else: 
                    print(f"User {target_id} Unknown Error: {e}")
                    time.sleep(2)
            except Exception:
                user_failed_ids.add(target_id)
                break

    # Update global users set
    if user_failed_ids:
        with data_lock:
            for failed_id in user_failed_ids:
                users_set.discard(failed_id)
            SAVE_USERS_NEEDED.set()

    total_sent = group_sent_count + user_sent_count
    total_failed = len(group_failed_ids) + len(user_failed_ids)

    # Final Reply
    try:
        reply_message = (
            f"✅ <b>Broadcast Forward</b> ပြီးစီးပါပြီ။\n\n"
            f"  • ပို့ပြီးသော Groups: {group_sent_count} ခု\n"
            f"  • ပို့ပြီးသော Users: {user_sent_count} ဦး\n"
            f"  • စုစုပေါင်း ပို့ပြီး: {total_sent}\n"
            f"  • ပို့ရန် မအောင်မြင်/ဖယ်ရှားပြီး: {total_failed}"
        )
        log_command_func(f"Forwarded to {total_sent} targets, removed {total_failed}.") 
        bot.send_message(chat_id_to_reply, reply_message, parse_mode="HTML")
    except Exception:
        print(f"Failed to send final broadcast message to {chat_id_to_reply}")

# ---------------- Background Saving Thread ----------------
def background_saver():
    while True:
        if SAVE_GROUPS_NEEDED.is_set():
            with data_lock:
                save_groups()
            SAVE_GROUPS_NEEDED.clear()

        if SAVE_USERS_NEEDED.is_set():
            with data_lock:
                save_users()
            SAVE_USERS_NEEDED.clear()

        time.sleep(5) 

threading.Thread(target=background_saver, daemon=True).start()

# ---------------- Auto group logging ----------------
@bot.message_handler(content_types=['new_chat_members'])
def new_group_log(message):
    for member in message.new_chat_members:
        if member.id == bot.get_me().id:
            chat_id = message.chat.id
            if chat_id not in groups:
                groups.add(chat_id)
                SAVE_GROUPS_NEEDED.set() 
                group_title = message.chat.title or "No Title"
                group_link = f"https://t.me/c/{str(chat_id)[4:]}" if str(chat_id).startswith("-100") else "Private/No link"
                log_text = (
                    f"🆕 Bot added to new group!\n"
                    f"💬 Group Name: {group_title}\n"
                    f"🆔 Group ID: {chat_id}\n"
                    f"🔗 Link: {group_link}\n"
                    f"👥 Type: {message.chat.type}"
                )
                print(log_text)
                # Send log to all current owners
                for owner in BOT_OWNERS: 
                    try:
                        bot.send_message(owner, log_text)
                    except:
                        pass

# ---------------- /start and /help ----------------
def get_help_message(admin_status):
    """မည်သူသုံးသည်ဖြစ်စေ command စာရင်း 
    အပြည့်အစုံကို ပြန်ပေးသည်"""
    general_commands = """
🤖 **General Commands:**
`/start` - Bot ကို စတင်အသုံးပြုခြင်း။
`/help` - ဤအကူအညီစာရင်းကို ပြသခြင်း။
`/myid` - သင့် User ID ကို ပြသခြင်း။
`/id` - Reply လုပ်ထားသော User ၏ ID ကို ပြသခြင်း။
`/aicheck <text1> vs <text2>` - စာသားနှစ်ခုကို ယှဉ်ပြိုင်ကြည့်ခြင်း။
"""

    admin_commands = """
⚔️ **Attack & Control Commands (Group Admin / Owner):**
`/attack <user_ids>` - သတ်မှတ်ထားသော ID များကို Attack စတင်ခြင်း။
`/stop` - လက်ရှိ Chat အတွင်း စတင်ထားသော Attack များကို ရပ်တန့်ခြင်း။
`/setnick <user_id> <nickname>` - Attack target အတွက် နာမည်ပြောင် သတ်မှတ်ခြင်း။

👻 **Ghost & Reply Control (Reply to user):**
`/ghost` - Target ၏ Messages များကို ချက်ချင်းဖျက်ခြင်း (Auto-Delete) စတင်ခြင်း。
`/stopghost` - Auto-Delete ကို ရပ်တန့်ခြင်း。
`/reply` - Target ၏ Messages များကို ချက်ချင်းပြန်ဖြေခြင်း (Auto-Reply) စတင်ခြင်း。
`/stopreply` - Auto-Reply ကို ရပ်တန့်ခြင်း。
`/list` - လက်ရှိ Chat အတွင်း Active ဖြစ်နေသော Ghost/Reply Targets များကို ပြသခြင်း。
"""

    owner_commands = """
👑 **Owner Commands (Bot Owner Only):**
`/squad` - Bot Owner များ၏ စာရင်းကို ကြည့်ခြင်း။
`/gang <user_id or @username>` - User ကို Owner အဖြစ် ထည့်သွင်းခြင်း。
`/ungang <user_id or @username>` - User ကို Owner စာရင်းမှ ဖယ်ရှားခြင်း。
`/broadcast <message>` - Group အားလုံးသို့ စာသားပို့ခြင်း (Slow).
`/broadcastuser <message>` - User အားလုံးသို့ စာသားပို့ခြင်း (Slow).
`/forwardgroup` - Reply Message ကို Group အားလုံးသို့ ပို့ခြင်း (Fast).
`/forwarduser` - Reply Message ကို User အားလုံးသို့ ပို့ခြင်း (Fast).
`/forwardall` - Reply Message ကို Group/User အားလုံးသို့ ပို့ခြင်း (Fast).
`/reloadgroups` - Group list ကို File မှ ပြန် Load ခြင်း。
`/reloadusers` - User list ကို File မှ ပြန် Load ခြင်း。
"""

    reply_management_commands = """
💬 **Reply Management:**
`/addreply <message>` - Reply message အသစ် ထည့်သွင်းခြင်း。
`/addreply` - DM-listen mode စတင်ခြင်း (Private Chat တွင်သာ)。
`/stopaddreply` - DM-listen mode ရပ်တန့်ခြင်း。
`/listreplies` - Reply Messages များအားလုံးကို ကြည့်ခြင်း။
`/removereply <number|text>` - Index သို့မဟုတ် စာသားဖြင့် ဖယ်ရှားခြင်း。
`/reloadreplies` - replies.txt မှ စာသားများကို ပြန်လည် Load ခြင်း。
"""

    # မည်သည့် permission မျှ စစ်ဆေးခြင်းမပြုတော့ဘဲ commands အားလုံးကို ပေါင်းလိုက်ခြင်း
    message = general_commands + admin_commands + owner_commands + reply_management_commands
    return message

@bot.message_handler(commands=['start', 'help'])
def start_and_help_bot(message):
    user_id = message.from_user.id
    admin_status = get_admin_status(user_id, message.chat.id)

    # /start နှိပ်ရင် user ကို list ထဲ ထည့်ခြင်း
    if user_id not in users:
        users.add(user_id)
        SAVE_USERS_NEEDED.set()

    # Welcome Message
    if message.text.startswith('/start'):
        welcome_text = "ဘော့စတင်အသုံးပြုလို့ရပါပြီ။\nအသုံးပြုပုံအသေးစိတ်သိလိုပါက `/help` ကို နှိပ်ပါ။"
        bot.reply_to(message, welcome_text)

    # Help Message
    help_text = get_help_message(admin_status)
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown")

    log_command(message.from_user, message.chat, message.text, "Displayed help/start message")

# ---------------- /aicheck ----------------
@bot.message_handler(commands=['aicheck'])
def ai_debate(message):
    try:
        # /aicheck ပြီးနောက် စာသား ရှိမရှိ စစ်ဆေးခြင်း
        match = re.search(r'/aicheck\s+(.+)', message.text, re.IGNORECASE)
        if not match:
            bot.send_message(message.chat.id, "⚠️ Format: /aicheck text1 vs text2")
            return

        text = match.group(1).strip()

        if " vs " not in text:
            bot.send_message(message.chat.id, "⚠️ Format: /aicheck text1 vs text2")
            return
        part1, part2 = text.split(" vs ", 1)
        score1 = random.randint(40, 60)

        score2 = 100 - score1
        winner, loser = (part1, part2) if score1 > score2 else (part2, part1)
        result = (
            f"{part1} — {score1}%\n"
            f"{part2} — {score2}%\n\n"
            f"🏆 Winner: {winner}\n"
            f"💀 Loser: {loser}"
        )
        bot.send_message(message.chat.id, result)
        log_command(message.from_user, message.chat, "/aicheck", f"{part1} vs {part2}")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Error: {e}")

# ---------------- Attack / Stop ----------------
@bot.message_handler(commands=['attack', 'stop'])
def attack_commands(message):
    from_user = message.from_user.id
    chat_id = message.chat.id
    admin_status = get_admin_status(from_user, chat_id)

    # Permission Check
    if admin_status not in ["owner", "group_admin"]:
        bot.reply_to(message, "မလောက်လေးမလောက်စားတောသားပါမစ်လိုချင်ဖေဖေခေါ်😂")
        log_command(message.from_user, message.chat, message.text, "Unauthorized attack attempt")
        return

    # Group Admin များသည် Private Chat တွင် Attack ကို စတင်/ရပ်တန့်နိုင်ခွင့် မရှိပါ
    if admin_status == "group_admin" and chat_id > 0:
        restriction_message = "Group Admin ခွင့်ပြုချက်သည် Group များတွင်သာ အလုပ်လုပ်ပါသည်။ Private တွင် Bot Owner သာ အသုံးပြုနိုင်ပါသည်။"
        bot.reply_to(message, restriction_message)
        return

    text = message.text.strip()

    if text.startswith("/attack"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            bot.reply_to(message, "Usage: /attack <user_ids comma separated>")
            log_command(message.from_user, message.chat, "/attack", "Invalid usage")
            return
        try:
            user_ids = [int(uid.strip()) for uid in parts[1].split(",")]
        except ValueError:
            bot.reply_to(message, "Invalid ID format")
            log_command(message.from_user, message.chat, "/attack", "Invalid ID format")
            return

        started = []
        skipped = []
        for uid in user_ids:
            if uid in banned_users:
                skipped.append(f"{uid} (banned)")
                continue
            # Bot Owner ကို Attack လုပ်၍မရပါ
            if is_owner(uid) and not is_owner(from_user):
                skipped.append(f"{uid} (is owner)")
                continue

            try:
                user = bot.get_chat(uid)
                user_name = user.first_name or f"User{uid}"
            except:
                user_name = f"User{uid}"

            # Attack စတင်သူ၏ ID ကို owner အဖြစ် မှတ်ထားသည်
            active_users[(chat_id, uid)] = {"active": True, "owner": from_user} 
            threading.Thread(
                target=send_auto_messages,
                args=(chat_id, uid, user_name, auto_messages)
            ).start()

            started.append(str(uid))

        reply = []
        if started:
            reply.append("သခင်လေးအမိန့်တိုင်းခွေးကိုရိုက်ချင်းစတင်ပါပြီ " + ", ".join(started))
        if skipped:
            reply.append("⏭ Skipped: " + ", ".join(skipped))
        bot.reply_to(message, "\n".join(reply) if reply else "Nothing to attack.")
        log_command(message.from_user, message.chat, "/attack", f"Started: {started}, Skipped: {skipped}")

    elif text.startswith("/stop"):
        stopped = 0

        # Group Admin ဖြစ်ရင် chat_id နဲ့ တိုက်ဆိုင်သော Attack အားလုံးကို ရပ်တန့်ခွင့်ပေးမည့်
        keys_to_delete = []
        for key in list(active_users.keys()):
            if key[0] == chat_id:
                active_users[key]["active"] = False
                keys_to_delete.append(key)
                stopped += 1

        for key in keys_to_delete:
            del active_users[key]

        bot.reply_to(message, f"Stopped {stopped} attacks" if stopped else "Nothing to stop.")
        log_command(message.from_user, message.chat, "/stop", f"Stopped {stopped} attacks in chat {chat_id}")

# ---------------- /id /myid ----------------
@bot.message_handler(commands=['myid', 'id'])
def get_id(message):
    if message.text.startswith("/myid"):
        bot.reply_to(message, f"Your ID: {message.from_user.id}")
        log_command(message.from_user, message.chat, "/myid")
    elif message.text.startswith("/id"):
        if message.reply_to_message:
            bot.reply_to(message, f"User ID: {message.reply_to_message.from_user.id}")
            log_command(message.from_user, message.chat, "/id", f"Target: {message.reply_to_message.from_user.id}")
        else:
            bot.reply_to(message, "Reply to a user's message with /id")
            log_command(message.from_user, message.chat, "/id", "No target")

# ---------------- /setnick ----------------
@bot.message_handler(commands=['setnick'])
def set_nick(message):
    admin_status = get_admin_status(message.from_user.id, message.chat.id)
    if admin_status not in ["owner", "group_admin"]:
        return

    # Group Admin များသည် Private Chat တွင် Nickname သတ်မှတ်နိုင်ခွင့် မရှိပါ
    if admin_status == "group_admin" and message.chat.id > 0:
        bot.reply_to(message, "Group Admin ခွင့်ပြုချက်သည် Group များတွင်သာ အလုပ်လုပ်ပါသည်။ Private တွင် Bot Owner သာ အသုံးပြုနိုင်ပါသည်။")
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.reply_to(message, "Usage: /setnick <user_id> <nickname>")
        return
    try:
        user_id = int(parts[1])
        nickname = parts[2]
        target_nicknames[user_id] = nickname
        bot.reply_to(message, f"Nickname set ✅")
        log_command(message.from_user, 
            message.chat, "/setnick", f"Set {nickname} for {user_id}")
    except:
        bot.reply_to(message, "Invalid user ID")

# ---------------- Listener for Auto-Delete & Auto-Reply ----------------
@bot.message_handler(func=lambda message: message.chat.type in ['group', 'supergroup'] and (message.chat.id, message.from_user.id) in active_targets, content_types=['text', 'photo', 'video', 'sticker', 'audio', 'document', 'voice'])
def target_message_handler(message):
    target_id = message.from_user.id
    chat_id = message.chat.id
    target_key = (chat_id, target_id)

    if target_key in active_targets:
        target_data = active_targets[target_key]

        # 1. Auto-Delete (Ghost)
        if target_data.get("ghost"):
            try:
                bot.delete_message(chat_id, message.message_id)
            except Exception as e:
                # Bot Admin မဟုတ်ရင် delete လုပ်မရနိုင်
                print(f"Failed to delete message from {target_id}: {e}")


        # 2. Auto-Reply
        if target_data.get("reply") and auto_messages:
            try:
                reply_message = random.choice(auto_messages)
                mention = f'<a href="tg://user?id={target_id}">{escape_html(message.from_user.first_name or "User")}</a>'
                full_message = f"{mention} {escape_html(reply_message)}"
                bot.send_message(chat_id, full_message, parse_mode="HTML", reply_to_message_id=message.message_id)
            except Exception as e:
                print(f"Failed to auto-reply to {target_id}: {e}")

# ---------------- /ghost ----------------
@bot.message_handler(commands=['ghost'])
def start_ghost(message):
    admin_status = get_admin_status(message.from_user.id, message.chat.id)
    if admin_status not in ["owner", "group_admin"]:
        return

    if not message.reply_to_message:
        bot.reply_to(message, "Usage: /ghost (Reply to user's message)")
        return

    target_id = message.reply_to_message.from_user.id
    target_name = message.reply_to_message.from_user.first_name or "Target"
    chat_id = message.chat.id
    target_key = (chat_id, target_id)

    # Owner ကို Ghost လုပ်၍မရပါ
    if is_owner(target_id) and not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Bot Owner ကို Ghost လုပ်၍မရပါ!")
        return

    active_targets.setdefault(target_key, {}).update({"ghost": True, "ghost_admin": message.from_user.id})
    bot.reply_to(message, f"👻 **{escape_html(target_name)}** ၏ Messages များကို **Instant Auto-Delete** စတင်ပါပြီ။")
    log_command(message.from_user, message.chat, "/ghost", f"Started ghosting {target_id} in {chat_id}")

# ---------------- /stopghost ----------------
@bot.message_handler(commands=['stopghost'])
def stop_ghost(message):
    admin_status = get_admin_status(message.from_user.id, message.chat.id)
    if admin_status not in ["owner", "group_admin"]:
        return

    if not message.reply_to_message:
        bot.reply_to(message, "Usage: /stopghost (Reply to user's message)")
        return

    target_id = message.reply_to_message.from_user.id
    target_name = message.reply_to_message.from_user.first_name or "Target"
    chat_id = message.chat.id
    target_key = (chat_id, target_id)

    if target_key in active_targets:
        if active_targets[target_key].get("ghost"):
            active_targets[target_key]["ghost"] = False
            active_targets[target_key].pop("ghost_admin", None) # Clean up admin ID

            # Check if both ghost and reply are stopped, if so, remove from dict
            if not active_targets[target_key].get("reply"):
                del active_targets[target_key]

            bot.reply_to(message, f"🛑 **{escape_html(target_name)}** ၏ Auto-Delete ကို ရပ်တန့်လိုက်ပါပြီ။")
            log_command(message.from_user, message.chat, "/stopghost", f"Stopped ghosting {target_id} in {chat_id}")
            return

    bot.reply_to(message, f"⚠️ **{escape_html(target_name)}** သည် Ghost Target စာရင်းထဲတွင် မရှိပါ။")

# ---------------- /reply ----------------
@bot.message_handler(commands=['reply'])
def start_reply(message):
    admin_status = get_admin_status(message.from_user.id, message.chat.id)
    if admin_status not in ["owner", "group_admin"]:
        return

    if not message.reply_to_message:
        bot.reply_to(message, "Usage: /reply (Reply to user's message)")
        return

    if not auto_messages:
        bot.reply_to(message, "❌ Auto-Reply စာသားများ မရှိသေးပါ။ /addreply ဖြင့် ထည့်သွင်းပါ။")
        return

    target_id = message.reply_to_message.from_user.id
    target_name = message.reply_to_message.from_user.first_name or "Target"
    chat_id = message.chat.id
    target_key = (chat_id, target_id)

    # Owner ကို Reply လုပ်၍မရပါ
    if is_owner(target_id) and not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Bot Owner ကို Auto-Reply လုပ်၍မရပါ!")
        return

    active_targets.setdefault(target_key, {}).update({"reply": True, "reply_admin": message.from_user.id})
    bot.reply_to(message, f"💬 **{escape_html(target_name)}** ၏ Messages များကို **Instant Auto-Reply** စတင်ပါပြီ။")
    log_command(message.from_user, message.chat, "/reply", f"Started auto-reply to {target_id} in {chat_id}")

# ---------------- /stopreply ----------------
@bot.message_handler(commands=['stopreply'])
def stop_reply(message):
    admin_status = get_admin_status(message.from_user.id, message.chat.id)
    if admin_status not in ["owner", "group_admin"]:
        return

    if not message.reply_to_message:
        bot.reply_to(message, "Usage: /stopreply (Reply to user's message)")
        return

    target_id = message.reply_to_message.from_user.id
    target_name = message.reply_to_message.from_user.first_name or "Target"
    chat_id = message.chat.id
    target_key = (chat_id, target_id)

    if target_key in active_targets:
        if active_targets[target_key].get("reply"):
            active_targets[target_key]["reply"] = False
            active_targets[target_key].pop("reply_admin", None) # Clean up admin ID

            # Check if both ghost and reply are stopped, if so, remove from dict
            if not active_targets[target_key].get("ghost"):
                del active_targets[target_key]

            bot.reply_to(message, f"🛑 **{escape_html(target_name)}** ၏ Auto-Reply ကို ရပ်တန့်လိုက်ပါပြီ။")
            log_command(message.from_user, message.chat, "/stopreply", f"Stopped auto-reply to {target_id} in {chat_id}")
            return

    bot.reply_to(message, f"⚠️ **{escape_html(target_name)}** သည် Reply Target စာရင်းထဲတွင် မရှိပါ။")

# ---------------- /list ----------------
@bot.message_handler(commands=['list'])
def list_targets(message):
    admin_status = get_admin_status(message.from_user.id, message.chat.id)
    if admin_status not in ["owner", "group_admin"]:
        return

    chat_id = message.chat.id
    target_list = []

    # လက်ရွိ Chat အတွက် Targets များကို စစ်ဆေးခြင်း
    for (cid, uid), data in active_targets.items():
        if cid == chat_id:
            try:
                user = bot.get_chat(uid)
                user_name = user.first_name or f"User{uid}"
            except:
                user_name = f"User{uid} (Not Found)"

            status = []
            if data.get("ghost"):
                status.append(f"👻 Ghost (by <code>{data.get('ghost_admin', 'N/A')}</code>)")
            if data.get("reply"):
                status.append(f"💬 Auto-Reply (by <code>{data.get('reply_admin', 'N/A')}</code>)")

            target_list.append(f"• <code>{uid}</code> ({escape_html(user_name)}): {', '.join(status)}")

    if target_list:
        reply_msg = f"🎯 **Active Targets in this Chat ({chat_id}):**\n\n" + "\n".join(target_list)
    else:
        reply_msg = "✅ လက်ရှိ Chat တွင် Active Target မရှိပါ။"

    bot.send_message(message.chat.id, reply_msg, parse_mode="HTML")
    log_command(message.from_user, message.chat, "/list", f"Displayed list of {len(target_list)} targets in {chat_id}")

# ---------------- Owner Management ----------------
@bot.message_handler(commands=['gang', 'ungang'])
def manage_owners(message):
    global BOT_OWNERS
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Bot Owner များသာ အသုံးပြုနိုင်ပါသည်။")
        return

    command = message.text.split(maxsplit=1)[0].lower()

    target_id = None

    # 1. Check reply
    if message.reply_to_message:
        target_id = message.reply_to_message.from_user.id
    # 2. Check text argument
    elif len(message.text.split()) > 1:
        arg = message.text.split(maxsplit=2)[1].strip()
        try:
            # Try to parse as numeric ID
            target_id = int(arg)
        except ValueError:
            # Try to resolve @username
            if arg.startswith('@'):
                username = arg.lstrip('@')
                try:
                    # Attempt to get ID from username (only works if user is known by the bot)
                    chat_member = bot.get_chat_member(message.chat.id, arg)
                    target_id = chat_member.user.id
                except Exception:
                    bot.reply_to(message, f"❌ Username **@{username}** ၏ ID ကို ရှာမတွေ့ပါ။ User ID ဖြင့်သာ ထည့်သွင်း/ဖယ်ရှားပါ။")
                    return
            else:
                 bot.reply_to(message, "Usage: /gang <user_id or @username> သို့မဟုတ် Reply လုပ်ပါ။")
                 return
        except Exception:
             bot.reply_to(message, "Usage: /gang <user_id or @username> သို့မဟုတ် Reply လုပ်ပါ။")
             return

    if target_id is None:
        bot.reply_to(message, "Usage: /gang <user_id or @username> သို့မဟုတ် Reply လုပ်ပါ။")
        return

    if target_id == bot.get_me().id:
        bot.reply_to(message, "❌ Bot ကို Owner အဖြစ် ထည့်/ဖယ် လုပ်၍မရပါ။")
        return

    try:
        user_info = bot.get_chat(target_id)
        name = escape_html(user_info.first_name)
    except:
        name = f"User{target_id}"


    if command == '/gang':
        if target_id in BOT_OWNERS:
            bot.reply_to(message, f"⚠️ **{name}** (<code>{target_id}</code>) သည် Owner စာရင်းတွင် ရှိပြီးဖြစ်သည်။")
        else:
            BOT_OWNERS.add(target_id)
            save_owners()
            bot.reply_to(message, f"✅ **{name}** (<code>{target_id}</code>) ကို Owner အဖြစ် ထည့်သွင်းပြီးပါပြီ။")
            log_command(message.from_user, message.chat, "/gang", f"Added owner ID: {target_id}")

    elif command == '/ungang':
        if target_id == message.from_user.id:
            bot.reply_to(message, "❌ သင့်ကိုယ်သင် Owner စာရင်းမှ ဖယ်ထုတ်၍မရပါ。")
            return

        if len(BOT_OWNERS) <= 1:
             bot.reply_to(message, "❌ Owner တစ်ဦးသာ ကျန်ရှိသဖြင့် ထပ်မံဖယ်ထုတ်၍မရပါ။")
             return

        if target_id not in BOT_OWNERS:
            bot.reply_to(message, f"⚠️ **{name}** (<code>{target_id}</code>) သည် Owner စာရင်းတွင် မရှိပါ။")
        else:
            BOT_OWNERS.remove(target_id)
            save_owners()
            bot.reply_to(message, f"🗑️ **{name}** (<code>{target_id}</code>) ကို Owner စာရင်းမှ ဖယ်ရှားပြီးပါပြီ။")
            log_command(message.from_user, message.chat, "/ungang", f"Removed owner ID: {target_id}")

@bot.message_handler(commands=['squad'])
def list_squad(message):
    if not is_owner(message.from_user.id):
        # Only log owner access, not failed attempts
        return

    owner_list = []
    global BOT_OWNERS
    for uid in BOT_OWNERS:
        try:
            user = bot.get_chat(uid)
            name = user.username if user.username else f"{user.first_name or ''} {user.last_name or ''}".strip()
            owner_list.append(f"- <code>{uid}</code> ({escape_html(name)})")
        except:
            owner_list.append(f"- <code>{uid}</code> (username not found)")

    bot.reply_to(message, "👑 Current Bot Owners Squad:\n" + "\n".join(owner_list), parse_mode="HTML")
    log_command(message.from_user, message.chat, "/squad", f"Listed {len(BOT_OWNERS)} owners")

# ---------------- Broadcast ----------------
@bot.message_handler(commands=['broadcast'])
def broadcast(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Only the owner can use /broadcast")
        return

    try:
        msg_text = message.text.split(maxsplit=1)[1]
    except:
        bot.reply_to(message, "Usage: /broadcast <message>")
        return

    # OLD Broadcast (slow)
    sent_count = 0
    for chat_id in groups.copy():
        try:
            bot.send_message(chat_id, msg_text)
            sent_count += 1
            time.sleep(0.1)
        except:
            groups.remove(chat_id)
            SAVE_GROUPS_NEEDED.set()

    bot.reply_to(message, f"✅ Broadcast sent to {sent_count} groups (Slow Method)")
    log_command(message.from_user, message.chat, "/broadcast", f"Sent to {sent_count} groups (Slow Method)")

@bot.message_handler(commands=['broadcastuser'])
def broadcast_user(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Only the owner can use /broadcastuser")
        return

    try:
        msg_text = message.text.split(maxsplit=1)[1]
    except:
        bot.reply_to(message, "Usage: /broadcastuser <message>")
        return

    # OLD Broadcast User (slow)
    sent_count = 0
    for user_id in users.copy():
        try:
            bot.send_message(user_id, msg_text)
            sent_count += 1
            time.sleep(0.1)
        except:
            users.remove(user_id)
            SAVE_USERS_NEEDED.set()

    bot.reply_to(message, f"✅ Broadcast sent to {sent_count} users (Slow Method)")
    log_command(message.from_user, message.chat, "/broadcastuser", f"Sent to {sent_count} users (Slow Method)")

# ---------------- New Forward Commands (Fast) ----------------
@bot.message_handler(commands=['forwardgroup'])
def forward_to_groups(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Only the owner can use /forwardgroup")
        return

    if not message.reply_to_message:
        bot.reply_to(message, "Usage: Reply to a message with /forwardgroup")
        return

    bot.reply_to(message, "⏳ Forwarding process စတင်ပါပြီ။ ပြီးဆုံးပါက အကြောင်းကြားပါမည်။ (Group များသို့)")

    # New Fast Forwarding Job (Only Groups)
    threading.Thread(
        target=_forward_broadcast_job,
        args=(message.chat.id, message.reply_to_message.chat.id, message.reply_to_message.message_id, groups, set(), lambda d: log_command(message.from_user, message.chat, "/forwardgroup", d))
    ).start()
    log_command(message.from_user, message.chat, "/forwardgroup", f"Started forwarding message ID: {message.reply_to_message.message_id} to {len(groups)} groups")

@bot.message_handler(commands=['forwarduser'])
def forward_to_users(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Only the owner can use /forwarduser")
        return

    if not message.reply_to_message:
        bot.reply_to(message, "Usage: Reply to a message with /forwarduser")
        return

    bot.reply_to(message, "⏳ Forwarding process စတင်ပါပြီ။ ပြီးဆုံးပါက အကြောင်းကြားပါမည်။ (User များသို့)")

    # New Fast Forwarding Job (Only Users)
    threading.Thread(
        target=_forward_broadcast_job,
        args=(message.chat.id, message.reply_to_message.chat.id, message.reply_to_message.message_id, set(), users, lambda d: log_command(message.from_user, message.chat, "/forwarduser", d))
    ).start()
    log_command(message.from_user, message.chat, "/forwarduser", f"Started forwarding message ID: {message.reply_to_message.message_id} to {len(users)} users")

@bot.message_handler(commands=['forwardall'])
def forward_to_all(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Only the owner can use /forwardall")
        return

    if not message.reply_to_message:
        bot.reply_to(message, "Usage: Reply to a message with /forwardall")
        return

    bot.reply_to(message, "⏳ Forwarding process စတင်ပါပြီ။ ပြီးဆုံးပါက အကြောင်းကြားပါမည်။ (Groups နှင့် Users များသို့)")

    # New Fast Forwarding Job (Groups & Users)
    threading.Thread(
        target=_forward_broadcast_job,
        args=(message.chat.id, message.reply_to_message.chat.id, message.reply_to_message.message_id, groups, users, lambda d: log_command(message.from_user, message.chat, "/forwardall", d))
    ).start()
    log_command(message.from_user, message.chat, "/forwardall", f"Started forwarding message ID: {message.reply_to_message.message_id} to {len(groups) + len(users)} total targets")

# ---------------- /reloadgroups /reloadusers ----------------
@bot.message_handler(commands=['reloadgroups'])
def reload_groups(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Bot Owner သာ အသုံးပြုနိုင်ပါသည်။")
        return

    global groups
    groups = load_groups()
    bot.reply_to(message, f"✅ Groups list ကို File မှ ပြန် Load ပြီးပါပြီ။ (Total: {len(groups)})")
    log_command(message.from_user, message.chat, "/reloadgroups", f"Reloaded {len(groups)} groups")

@bot.message_handler(commands=['reloadusers'])
def reload_users(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Bot Owner သာ အသုံးပြုနိုင်ပါသည်။")
        return

    global users
    users = load_users()
    bot.reply_to(message, f"✅ Users list ကို File မှ ပြန် Load ပြီးပါပြီ။ (Total: {len(users)})")
    log_command(message.from_user, message.chat, "/reloadusers", f"Reloaded {len(users)} users")

# ---------------- Reply Management ----------------
@bot.message_handler(commands=['addreply', 'stopaddreply'])
def handle_add_reply_mode(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Bot Owner သာ အသုံးပြုနိုင်ပါသည်။")
        return

    user_id = message.from_user.id
    text = message.text.strip()

    if text.startswith("/stopaddreply"):
        if user_id in dm_listen_mode:
            dm_listen_mode.remove(user_id)
            bot.reply_to(message, "🛑 DM-Listen Mode ကို ရပ်တန့်လိုက်ပါပြီ။")
            log_command(message.from_user, message.chat, "/stopaddreply", "Stopped DM-listen mode")
        else:
            bot.reply_to(message, "⚠️ DM-Listen Mode စတင်ထားခြင်းမရှိပါ။")
        return

    if message.chat.type != 'private':
        bot.reply_to(message, "❌ `DM-Listen Mode` ကို Private Chat တွင်သာ အသုံးပြုနိုင်ပါသည်။")
        return

    parts = text.split(maxsplit=1)

    if len(parts) == 2:
        # /addreply <message>
        new_msg = parts[1]
        global auto_messages
        if new_msg in auto_messages:
            bot.reply_to(message, "⚠️ ဤစာသားသည် စာရင်းတွင် ရှိနှင့်ပြီးသားဖြစ်သည်။")
            return

        auto_messages.append(new_msg)
        if save_auto_messages(auto_messages):
            bot.reply_to(message, f"✅ Reply message အသစ် ထည့်သွင်းပြီးပါပြီ။ (Total: {len(auto_messages)})")
            log_command(message.from_user, message.chat, "/addreply", f"Added reply: {new_msg[:50]}...")
        else:
            bot.reply_to(message, "❌ Message save လုပ်ရာတွင် Error ဖြစ်ပွားခဲ့သည်။")

    elif len(parts) == 1:
        # /addreply (no arguments) -> Enable DM-listen mode
        if user_id not in dm_listen_mode:
            dm_listen_mode.add(user_id)
            bot.reply_to(message, "💬 **DM-Listen Mode** စတင်ပါပြီ။\n\nသင့္ပို့သော စာသားတိုင်းကို Auto-Reply စာရင်းထဲသို့ ထည့်သွင်းပါမည်။\n\nရပ်တန့်ရန်: `/stopaddreply`")
            log_command(message.from_user, message.chat, "/addreply", "Started DM-listen mode")
        else:
            bot.reply_to(message, "⚠️ DM-Listen Mode သည် စတင်ထားပြီးဖြစ်သည်။ ရပ်တန့်ရန်: `/stopaddreply`")

@bot.message_handler(func=lambda message: message.chat.type == 'private' and message.from_user.id in dm_listen_mode, content_types=['text'])
def dm_listener(message):
    user_id = message.from_user.id
    new_msg = message.text.strip()

    if new_msg and not new_msg.startswith("/"):
        global auto_messages
        if new_msg in auto_messages:
            bot.reply_to(message, "⚠️ ဤစာသားသည် စာရင်းတွင် ရှိနှင့်ပြီးသားဖြစ်သည်။")
            return

        auto_messages.append(new_msg)
        if save_auto_messages(auto_messages):
            bot.reply_to(message, f"✅ Reply message အသစ် ထည့်သွင်းပြီးပါပြီ။ (Total: {len(auto_messages)})")
            # Log is handled by /addreply, so skipping here

# ---------------- /listreplies ----------------
@bot.message_handler(commands=['listreplies'])
def list_replies(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Bot Owner သာ အသုံးပြုနိုင်ပါသည်။")
        return

    if not auto_messages:
        bot.reply_to(message, "❌ Reply message များ မရှိသေးပါ။")
        return

    reply_list = []
    for i, msg in enumerate(auto_messages):
        reply_list.append(f"{i+1}. {escape_html(msg)}")

    # Send in chunks if too long
    full_text = "💬 **Current Auto-Reply Messages:**\n\n" + "\n".join(reply_list)
    if len(full_text) > 4096:
        for i in range(0, len(reply_list), 50): # 50 messages per chunk
            chunk = "💬 **Auto-Reply Messages (Cont.):**\n\n" + "\n".join(reply_list[i:i+50])
            bot.send_message(message.chat.id, chunk, parse_mode="HTML")
    else:
        bot.send_message(message.chat.id, full_text, parse_mode="HTML")

    log_command(message.from_user, message.chat, "/listreplies", f"Displayed {len(auto_messages)} replies")

# ---------------- /removereply ----------------
@bot.message_handler(commands=['removereply'])
def remove_reply(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Bot Owner သာ အသုံးပြုနိုင်ပါသည်။")
        return

    try:
        query = message.text.split(maxsplit=1)[1].strip()
    except IndexError:
        bot.reply_to(message, "Usage: /removereply <index_number | exact_text>")
        return

    if not auto_messages:
        bot.reply_to(message, "❌ Reply message များ မရှိသေးပါ။")
        return

    removed_msg = None

    # 1. Index ဖြင့် ဖယ်ရှားခြင်း
    if query.isdigit():
        index = int(query) - 1
        if 0 <= index < len(auto_messages):
            removed_msg = auto_messages.pop(index)
        else:
            bot.reply_to(message, f"❌ Index နံပါတ် {query} သည် မရှိပါ။ (Total: {len(auto_messages)})")
            return
    # 2. Text ဖြင့် ဖယ်ရှားခြင်း
    else:
        try:
            # တိကျတဲ့ စာသားကို ရှာဖွေပြီး ဖယ်ရှားခြင်း
            index = auto_messages.index(query)
            removed_msg = auto_messages.pop(index)
        except ValueError:
            bot.reply_to(message, f"❌ တိကျသော စာသားကို ရှာမတွေ့ပါ။ စာလုံးပေါင်း သေချာစစ်ပါ။")
            return

    if removed_msg:
        save_auto_messages(auto_messages)
        bot.reply_to(message, f"🗑️ Reply message ကို ဖယ်ရှားပြီးပါပြီ။ (Total: {len(auto_messages)}) \n\nဖယ်ရှားခံရသည့်စာသား: `{escape_html(removed_msg[:50])}...`", parse_mode="HTML")
        log_command(message.from_user, message.chat, "/removereply", f"Removed reply: {removed_msg[:50]}...")

# /reloadreplies command
@bot.message_handler(commands=['reloadreplies'])
def reload_replies(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Bot Owner သာ အသုံးပြုနိုင်ပါသည်။")
        return

    global auto_messages
    new_messages = load_auto_messages()
    old_count = len(auto_messages)
    auto_messages = new_messages
    new_count = len(auto_messages)

    bot.reply_to(message, f"✅ `replies.txt` မှ Message များကို ပြန်လည် Load ပြီးပါပြီ။ (Old: {old_count}, New: {new_count})")
    log_command(message.from_user, message.chat, "/reloadreplies", f"Reloaded {new_count} replies")

# ---------------- Fallback Handler for Unknown Commands ----------------
@bot.message_handler(func=lambda message: True, content_types=['text'])
def unknown_command(message):
    if message.text.startswith("/"):
        # This acts as a final log for any command that wasn't handled
        log_command(message.from_user, message.chat, message.text, "Unknown command")

# ---------------- Bot Polling Start ----------------
print("Bot Polling started...")
bot.infinity_polling()
