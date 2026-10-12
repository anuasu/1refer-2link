from telebot import types
from bot import bot
from config import GROUP_ID, GROUP_INVITE_LINK, CHANNEL_ID, CHANNEL_INVITE_LINK, LINK_UNLOCK_COST
from database import get_user, complete_verification, get_active_links, has_unlocked_link, unlock_link


def check_membership(user_id):
    try:
        group_member = bot.get_chat_member(GROUP_ID, user_id)
        channel_member = bot.get_chat_member(CHANNEL_ID, user_id)
        valid_statuses = ("member", "administrator", "creator")
        return group_member.status in valid_statuses and channel_member.status in valid_statuses
    except Exception:
        return False


def join_keyboard():
    keyboard = types.InlineKeyboardMarkup()
    keyboard.row(types.InlineKeyboardButton("📢 Join Group", url=GROUP_INVITE_LINK))
    keyboard.row(types.InlineKeyboardButton("📣 Join Channel", url=CHANNEL_INVITE_LINK))
    keyboard.row(types.InlineKeyboardButton("✅ Check Join", callback_data="check_join"))
    return keyboard


def show_links(chat_id, user_id, notice=None):
    links = get_active_links()

    if not links:
        bot.send_message(chat_id, "📭 Abhi koi link available nahi hai.")
        return

    next_link = None
    next_number = None

    for index, link in enumerate(links, start=1):
        if not has_unlocked_link(user_id, int(link["id"])):
            next_link = link
            next_number = index
            break

    if next_link is None:
        text = (
            "🔓 <b>OPEN LINKS</b>\n\n"
            f"🔗 Total Available Links: <b>{len(links)}</b>\n\n"
            "🎉 Aapne saare available links unlock kar liye hain!"
        )
        if notice:
            text = notice + "\n\n" + text
        bot.send_message(chat_id, text, parse_mode="HTML")
        return

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton(
            f"🔓 Open Link #{next_number} | {LINK_UNLOCK_COST} Coin",
            callback_data=f"unlock_{next_link['id']}"
        )
    )

    text = (
        "🔓 <b>OPEN LINKS</b>\n\n"
        f"🔗 Total Available Links: <b>{len(links)}</b>\n"
        f"📍 Current Link: <b>#{next_number}</b>\n"
        f"💰 Unlock Cost: <b>{LINK_UNLOCK_COST} Coin</b>\n\n"
        "Link unlock karne ke liye neeche button dabao.\n"
        "Ek hi link ko dobara unlock karne par coins dobara nahi katenge."
    )

    if notice:
        text = notice + "\n\n" + text

    bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode="HTML")


def open_links(message):
    user_id = message.from_user.id

    if not get_user(user_id):
        bot.reply_to(message, "Pehle /start karke account register karo.")
        return

    if not check_membership(user_id):
        bot.send_message(
            message.chat.id,
            "🔐 Open Links use karne ke liye group aur channel dono join karo.",
            reply_markup=join_keyboard()
        )
        return

    verification = complete_verification(user_id)

    if not verification["success"]:
        bot.send_message(message.chat.id, "Verification complete nahi hua. Dobara /start karo.")
        return

    show_links(message.chat.id, user_id)


@bot.message_handler(commands=["links"])
def links_command(message):
    open_links(message)


@bot.message_handler(func=lambda message: message.text is not None and message.text.strip() == "🔓 Open Links")
def links_button(message):
    open_links(message)


@bot.callback_query_handler(func=lambda call: call.data is not None and call.data.startswith("unlock_"))
def unlock_link_callback(call):
    user_id = call.from_user.id

    if not get_user(user_id):
        bot.answer_callback_query(call.id, "Pehle /start karo!", show_alert=True)
        return

    if not check_membership(user_id):
        bot.answer_callback_query(call.id, "Pehle group aur channel dono join karo!", show_alert=True)
        bot.send_message(
            call.message.chat.id,
            "🔐 Link unlock karne ke liye group aur channel dono join karo.",
            reply_markup=join_keyboard()
        )
        return

    verification = complete_verification(user_id)

    if not verification["success"]:
        bot.answer_callback_query(call.id, "Verification complete nahi hua!", show_alert=True)
        return

    try:
        link_id = int(call.data.split("_", 1)[1])
    except (ValueError, IndexError):
        bot.answer_callback_query(call.id, "Invalid link!", show_alert=True)
        return

    result = unlock_link(user_id, link_id)

    if not result["success"]:
        reason = result.get("reason")

        if reason == "insufficient_coins":
            error_message = f"Coins kam hain! Balance: {result.get('balance', 0)}"
        elif reason == "user_not_verified":
            error_message = "Pehle verification complete karo!"
        else:
            error_message = "Ye link available nahi hai."

        bot.answer_callback_query(call.id, error_message, show_alert=True)
        return

    bot.answer_callback_query(
        call.id,
        "Link pehle se unlocked hai!" if result["already_unlocked"] else "Link unlock ho gaya!"
    )

    links = get_active_links()
    current_number = next(
        (index for index, link in enumerate(links, start=1) if int(link["id"]) == link_id),
        None
    )

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("🔗 Open Link", url=result["url"]))

    bot.send_message(
        call.message.chat.id,
        "✅ <b>Link Unlock Successful!</b>\n\n"
        + (f"📍 Link <b>#{current_number}</b> successfully unlock ho gaya!\n" if current_number else "")
        + f"💰 Remaining Coins: <b>{result['balance']}</b>\n\n"
        "Neeche button se link open karo.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

    notice = (
        f"✅ Aapne Link #{current_number} successfully unlock kar liya!"
        if current_number else "✅ Link successfully unlock ho gaya!"
    )

    show_links(call.message.chat.id, user_id, notice=notice)


@bot.callback_query_handler(func=lambda call: call.data == "back_to_links")
def back_to_links_callback(call):
    user_id = call.from_user.id

    if not get_user(user_id):
        bot.answer_callback_query(call.id, "Pehle /start karo!", show_alert=True)
        return

    if not check_membership(user_id):
        bot.answer_callback_query(call.id, "Pehle group aur channel dono join karo!", show_alert=True)
        return

    bot.answer_callback_query(call.id)
    show_links(call.message.chat.id, user_id)
