import telebot
import requests
import re
import sqlite3
import time
from telebot import types
from Crypto.Cipher import AES
from typing import Optional, Tuple


# ===== CONFIGURATION =====
BOT_TOKEN = "8629038583:AAHMT81m1bzOCkTw7g2Fnwlin717TN9ic1U"
OWNER_ID = 7778746139
OWNER_USERNAME = "aizen"
OWNER_LINK = "https://t.me/aizesuigetsu"
CHANNEL_LINK = "https://whatsapp.com/channel/0029Vb7eSHf42Dcmdd3XA326"
VAMPIRE_CHANNEL = "https://t.me/darkweb"
BOT_USERNAME = "Deepseek_ai_new_bot"

POINTS_TO_UNLOCK = 5
DB_PATH = "bot.db"

bot = telebot.TeleBot(BOT_TOKEN)
ai_session: Optional[requests.Session] = None


# ===== ALL 18 DEEPSEEK MODELS =====
MODELS = [
    "DeepSeek-V1", "DeepSeek-V2", "DeepSeek-V2.5", "DeepSeek-V3",
    "DeepSeek-V3-0324", "DeepSeek-V3.1", "DeepSeek-V3.2", "DeepSeek-R1",
    "DeepSeek-R1-0528", "DeepSeek-R1-Distill", "DeepSeek-Prover-V1",
    "DeepSeek-Prover-V1.5", "DeepSeek-Prover-V2", "DeepSeek-VL",
    "DeepSeek-Coder", "DeepSeek-Coder-V2", "DeepSeek-Coder-6.7B-base",
    "DeepSeek-Coder-6.7B-instruct",
]


# ===== HELPERS =====
def progress_bar(points: int, max_pts: int = POINTS_TO_UNLOCK) -> str:
    """Return a filled/empty block bar like ▓▓▓░░."""
    filled = min(points, max_pts)
    return "▓" * filled + "░" * (max_pts - filled)


def referral_link(uid: int) -> str:
    """Build a Telegram deep-link referral URL for the given user."""
    return f"https://t.me/{BOT_USERNAME}?start={uid}"


def truncate(text: str, length: int = 25) -> str:
    """Shorten *text* with an ellipsis if it exceeds *length*."""
    return text[:length] + "..." if len(text) > length else text


# ===== AI ENGINE =====
def init_ai() -> None:
    """
    Establish a session with the DeepSeek proxy (asmodeus.free.nf).

    The proxy uses an AES-CBC challenge cookie.  If the handshake
    succeeds, the session is stored in the global ``ai_session``.
    """
    global ai_session
    try:
        session = requests.Session()
        session.headers["User-Agent"] = (
            "Mozilla/5.0 (Linux; Android 12; SM-G998B) AppleWebKit/537.36"
        )

        page = session.get("https://asmodeus.free.nf/", timeout=20)
        hex_values = re.findall(r'toNumbers\("([a-f0-9]+)"\)', page.text)

        if len(hex_values) >= 3:
            key, iv, data = [bytes.fromhex(h) for h in hex_values[:3]]
            cipher = AES.new(key, AES.MODE_CBC, iv)
            cookie_value = cipher.decrypt(data).hex()
            session.cookies.set(
                "__test", cookie_value, domain="asmodeus.free.nf"
            )
            session.get("https://asmodeus.free.nf/index.php?i=1", timeout=15)
            ai_session = session
            print("✅ AI Connected")
    except Exception as exc:
        print(f"AI Error: {exc}")


