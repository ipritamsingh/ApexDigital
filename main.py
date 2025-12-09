import telebot
from telebot import types
import pymongo
from datetime import datetime, date
import os
from dotenv import load_dotenv

# Server ko jagaye rakhne ke liye (agar file exist karti hai)
try:
    from keep_alive import keep_alive
except ImportError:
    def keep_alive():
        pass  # Agar file nahi hai to ignore karein

# 1. SETUP & CONFIGURATION
load_dotenv()

# --- KEYS LOAD KAREIN ---
# Dhyan rahe .env file me ye sab hona chahiye
USER_TOKEN = os.getenv("USER_BOT_TOKEN")
ADMIN_TOKEN = os.getenv("ADMIN_BOT_TOKEN")

# ID ko integer me convert karte waqt safety check
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID"))
    FORCE_CHANNEL_ID = int(os.getenv("FORCE_SUB_CHANNEL_ID"))
    ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID"))
except TypeError:
    print("❌ Error: .env file me IDs check karein (ADMIN_ID, etc.)")
    exit()

MONGO_URI = os.getenv("MONGO_URI")
FORCE_CHANNEL_LINK = os.getenv("FORCE_SUB_CHANNEL_LINK")

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
        # User ka status check karein channel me
        status = bot.get_chat_member(FORCE_CHANNEL_ID, user_id).status
        return status in ['member', 'administrator', 'creator']
    except Exception as e:
        print(f"Join Check Error: {e}")
        return False # Agar bot admin nahi hai channel me to False dega

# ================= START & REGISTER =================

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    
    # 1. Check agar user pehle se exist karta hai
    if get_user(user_id):
        check_channel_join(message)
        return

    # 2. Referral Check (Start link se aaya hai ya nahi)
    text = message.text.split()
    referrer_id = None
    if len(text) > 1 and text[1].isdigit():
        referrer_id = int(text[1])
        if referrer_id == user_id:
            referrer_id = None  # Khud ko refer nahi kar sakta

    # Disclaimer Show karein
    disclaimer_text = (
        "⚠️ **Terms & Conditions**\n\n"
        "1. Fake referrals = Ban.\n"
        "2. Payment within 24-48 hours.\n"
        "3. Email backup required.\n\n"
        "Do you agree?"
    )
    
    # Referrer ID ko temporarily save karne ke liye hum agle step me pass karenge
    markup = types.InlineKeyboardMarkup()
    # Callback data me referrer id pass kar rahe hain (format: agree_refID)
    callback_val = f"agree_{referrer_id}" if referrer_id else "agree_none"
    
    markup.add(types.InlineKeyboardButton("✅ I Agree", callback_data=callback_val))
    bot.send_message(user_id, disclaimer_text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("agree_"))
def ask_email_step(call):
    bot.delete_message(call.message.chat.id, call.message.message_id)
    
    # Referrer ID extract karein
    referrer_id_str = call.data.split("_")[1]
    referrer_id = int(referrer_id_str) if referrer_id_str != "none" else None
    
    msg = bot.send_message(call.message.chat.id, "📧 **Apna Email ID likh kar bhejein:**")
    bot.register_next_step_handler(msg, save_email_register, referrer_id)

def save_email_register(message, referrer_id):
    user_id = message.from_user.id
    name = message.from_user.first_name
    email = message.text.strip()

    # Email Validation
    if "@" not in email or "." not in email:
        msg = bot.reply_to(message, "❌ Invalid Email! Dobara bhejein:")
        bot.register_next_step_handler(msg, save_email_register, referrer_id)
        return

    # User Data Save
    users_col.insert_one({
        "_id": user_id,
        "name": name,
        "email": email,
        "balance": 0.0,
        "referrals": 0,
        "joined_date": datetime.now(),
        "referrer": referrer_id,
        "last_checkin": None
    })

    # Referrer ko bonus dein
    if referrer_id:
        inc_amount = 1.0 # Refer ka ₹1 (Isse change kar sakte hain)
        users_col.update_one({"_id": referrer_id}, {"$inc": {"balance": inc_amount, "referrals": 1}})
        try:
            bot.send_message(referrer_id, f"🎉 New Referral! +₹{inc_amount} added.")
        except:
            pass

    bot.reply_to(message, "✅ Account Created Successfully!")
    check_channel_join(message)

# ================= CHANNEL CHECK =================

