from telebot import types

from bot import bot

from config import (
GROUP_ID,
GROUP_INVITE_LINK,
CHANNEL_ID,
CHANNEL_INVITE_LINK,
LINK_UNLOCK_COST
)

from database import (
get_user,
complete_verification,
get_active_links,
unlock_link
)

def check_membership(user_id):
try:
group_member = bot.get_chat_member(GROUP_ID, user_id)
channel_member = bot.get_chat_member(CHANNEL_ID, user_id)

    valid_statuses = ("member", "administrator", "creator")

    return (
        group_member.status in valid_statuses
        and channel_member.status in valid_statuses
    )
except Exception:
    return False

def join_keyboard():
keyboard = types.InlineKeyboardMarkup()

keyboard.row(
    types.InlineKeyboardButton(
        "📢 Join Group",
        url=GROUP_INVITE_LINK
    )
)

keyboard.row(
    types.InlineKeyboardButton(
        "📣 Join Channel",
        url=CHANNEL_INVITE_LINK
    )
)

keyboard.row(
    types.InlineKeyboardButton(
        "✅ Check Join",
        callback_data="check_join"
    )
)

return keyboard

def get_next_link(links, user_id):
for index, link in enumerate(links):
link_id = int(link["id"])

    result = None

    try:
        result = unlock_link(user_id, link_id)
    except Exception:
        result = None

    if result and result.get("already_unlocked"):
        continue

    return index, link

return None, None

def show_links(chat_id, user_id, notice=None):
links = get_active_links()

if not links:
    bot.send_message(
        chat_id,
        "📭 Abhi koi link available nahi hai."
    )
    return

keyboard = types.InlineKeyboardMarkup()

next_index, next_link = get_next_link(links, user_id)

if next_link is None:
    text = (
        "🔓 <b>OPEN LINKS</b>\n\n"
        f"🔗 Total Available Links: <b>{len(links)}</b>\n\n"
        "🎉 Aapne saare available links unlock kar liye hain!\n"
        "Dobara kisi unlocked link ko open karne par coins nahi katenge."
    )

    if notice:
        text = notice + "\n\n" + text

    bot.send_message(
        chat_id,
        text,
        parse_mode="HTML"
    )
    return

link_number = next_index + 1

keyboard.row(
    types.InlineKeyboardButton(
        f"🔓 Open Link #{link_number} | {LINK_UNLOCK_COST} Coin",
        callback_data=f"unlock_{next_link['id']}"
    )
)

text = (
    "🔓 <b>OPEN LINKS</b>\n\n"
    f"🔗 Total Available Links: <b>{len(links)}</b>\n"
    f"📍 Aap abhi Link <b>#{link_number}</b> par ho.\n"
    f"💰 New link unlock cost: <b>{LINK_UNLOCK_COST} Coin</b>\n\n"
    "Ek baar unlock kiya hua link dobara open karne par coins nahi katenge."
)

if notice:
    text = notice + "\n\n" + text

bot.send_message(
    chat_id,
    text,
    reply_markup=keyboard,
    parse_mode="HTML"
)

def open_links(message):
user_id = message.from_user.id

user = get_user(user_id)

if not user:
    bot.reply_to(
        message,
        "Pehle /start karke account register karo."
    )
    return

if not check_membership(user_id):
    bot.send_message(
        message.chat.id,
        "🔐 Open Links use karne ke liye group aur channel dono join karo.",
        reply_markup=join_keyboard()
    )
    return

result = complete_verification(user_id)

if not result["success"]:
    bot.send_message(
        message.chat.id,
        "Verification complete nahi hua. Dobara /start karo."
    )
    return

show_links(message.chat.id, user_id)

@bot.message_handler(commands=["links"])
def links_command(message):
open_links(message)

@bot.message_handler(
func=lambda message: (
message.text is not None
and message.text.strip() == "🔓 Open Links"
)
)
def links_button(message):
open_links(message)

@bot.callback_query_handler(
func=lambda call: (
call.data is not None
and call.data.startswith("unlock_")
)
)
def unlock_link_callback(call):
user_id = call.from_user.id

user = get_user(user_id)

if not user:
    bot.answer_callback_query(
        call.id,
        "Pehle /start karo!",
        show_alert=True
    )
    return

if not check_membership(user_id):
    bot.answer_callback_query(
        call.id,
        "Pehle group aur channel dono join karo!",
        show_alert=True
    )

    bot.send_message(
        call.message.chat.id,
        "🔐 Link unlock karne ke liye group aur channel dono join karo.",
        reply_markup=join_keyboard()
    )
    return

verification = complete_verification(user_id)

if not verification["success"]:
    bot.answer_callback_query(
        call.id,
        "Verification complete nahi hua!",
        show_alert=True
    )
    return

try:
    link_id = int(call.data.split("_", 1)[1])
except (ValueError, IndexError):
    bot.answer_callback_query(
        call.id,
        "Invalid link!",
        show_alert=True
    )
    return

result = unlock_link(user_id, link_id)

if not result["success"]:
    reason = result.get("reason")

    if reason == "insufficient_coins":
        bot.answer_callback_query(
            call.id,
            f"Coins kam hain! Balance: {result.get('balance', 0)}",
            show_alert=True
        )

    elif reason == "user_not_verified":
        bot.answer_callback_query(
            call.id,
            "Pehle verification complete karo!",
            show_alert=True
        )

    else:
        bot.answer_callback_query(
            call.id,
            "Ye link available nahi hai.",
            show_alert=True
        )

    return

bot.answer_callback_query(
    call.id,
    (
        f"Link pehle se unlocked hai! Balance: {result['balance']}"
        if result["already_unlocked"]
        else f"Link unlock ho gaya! Balance: {result['balance']}"
    )
)

links = get_active_links()
unlocked_id = link_id
current_number = next(
    (
        index + 1
        for index, link in enumerate(links)
        if int(link["id"]) == unlocked_id
    ),
    None
)

keyboard = types.InlineKeyboardMarkup()

keyboard.row(
    types.InlineKeyboardButton(
        "🔗 Open Link",
        url=result["url"]
    )
)

bot.send_message(
    call.message.chat.id,
    "✅ <b>Link Unlock Successful!</b>\n\n"
    + (
        f"🎉 Aapne Link <b>#{current_number}</b> successfully unlock kar liya!\n"
        if current_number is not None
        else "🎉 Aapka link successfully unlock ho gaya!\n"
    )
    + f"💰 Remaining Coins: <b>{result['balance']}</b>\n\n"
    "Neeche diye button se link open karo.",
    reply_markup=keyboard,
    parse_mode="HTML"
)

show_links(
    call.message.chat.id,
    user_id,
    notice=(
        f"✅ Aapne Link #{current_number} successfully unlock kar liya!"
        if current_number is not None
        else "✅ Link successfully unlock ho gaya!"
    )
)

@bot.callback_query_handler(
func=lambda call: call.data == "back_to_links"
)
def back_to_links_callback(call):
user_id = call.from_user.id

if not get_user(user_id):
    bot.answer_callback_query(
        call.id,
        "Pehle /start karo!",
        show_alert=True
    )
    return

if not check_membership(user_id):
    bot.answer_callback_query(
        call.id,
        "Pehle group aur channel dono join karo!",
        show_alert=True
    )
    return

bot.answer_callback_query(call.id)

show_links(
    call.message.chat.id,
    user_id
)