def ask_ai(model_idx: int, question: str) -> str:
    """
    Send *question* to the proxy using the model at *model_idx*.

    Returns the plain-text answer (max 3 800 chars) or an error string.
    """
    global ai_session

    if not ai_session:
        init_ai()
        if not ai_session:
            return "🔄 AI loading, please retry..."

    model = MODELS[model_idx] if 0 <= model_idx < len(MODELS) else MODELS[0]

    try:
        resp = ai_session.post(
            "https://asmodeus.free.nf/deepseek.php",
            params={"i": "1"},
            data={"model": model, "question": question},
            timeout=30,
        )
        match = re.search(
            r'<div class="response-content">(.*?)</div>',
            resp.text,
            re.DOTALL,
        )
        if match:
            clean = re.sub(r"<[^>]+>", "", match.group(1).strip())
            return clean[:3800]
        return "🤖 No response from AI"
    except Exception:
        ai_session = None
        return "⚠️ Error!, please try again!"


# ===== DATABASE =====
def db_init() -> None:
    """Create the ``u`` table if it doesn't exist yet."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS u ("
            "  id    INTEGER PRIMARY KEY,"
            "  pts   INTEGER DEFAULT 0,"
            "  prem  INTEGER DEFAULT 0,"
            "  model INTEGER DEFAULT 0"
            ")"
        )
        conn.commit()


def db_get(uid: int) -> Tuple[int, int, int]:
    """
    Return ``(points, premium, model_index)`` for *uid*.

    Inserts a default row when the user is seen for the first time.
    """
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT pts, prem, model FROM u WHERE id = ?", (uid,))
        row = cursor.fetchone()
        if not row:
            cursor.execute(
                "INSERT INTO u (id, pts, prem, model) VALUES (?, 0, 0, 0)",
                (uid,),
            )
            conn.commit()
            return (0, 0, 0)
        return row


def db_set(
    uid: int,
    pts: Optional[int] = None,
    prem: Optional[int] = None,
    model: Optional[int] = None,
) -> None:
    """Update one or more fields for *uid*."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        if pts is not None:
            cursor.execute("UPDATE u SET pts = ? WHERE id = ?", (pts, uid))
        if prem is not None:
            cursor.execute("UPDATE u SET prem = ? WHERE id = ?", (prem, uid))
        if model is not None:
            cursor.execute("UPDATE u SET model = ? WHERE id = ?", (model, uid))
        conn.commit()


def can_use(uid: int) -> bool:
    """Check whether *uid* has enough points or premium access."""
    if uid == OWNER_ID:
        return True
    pts, prem, _ = db_get(uid)
    return pts >= POINTS_TO_UNLOCK or prem == 1


# ===== OWNER DM LINK =====
owner_dm = f"https://t.me/{OWNER_ID}"


