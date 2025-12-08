import telebot
from telebot import types
import pymongo
from datetime import datetime
import os
from dotenv import load_dotenv
from keep_alive import keep_alive  # Server ko jagaye rakhne ke liye

# 1. SETUP & CONFIGURATION
load_dotenv()

# --- KEYS LOAD KAREIN ---
USER_TOKEN = os.getenv("USER_BOT_TOKEN")
ADMIN_TOKEN = os.getenv("ADMIN_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
MONGO_URI = os.getenv("MONGO_URI")

# Channels & Groups
FORCE_CHANNEL_ID = int(os.getenv("FORCE_SUB_CHANNEL_ID"))
FORCE_CHANNEL_LINK = os.getenv("FORCE_SUB_CHANNEL_LINK") # Yehi link ab Check-in ke liye use hoga
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID")) # Proof Group

# Shortener API Keys (Render se load hongi)
KEY_GPLINK = os.getenv("GPLINK_KEY")
KEY_SHRINKME = os.getenv("SHRINKME_KEY")
KEY_SHRINKEARN = os.getenv("SHRINKEARN_KEY")

# Database Connection
client = pymongo.MongoClient(MONGO_URI)
db = client["EarningBotDB"]
users_col = db["users"]
withdraw_col = db["withdrawals"]

# DO BOTS SETUP
bot = telebot.TeleBot(USER_TOKEN)
admin_bot = telebot.TeleBot(ADMIN_TOKEN)

# ================= HELPER FUNCTIONS =================

def get_user(user_id):
    return users_col.find_one({"_id": user_id})

def is_joined(user_id):
    try:
        status = bot.get_chat_member(FORCE_CHANNEL_ID, user_id).status
        return status in ['member', 'administrator', 'creator']
    except:
        return False

# ================= START & REGISTER =================

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    
    if get_user(user_id):
        check_channel_join(message)
        return

    # Disclaimer
    disclaimer_text = (
        "⚠️ **Terms & Conditions**\n\n"
        "1. Fake referrals = Ban.\n"
        "2. Payment within 24-48 hours.\n"
        "3. Email backup required.\n\n"
        "Do you agree?"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ I Agree", callback_data="agree_terms"))
    bot.send_message(user_id, disclaimer_text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "agree_terms")
def ask_email_step(call):
    bot.delete_message(call.message.chat.id, call.message.message_id)
    msg = bot.send_message(call.message.chat.id, "📧 **Apna Email ID likh kar bhejein:**")
    bot.register_next_step_handler(msg, save_email_register)

def save_email_register(message):
    user_id = message.from_user.id
    name = message.from_user.first_name
    email = message.text.strip()

    if "@" not in email or "." not in email:
        msg = bot.reply_to(message, "❌ Invalid Email!")
        bot.register_next_step_handler(msg, save_email_register)
        return

    users_col.insert_one({
        "_id": user_id,
        "name": name,
        "email": email,
        "balance": 0.0,
        "referrals": 0,
        "joined_date": datetime.now()
    })
    bot.reply_to(message, "✅ Account Created!")
    check_channel_join(message)

# ================= CHANNEL CHECK =================

def check_channel_join(message):
    user_id = message.from_user.id
    if not is_joined(user_id):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📢 Join Channel", url=FORCE_CHANNEL_LINK))
        markup.add(types.InlineKeyboardButton("✅ Checked", callback_data="check_join"))
        bot.send_message(user_id, "Channel Join karein:", reply_markup=markup)
    else:
        show_main_menu(user_id)

@bot.callback_query_handler(func=lambda call: call.data == "check_join")
def callback_join(call):
    if is_joined(call.from_user.id):
        bot.delete_message(call.message.chat.id, call.message.message_id)
        show_main_menu(call.from_user.id)
    else:
        bot.answer_callback_query(call.id, "❌ Join nahi kiya!", show_alert=True)

# ================= DASHBOARD =================

def show_main_menu(user_id):
    user = get_user(user_id)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("💰 Balance", "🔗 Invite")
    markup.add("💸 Withdraw", "📋 Daily Task")
    
    text = (f"👋 Hello {user['name']}\n"
            f"💰 Balance: ₹{user.get('balance', 0)}\n"
            f"📧 Email: {user['email']}")
    bot.send_message(user_id, text, reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "💰 Balance")
def show_balance(message):
    user = get_user(message.from_user.id)
    bot.reply_to(message, f"💰 Balance: ₹{user['balance']}")

@bot.message_handler(func=lambda message: message.text == "📋 Daily Task")
def daily_task_info(message):
    # Ab ye button seedha FORCE JOIN CHANNEL par le jayega
    markup = types.InlineKeyboardMarkup()
    # Yahan FORCE_CHANNEL_LINK use kiya hai engagement ke liye
    markup.add(types.InlineKeyboardButton("✅ Daily Check-in (Channel)", url=FORCE_CHANNEL_LINK))
    
    bot.reply_to(message, "👇 Aaj ka Task (Check-in):", reply_markup=markup)

# ================= WITHDRAW =================

@bot.message_handler(func=lambda message: message.text == "💸 Withdraw")
def withdraw_start(message):
    user_id = message.from_user.id
    user = get_user(user_id)
    if user['balance'] < 20:
        bot.reply_to(message, "❌ Min Withdraw ₹20")
        return
    msg = bot.send_message(user_id, "🏧 **UPI ID bhejein:**")
    bot.register_next_step_handler(msg, process_withdraw)

def process_withdraw(message):
    user_id = message.from_user.id
    upi = message.text
    user = get_user(user_id)
    amount = user['balance']
    
    users_col.update_one({"_id": user_id}, {"$set": {"balance": 0.0}})
    
    withdraw_col.insert_one({
        "user_id": user_id,
        "name": user['name'],
        "email": user['email'],
        "amount": amount,
        "upi": upi,
        "date": datetime.now()
    })
    
    bot.reply_to(message, "✅ Request Sent!")
    
    # ADMIN ALERT (Group + Private)
    alert_msg = f"🔔 **NEW WITHDRAW**\nName: {user['name']}\nUPI: `{upi}`\nAmount: ₹{amount}"
    try:
        admin_bot.send_message(ADMIN_ID, alert_msg, parse_mode="Markdown")
        admin_bot.send_message(ADMIN_GROUP_ID, alert_msg, parse_mode="Markdown") # Group me bhi bhejega
    except Exception as e:
        print(f"Error: {e}")

# ================= RUN =================
print("Bot Alive...")
keep_alive()
bot.infinity_polling()
