import telebot
from telebot import types
import pymongo
from datetime import datetime
import os
from dotenv import load_dotenv
from keep_alive import keep_alive  # Server ko jagaye rakhne ke liye

# 1. SETUP & CONFIGURATION
load_dotenv()  # Local testing ke liye

# Variables load karein
USER_TOKEN = os.getenv("USER_BOT_TOKEN")
ADMIN_TOKEN = os.getenv("ADMIN_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
FORCE_CHANNEL_ID = int(os.getenv("FORCE_SUB_CHANNEL_ID"))
FORCE_CHANNEL_LINK = os.getenv("FORCE_SUB_CHANNEL_LINK")
MONGO_URI = os.getenv("MONGO_URI")

# Database Connection
client = pymongo.MongoClient(MONGO_URI)
db = client["EarningBotDB"]
users_col = db["users"]
withdraw_col = db["withdrawals"]

# DO BOTS SETUP
bot = telebot.TeleBot(USER_TOKEN)       # Public Bot
admin_bot = telebot.TeleBot(ADMIN_TOKEN) # Admin Alert Bot

# ================= HELPER FUNCTIONS =================

def get_user(user_id):
    return users_col.find_one({"_id": user_id})

def is_joined(user_id):
    try:
        # Check User Bot ke through hi hoga
        status = bot.get_chat_member(FORCE_CHANNEL_ID, user_id).status
        return status in ['member', 'administrator', 'creator']
    except:
        return False

# ================= STEP 1: START & REGISTRATION =================

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    
    # Agar purana user hai
    if get_user(user_id):
        check_channel_join(message)
        return

    # Naya User: Disclaimer Popup
    disclaimer_text = (
        "⚠️ **Terms & Conditions**\n\n"
        "1. Fake referrals karne par ID Ban hogi.\n"
        "2. Payment 24-48 hours mein milega.\n"
        "3. Hum backup ke liye Email lenge.\n\n"
        "Kya aap sehmat hain?"
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

    # Email Validation
    if "@" not in email or "." not in email:
        msg = bot.reply_to(message, "❌ Invalid Email! Sahi email likhein:")
        bot.register_next_step_handler(msg, save_email_register)
        return

    # Database Entry
    users_col.insert_one({
        "_id": user_id,
        "name": name,
        "email": email,
        "balance": 0.0,
        "referrals": 0,
        "joined_date": datetime.now()
    })

    bot.reply_to(message, "✅ Account Created Successfully!")
    check_channel_join(message)

# ================= STEP 2: CHANNEL CHECK =================

def check_channel_join(message):
    user_id = message.from_user.id
    if not is_joined(user_id):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📢 Join Channel", url=FORCE_CHANNEL_LINK))
        markup.add(types.InlineKeyboardButton("✅ Joined", callback_data="check_join"))
        bot.send_message(user_id, "Bot use karne ke liye channel join karein:", reply_markup=markup)
    else:
        show_main_menu(user_id)

@bot.callback_query_handler(func=lambda call: call.data == "check_join")
def callback_join(call):
    if is_joined(call.from_user.id):
        bot.delete_message(call.message.chat.id, call.message.message_id)
        show_main_menu(call.from_user.id)
    else:
        bot.answer_callback_query(call.id, "❌ Pehle Channel Join Karein!", show_alert=True)

# ================= STEP 3: MAIN DASHBOARD =================

def show_main_menu(user_id):
    user = get_user(user_id)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("💰 Balance", "🔗 Invite")
    markup.add("💸 Withdraw", "🆘 Support")
    
    text = (f"👋 Hello {user['name']}\n"
            f"💰 Balance: ₹{user.get('balance', 0)}\n"
            f"📧 Email: {user['email']}")
    
    bot.send_message(user_id, text, reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "💰 Balance")
def show_balance(message):
    user = get_user(message.from_user.id)
    bot.reply_to(message, f"💰 Aapka Balance: ₹{user['balance']}")

@bot.message_handler(func=lambda message: message.text == "🔗 Invite")
def invite_link(message):
    user_id = message.from_user.id
    bot_username = bot.get_me().username
    link = f"https://t.me/{bot_username}?start={user_id}"
    bot.reply_to(message, f"🔗 **Refer Link:**\n{link}\n\nShare karein aur kamayein!")

@bot.message_handler(func=lambda message: message.text == "🆘 Support")
def support_handler(message):
    bot.reply_to(message, "📞 Admin Contact: @YourAdminIDHere") # Apna username daal dena

# ================= STEP 4: WITHDRAW SYSTEM =================

@bot.message_handler(func=lambda message: message.text == "💸 Withdraw")
def withdraw_start(message):
    user_id = message.from_user.id
    user = get_user(user_id)
    
    if user['balance'] < 20: # Example limit
        bot.reply_to(message, "❌ Minimum Withdraw ₹20 hai.")
        return
        
    msg = bot.send_message(user_id, "🏧 **Apna UPI Address bhejein:**")
    bot.register_next_step_handler(msg, process_withdraw)

def process_withdraw(message):
    user_id = message.from_user.id
    upi_id = message.text
    user = get_user(user_id)
    amount = user['balance']
    
    # 1. Deduct Balance
    users_col.update_one({"_id": user_id}, {"$set": {"balance": 0.0}})
    
    # 2. Save Log
    withdraw_col.insert_one({
        "user_id": user_id,
        "name": user['name'],
        "email": user['email'],
        "amount": amount,
        "upi": upi_id,
        "status": "pending",
        "date": datetime.now()
    })
    
    bot.reply_to(message, "✅ Request Sent! 24 Hours me payment aayega.")
    
    # 3. NOTIFY ADMIN (Via 2nd Bot)
    try:
        admin_msg = (
            f"🔔 **NEW WITHDRAWAL**\n\n"
            f"👤 Name: {user['name']}\n"
            f"📧 Email: `{user['email']}`\n"
            f"💰 Amount: ₹{amount}\n"
            f"🏦 UPI: `{upi_id}`\n"
            f"🆔 User ID: `{user_id}`"
        )
        admin_bot.send_message(ADMIN_ID, admin_msg, parse_mode="Markdown")
    except Exception as e:
        print(f"Admin Alert Error: {e}")

# ================= RUN SERVER =================
print("Bot is Alive...")
keep_alive()  # Web server start
bot.infinity_polling() # Telegram bot start