# ===== START — BEAUTIFUL WELCOME =====
@bot.message_handler(commands=["start", "menu"])
def start(msg: types.Message) -> None:
    """Display the main welcome screen with inline buttons."""
    uid = msg.from_user.id
    pts, prem, mdl = db_get(uid)

    # — Referral tracker —
    parts = msg.text.split()
    if len(parts) > 1:
        try:
            referrer = int(parts[1])
            if referrer != uid:
                ref_pts, _, _ = db_get(referrer)
                db_set(referrer, pts=ref_pts + 1)
                bot.reply_to(
                    msg,
                    f"🎉 **Referral Success!**\n"
                    f"✅ Your friend got **+1 point** (Total: {ref_pts + 1}/5)",
                    parse_mode="Markdown",
                )
        except (ValueError, IndexError):
            pass

    # — Build status line —
    if uid == OWNER_ID:
        status_line = "┃ 👤 👑 **VIP OWNER**"
    elif prem:
        status_line = "┃ 👤 💎 **PREMIUM USER**"
    else:
        bar = progress_bar(pts)
        status_line = f"┃ 👤 ⭐ **{pts}/5 Points** {bar}"

    model_name = truncate(MODELS[mdl])

    welcome = f"""
╔══════════════════════════╗
║ ✨ WELCOME TO THE SYSTEM! ✨ ║
║  🤖 DeepSeek AI Bot     ║
╚══════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━
{status_line}
┃ 🤖 Model: `{model_name}`
┃ 📡 Status: {'✅ UNLOCKED' if can_use(uid) else '🔒 LOCKED'}
━━━━━━━━━━━━━━━━━━━━━

I can answer questions using **18 different DeepSeek models**! 
⚡ Type In A Command To Start.

📌 **How to use:**
1️⃣ Select a model from buttons below
2️⃣ Start chatting – I'll reply instantly
3️⃣ Use `/model` to change anytime
4️⃣ Use `/stop` to end conversation

🔔 **Join:** @darkweb info
"""

    bar = progress_bar(pts)
    markup = types.InlineKeyboardMarkup(row_width=1)

    # Channel links
    markup.add(
        types.InlineKeyboardButton("📢 JOIN CHANNELS 🔔", url=VAMPIRE_CHANNEL),
        types.InlineKeyboardButton("📢 WHATSAPP CHANNEL 👑", url=CHANNEL_LINK),
    )

    # Referral button
    markup.add(
        types.InlineKeyboardButton(
            f"👥 REFERRALS {bar} {pts}/5", callback_data="refer"
        )
    )

    # Access button
    if can_use(uid):
        markup.add(
            types.InlineKeyboardButton(
                "🤖 AI CHAT — UNLOCKED ✅", callback_data="ai"
            )
        )
    else:
        markup.add(
            types.InlineKeyboardButton(
                "🔒 UNLOCK ACCESS (5 POINTS)", callback_data="unlock"
            )
        )

    markup.add(
        types.InlineKeyboardButton("🔧 SELECT MODEL", callback_data="models"),
        types.InlineKeyboardButton("📊 MY STATS", callback_data="stats"),
        types.InlineKeyboardButton("👤 CONTACT OWNER", url=owner_dm),
        types.InlineKeyboardButton("📢 CHANNELS", url=VAMPIRE_CHANNEL),
    )

    bot.send_message(msg.chat.id, welcome, reply_markup=markup, parse_mode="Markdown")


# ===== MODEL SELECTION MENU =====
@bot.message_handler(commands=["model"])
def model_cmd(msg: types.Message) -> None:
    """Open the model selection menu (requires access)."""
    if not can_use(msg.from_user.id):
        bot.reply_to(
            msg, "🔒 Need 5 points or premium!\n/start", parse_mode="Markdown"
        )
        return
    show_models(msg.chat.id)


def show_models(chat_id: int, edit_msg_id: Optional[int] = None) -> None:
    """Render the model picker as inline buttons (send or edit)."""
    text = """
╔══════════════════════════╗
║ 🤖 SELECT YOUR MODEL 🤖 ║
╚══════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━
Choose a DeepSeek model:
━━━━━━━━━━━━━━━━━━━━━━━
"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    for idx, model in enumerate(MODELS):
        label = f"{idx + 1}. {truncate(model, 20)}"
        markup.add(
            types.InlineKeyboardButton(label, callback_data=f"mdl_{idx}")
        )

    markup.add(types.InlineKeyboardButton("🔙 MAIN MENU", callback_data="menu"))

    if edit_msg_id:
        bot.edit_message_text(
            text, chat_id, edit_msg_id, reply_markup=markup, parse_mode="Markdown"
        )
    else:
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")


# ===== CALLBACKS =====
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call: types.CallbackQuery) -> None:
    """Central dispatcher for all inline-button callbacks."""
    uid = call.from_user.id
    pts, prem, mdl = db_get(uid)
    msg_id = call.message.message_id
    chat_id = call.message.chat.id

    # — Referral screen —
    if call.data == "refer":
        link = referral_link(uid)
        bar = progress_bar(pts)
        text = f"""
╔══════════════════════════╗
║    👥 REFERRAL SYSTEM    ║
╚══════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━
📎 **Your Referral Link:**
`{link}`

━━━━━━━━━━━━━━━━━━━━━━━
👤 1 Friend Invited = ⭐ 1 Point
━━━━━━━━━━━━━━━━━━━━━━━

⭐ **Progress:** `{pts}/5` {bar}
💎 **Premium:** `{'✅ YES' if prem else '❌ NO'}`