def check_channel_join(message):
    user_id = message.from_user.id
    if not is_joined(user_id):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📢 Join Channel", url=FORCE_CHANNEL_LINK))
        markup.add(types.InlineKeyboardButton("✅ Checked", callback_data="check_join"))
        bot.send_message(user_id, "Bot use karne ke liye Channel Join karein:", reply_markup=markup)
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
    # Reply Keyboard (Neeche wala keyboard)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("💰 Balance", "🔗 Invite")
    markup.add("💸 Withdraw", "📋 Daily Task")
    
    text = (f"👋 Hello {user['name']}\n"
            f"💰 Balance: ₹{round(user.get('balance', 0), 2)}\n"
            f"📧 Email: {user['email']}")
    bot.send_message(user_id, text, reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "💰 Balance")
def show_balance(message):
    user = get_user(message.from_user.id)
    bot.reply_to(message, f"💰 Current Balance: ₹{round(user['balance'], 2)}")

@bot.message_handler(func=lambda message: message.text == "🔗 Invite")
def invite_link_gen(message):
    user_id = message.from_user.id
    bot_username = bot.get_me().username
    link = f"https://t.me/{bot_username}?start={user_id}"
    
    msg = (f"📣 **Refer & Earn**\n\n"
           f"Apne dosto ko invite karein aur kamayein!\n"
           f"Your Link: `{link}`")
    bot.reply_to(message, msg, parse_mode="Markdown")

# ================= DAILY TASK (UPDATED) =================

@bot.message_handler(func=lambda message: message.text == "📋 Daily Task")
def daily_task_info(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📢 Go to Channel", url=FORCE_CHANNEL_LINK))
    # Claim button add kiya taaki user paise le sake
    markup.add(types.InlineKeyboardButton("💰 Claim Reward", callback_data="claim_daily"))
    
    bot.reply_to(message, "👇 Aaj ka Task: Channel visit karein aur Claim karein!", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "claim_daily")
def claim_daily_reward(call):
    user_id = call.from_user.id
    user = get_user(user_id)
    
    today = date.today().isoformat() # Aaj ki date string format me (YYYY-MM-DD)
    last_checkin = user.get("last_checkin")
    
    if last_checkin == today:
        bot.answer_callback_query(call.id, "❌ Aaj ka reward le liya hai! Kal aana.", show_alert=True)
    else:
        reward = 0.50 # Daily check-in amount
        users_col.update_one(
            {"_id": user_id}, 
            {
                "$inc": {"balance": reward}, 
                "$set": {"last_checkin": today}
            }
        )
        bot.answer_callback_query(call.id, f"✅ Success! ₹{reward} added.", show_alert=True)
        bot.delete_message(call.message.chat.id, call.message.message_id)

# ================= WITHDRAW =================

@bot.message_handler(func=lambda message: message.text == "💸 Withdraw")
def withdraw_start(message):
    user_id = message.from_user.id
    user = get_user(user_id)
    
    if user['balance'] < 20:
        bot.reply_to(message, f"❌ Minimum Withdraw ₹20 hai.\nApka Balance: ₹{round(user['balance'], 2)}")
        return
        
    msg = bot.send_message(user_id, "🏧 **Apna UPI ID bhejein:**")
    bot.register_next_step_handler(msg, process_withdraw)

def process_withdraw(message):
    user_id = message.from_user.id
    upi = message.text
    user = get_user(user_id)
    amount = user['balance']
    
    # Balance zero kar do
    users_col.update_one({"_id": user_id}, {"$set": {"balance": 0.0}})
    
    # Withdraw history save karo
    withdraw_col.insert_one({
        "user_id": user_id,
        "name": user['name'],
        "email": user['email'],
        "amount": amount,
        "upi": upi,
        "date": datetime.now()
    })
    
    bot.reply_to(message, "✅ Withdrawal Request Sent! Payment 24-48 hours me aayega.")
    
    # ADMIN ALERT
    alert_msg = (f"🔔 **NEW WITHDRAW**\n"
                 f"👤 Name: {user['name']}\n"
                 f"🆔 ID: `{user_id}`\n"
                 f"💳 UPI: `{upi}`\n"
                 f"💰 Amount: ₹{amount}")
    
    try:
        # Admin Bot se Admin ko msg bhejo
        admin_bot.send_message(ADMIN_ID, alert_msg, parse_mode="Markdown")
        admin_bot.send_message(ADMIN_GROUP_ID, alert_msg, parse_mode="Markdown")
    except Exception as e:
        print(f"Admin Alert Failed: {e}")

# ================= RUN =================
print("🤖 Bot Started...")
keep_alive()
bot.infinity_polling()