Share link with friends to earn points!
"""
        bot.edit_message_text(
            text,
            chat_id,
            msg_id,
            parse_mode="Markdown",
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("🔙 MAIN MENU", callback_data="menu")
            ),
        )

    # — AI Chat —
    elif call.data == "ai":
        if can_use(uid):
            model_name = MODELS[mdl]
            text = f"""
╔══════════════════════════╗
║  🤖 **AI READY** ✅      ║
╚══════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━
**Active Model:** `{model_name}`

✅ Send any message to start chatting!
━━━━━━━━━━━━━━━━━━━━━━━
🔹 /menu — Main Menu
🔹 /model — Change Model
🔹 /stop — End Chat
🔹 /points — Your Stats
━━━━━━━━━━━━━━━━━━━━━━━
"""
            bot.edit_message_text(
                text,
                chat_id,
                msg_id,
                parse_mode="Markdown",
                reply_markup=types.InlineKeyboardMarkup(row_width=1).add(
                    types.InlineKeyboardButton(
                        "🔧 CHANGE MODEL", callback_data="models"
                    ),
                    types.InlineKeyboardButton(
                        "🔙 MAIN MENU", callback_data="menu"
                    ),
                ),
            )
        else:
            bot.answer_callback_query(call.id, "❌ NEED 5 POINTS OR PREMIUM!")

    # — Unlock —
    elif call.data == "unlock":
        bar = progress_bar(pts)
        text = f"""
╔══════════════════════════╗
║  🔓 **UNLOCK ACCESS**    ║
╚══════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━
🎯 **OPTION 1 — FREE**
   ⭐ Invite **5 friends**
   👥 1 friend = ⭐ 1 point
   {bar} `{pts}/5`
━━━━━━━━━━━━━━━━━━━━━━━
💎 **OPTION 2 — PREMIUM**
   📩 DM the owner directly
   💬 Say: "Add me premium pls"
━━━━━━━━━━━━━━━━━━━━━━━
"""
        bot.edit_message_text(
            text,
            chat_id,
            msg_id,
            parse_mode="Markdown",
            reply_markup=types.InlineKeyboardMarkup(row_width=1).add(
                types.InlineKeyboardButton(
                    "💎 DM OWNER (@aizesuigetsu)", url=owner_dm
                ),
                types.InlineKeyboardButton("👤 OWNER PROFILE", url=OWNER_LINK),
                types.InlineKeyboardButton("🔙 MAIN MENU", callback_data="menu"),
            ),
        )

    # — Model picker —
    elif call.data == "models":
        show_models(chat_id, msg_id)

    # — Model selected —
    elif call.data.startswith("mdl_"):
        idx = int(call.data.split("_")[1])
        db_set(uid, model=idx)
        model_name = MODELS[idx]
        text = f"""
╔══════════════════════════╗
║ ✅ **MODEL SELECTED** ✅ ║
╚══════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━
🤖 **{model_name}** is now active!

💬 Send any message to chat!
━━━━━━━━━━━━━━━━━━━━━━━
"""
        bot.edit_message_text(
            text,
            chat_id,
            msg_id,
            parse_mode="Markdown",
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("🔧 CHANGE", callback_data="models"),
                types.InlineKeyboardButton("🔙 MAIN MENU", callback_data="menu"),
            ),
        )
        bot.answer_callback_query(call.id, f"✅ {model_name} activated!")

    # — Stats —
    elif call.data == "stats":
        link = referral_link(uid)
        bar = progress_bar(pts)
        model_name = MODELS[mdl]
        text = f"""
╔══════════════════════════╗
║  📊 **YOUR STATS**       ║
╚══════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━
⭐ **Points:** `{pts}/5` {bar}
💎 **Premium:** `{'✅ YES' if prem else '❌ NO'}`
👑 **Owner:** `{'✅ YES' if uid == OWNER_ID else '❌ NO'}`
🤖 **Model:** `{model_name}`
━━━━━━━━━━━━━━━━━━━━━━━

📎 **Referral Link:**
`{link}`
"""
        bot.edit_message_text(
            text,
            chat_id,
            msg_id,
            parse_mode="Markdown",
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("🔙 MAIN MENU", callback_data="menu")
            ),
        )

    # — Back to main menu —
    elif call.data == "menu":
        proxy_msg = call.message
        proxy_msg.text = "/start"
        start(proxy_msg)


# ===== AI CHAT =====
@bot.message_handler(func=lambda msg: True)
def ai_chat(msg: types.Message) -> None:
    """Forward any non-command message to the selected DeepSeek model."""
    uid = msg.from_user.id
    if not can_use(uid):
        bot.reply_to(
            msg,
            "🔒 **ACCESS DENIED**\nNeed 5 points or premium!\n/start",
            parse_mode="Markdown",
        )
        return

    _, _, mdl = db_get(uid)
    model_name = MODELS[mdl]

    thinking = bot.reply_to(
        msg, f"🧠 **{model_name} is thinking...**", parse_mode="Markdown"
    )
    response = ask_ai(mdl, msg.text)

    try:
        bot.delete_message(thinking.chat.id, thinking.message_id)
    except Exception:
        pass

    reply = f"""
╔══════════════════════════╗
║  🤖 **{model_name}**     ║
╚══════════════════════════╝

{response}

━━━━━━━━━━━━━━━━━━━━━━━
💡 *Powered by VAMPIRE DeepSeek API*
"""
    bot.reply_to(msg, reply, parse_mode="Markdown", disable_web_page_preview=True)


# ===== POINTS =====
@bot.message_handler(commands=["points"])
def points_cmd(msg: types.Message) -> None:
    """Quick overview of the caller's points and referral link."""
    uid = msg.from_user.id
    pts, prem, _ = db_get(uid)
    link = referral_link(uid)
    bar = progress_bar(pts)
    bot.reply_to(
        msg,
        f"⭐ **{pts}/5 Points** {bar}\n"
        f"💎 Premium: {'✅' if prem else '❌'}\n\n"
        f"📎 `{link}`",
        parse_mode="Markdown",
    )


# ===== STOP =====
@bot.message_handler(commands=["stop"])
def stop_cmd(msg: types.Message) -> None:
    """End the current chat session with a farewell card."""
    text = """
╔══════════════════════════╗
║  👋 **SESSION ENDED**    ║
╚══════════════════════════╝

💬 Use /start to begin again
🔔 Join @darkweb
"""
    bot.reply_to(msg, text, parse_mode="Markdown")


# ===== OWNER PREMIUM COMMAND =====
@bot.message_handler(commands=["premium"])
def premium_cmd(msg: types.Message) -> None:
    """Grant premium status to a user (owner only)."""
    if msg.from_user.id != OWNER_ID:
        bot.reply_to(
            msg, "❌ **OWNER ONLY COMMAND**\n👤 @aizesuigetsu", parse_mode="Markdown"
        )
        return

    try:
        target_uid = int(msg.text.split()[1])
        db_set(target_uid, prem=1)
        bot.reply_to(
            msg,
            f"✅ **User `{target_uid}`** → **PREMIUM ACTIVATED** ✅",
            parse_mode="Markdown",
        )
    except (ValueError, IndexError):
        bot.reply_to(msg, "❌ Usage: `/premium USERID`", parse_mode="Markdown")


# ===== ENTRY POINT =====
if __name__ == "__main__":
    print("🚀 AI ENGINE - Starting...")
    print(f"👑 Owner: @{OWNER_USERNAME}")
    print(f"📢 Channel: @darkweb")
    print(f"🤖 Models: {len(MODELS)} DeepSeek AI")

    db_init()
    init_ai()
    print("✅ READY!")

    while True:
        try:
            bot.polling(
                none_stop=True, timeout=25, interval=1, long_polling_timeout=15
            )
        except Exception as exc:
            print(f"⚠️ {exc}")
            time.sleep(5)
            init_ai()
