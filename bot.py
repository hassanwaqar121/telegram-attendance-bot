import json
import os
import calendar
import asyncio
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import pytz
from keep_alive import keep_alive

# ============ SETTINGS ============
BOT_TOKEN = os.environ.get("BOT_TOKEN")
PAKISTAN_TZ = pytz.timezone("Asia/Karachi")
DATA_FILE = "user_data.json"

# ============ DATA FUNCTIONS ============
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def get_now():
    return datetime.now(PAKISTAN_TZ)

def get_total_days_in_month(now):
    return calendar.monthrange(now.year, now.month)[1]

def get_monthly_stats(user_data, now):
    current_month = now.strftime("%Y-%m")
    monthly_records = [r for r in user_data.get("attendance", []) if r["date"].startswith(current_month)]
    present_days = len(monthly_records)
    late_days = len([r for r in monthly_records if r.get("is_late", False)])
    total_days = get_total_days_in_month(now)
    days_passed = now.day
    off_days = days_passed - present_days
    if off_days < 0:
        off_days = 0
    return {"total_days": total_days, "present_days": present_days, "late_days": late_days, "off_days": off_days}

def get_monthly_stats_text(user_data, now):
    stats = get_monthly_stats(user_data, now)
    month_name = now.strftime("%B %Y")
    return (
        f"📊 *MONTHLY REPORT ({month_name.upper()})*\n\n"
        f"📆 Total Working Days:  *{stats['total_days']} days*\n\n"
        f"✅ Present Days:  *{stats['present_days']} days*\n\n"
        f"❌ Off Days:  *{stats['off_days']} days*\n\n"
        f"❗ Late Days:  *{stats['late_days']} days*"
    )

def format_duration(total_seconds):
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    result = ""
    if h > 0:
        result += f"{h} hour "
    if m > 0:
        result += f"{m} min "
    if s > 0:
        result += f"{s} sec"
    return result.strip() if result else "0 sec"

def get_main_menu():
    keyboard = [
        [KeyboardButton("🟢 Start Work"), KeyboardButton("🚻 Washroom")],
        [KeyboardButton("🚬 Smoke"), KeyboardButton("☕ Break")],
        [KeyboardButton("💺 Back to Seat"), KeyboardButton("🔴 Off Work")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏢 *EMPLOYEE ATTENDANCE SYSTEM*\n\n👋 Welcome! Please select an action from the buttons below.",
        reply_markup=get_main_menu(), parse_mode="Markdown"
    )

async def handle_start_work(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    username = f"@{user.username}" if user.username else user.first_name
    user_id = str(user.id)
    now = get_now()
    current_time = now.strftime("%I:%M:%S %p")
    current_date = now.strftime("%Y-%m-%d")
    day_name = now.strftime("%A")

    if day_name == "Sunday":
        scheduled_time = now.replace(hour=16, minute=0, second=0, microsecond=0)
        shift_type = "Half Day (Sunday)"
        scheduled_str = "04:00:00 PM"
    else:
        scheduled_time = now.replace(hour=10, minute=0, second=0, microsecond=0)
        shift_type = "Full Day"
        scheduled_str = "10:00:00 AM"

    data = load_data()
    if user_id not in data:
        data[user_id] = {"username": username, "attendance": [], "activities": []}

    today_records = [r for r in data[user_id]["attendance"] if r["date"] == current_date]
    if today_records:
        await update.message.reply_text(
            f"⚠️ *ALREADY AT WORK!*\n\n👤 User:  {username}\n\n❌ You are *already in work!*\n\n"
            f"📅 Date:  *{current_date}*\n\n⏰ Started At:  *{today_records[0]['start_time']}*\n\n"
            f"🔔 Please press  *🔴 Off Work*  first to end your shift.",
            parse_mode="Markdown", reply_markup=get_main_menu()
        )
        return

    is_late = now > scheduled_time
    late_message = ""
    if is_late:
        late_duration = now - scheduled_time
        late_time_str = format_duration(int(late_duration.total_seconds()))
        late_message = (
            f"\n\n❗🔴 *LATE ARRIVAL* 🔴❗\n\n⏰ Scheduled Time:  *{scheduled_str}*\n\n"
            f"⏰ Arrival Time:  *{current_time}*\n\n⏳ Late By:  *{late_time_str}*"
        )
        status = "LATE ❗"
    else:
        status = "ON TIME ✅"

    data[user_id]["attendance"].append({
        "date": current_date, "day": day_name, "start_time": current_time,
        "start_timestamp": now.isoformat(), "status": status, "is_late": is_late,
        "shift_type": shift_type, "end_time": None, "end_timestamp": None
    })
    save_data(data)
    monthly_text = get_monthly_stats_text(data[user_id], now)

    message = (
        f"🟢 *WORK STARTED* 🟢\n\n👤 User:  {username}\n\n📅 Date:  *{current_date}*  ({day_name})\n\n"
        f"⏰ Time:  *{current_time}*\n\n📌 Shift:  *{shift_type}*\n\n📌 Status:  *{status}*"
        f"{late_message}\n\n━━━━━━━━━━━━━━━━━━\n\n{monthly_text}"
    )
    await update.message.reply_text(text=message, parse_mode="Markdown", reply_markup=get_main_menu())

def check_work_started(data, user_id, current_date):
    if user_id not in data:
        return False
    return len([r for r in data[user_id].get("attendance", []) if r["date"] == current_date]) > 0

async def handle_activity(update, context, activity_name, icon, extra_info=""):
    user = update.message.from_user
    username = f"@{user.username}" if user.username else user.first_name
    user_id = str(user.id)
    now = get_now()
    current_time = now.strftime("%I:%M:%S %p")
    current_date = now.strftime("%Y-%m-%d")
    data = load_data()

    if not check_work_started(data, user_id, current_date):
        await update.message.reply_text(
            f"⚠️ *ACTION DENIED!*\n\n👤 User:  {username}\n\n❌ You have *not started work yet!*\n\n"
            f"🔔 Please press  *🟢 Start Work*  first.",
            parse_mode="Markdown", reply_markup=get_main_menu()
        )
        return

    active = [a for a in data[user_id].get("activities", []) if a["date"] == current_date and a.get("end_time") is None]
    if active:
        await update.message.reply_text(
            f"⚠️ *ACTION DENIED!*\n\n👤 User:  {username}\n\n"
            f"❌ You are *already engaged in {active[0]['type']}* activity!\n\n"
            f"🔔 Please press  *💺 Back to Seat*  first.",
            parse_mode="Markdown", reply_markup=get_main_menu()
        )
        return

    activity = {
        "date": current_date, "type": activity_name, "start_time": current_time,
        "start_timestamp": now.isoformat(), "end_time": None, "end_timestamp": None, "duration": None
    }
    if activity_name == "Break":
        deadline = now.replace(hour=15, minute=0, second=0, microsecond=0)
        activity["deadline"] = "03:00:00 PM"
        activity["deadline_timestamp"] = deadline.isoformat()

    if "activities" not in data[user_id]:
        data[user_id]["activities"] = []
    data[user_id]["activities"].append(activity)
    save_data(data)

    if activity_name == "Break":
        message = (
            f"☕ *BREAK STARTED*\n\n👤 User:  {username}\n\n📅 Date:  *{current_date}*\n\n"
            f"⏰ Break Start:  *{current_time}*\n\n⏳ Break Duration:  *1 Hour*\n\n"
            f"⏰ You must be back by:  *03:00:00 PM*\n\n"
            f"🔔 Please press  *💺 Back to Seat*  when you return."
        )
    else:
        message = (
            f"{icon} *{activity_name.upper()} BREAK*\n\n👤 User:  {username}\n\n"
            f"📅 Date:  *{current_date}*\n\n⏰ Time:  *{current_time}*\n\n"
            f"✅ {activity_name} break  *registered!*\n\n🔓 You have *permission to go.*\n\n"
            f"🔔 Please press  *💺 Back to Seat*  when you return."
        )
    await update.message.reply_text(text=message, parse_mode="Markdown", reply_markup=get_main_menu())

async def handle_washroom(update, context):
    await handle_activity(update, context, "Washroom", "🚻")

async def handle_smoke(update, context):
    await handle_activity(update, context, "Smoke", "🚬")

async def handle_break(update, context):
    await handle_activity(update, context, "Break", "☕")

async def handle_back_to_seat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    username = f"@{user.username}" if user.username else user.first_name
    user_id = str(user.id)
    now = get_now()
    current_time = now.strftime("%I:%M:%S %p")
    current_date = now.strftime("%Y-%m-%d")
    data = load_data()

    if not check_work_started(data, user_id, current_date):
        await update.message.reply_text(
            f"⚠️ *ACTION DENIED!*\n\n👤 User:  {username}\n\n❌ You have *not started work yet!*\n\n"
            f"🔔 Please press  *🟢 Start Work*  first.",
            parse_mode="Markdown", reply_markup=get_main_menu()
        )
        return

    active = None
    active_index = None
    for i, a in enumerate(data[user_id].get("activities", [])):
        if a["date"] == current_date and a.get("end_time") is None:
            active = a
            active_index = i
            break

    if not active:
        await update.message.reply_text(
            f"⚠️ *ACTION DENIED!*\n\n👤 User:  {username}\n\n❌ You are *not engaged in any activity!*\n\n"
            f"🔔 No active  *Washroom / Smoke / Break*  found.",
            parse_mode="Markdown", reply_markup=get_main_menu()
        )
        return

    start_dt = datetime.fromisoformat(active["start_timestamp"])
    total_seconds = int((now - start_dt).total_seconds())
    duration_str = format_duration(total_seconds)

    data[user_id]["activities"][active_index]["end_time"] = current_time
    data[user_id]["activities"][active_index]["end_timestamp"] = now.isoformat()
    data[user_id]["activities"][active_index]["duration"] = total_seconds

    activity_type = active["type"]
    icons = {"Washroom": "🚻", "Smoke": "🚬", "Break": "☕"}
    icon = icons.get(activity_type, "📌")

        late_message = ""
    if activity_type == "Break":
        deadline_dt = datetime.fromisoformat(active["deadline_timestamp"])
        if now > deadline_dt:
            late_str = format_duration(int((now - deadline_dt).total_seconds()))
            late_message = f"\n\n❗🔴 *LATE BY:  {late_str}* 🔴❗\n(Max allowed: 1 Hour)"
            data[user_id]["activities"][active_index]["is_late"] = True
        else:
            late_message = "\n\n📌 Status:  *ON TIME* ✅"
            data[user_id]["activities"][active_index]["is_late"] = False
    elif activity_type == "Washroom":
        max_seconds = 10 * 60  # 10 minutes
        if total_seconds > max_seconds:
            extra_seconds = total_seconds - max_seconds
            late_str = format_duration(extra_seconds)
            late_message = f"\n\n❗🔴 *LATE BY:  {late_str}* 🔴❗\n(Max allowed: 10 min)"
            data[user_id]["activities"][active_index]["is_late"] = True
        else:
            late_message = "\n\n📌 Status:  *ON TIME* ✅"
            data[user_id]["activities"][active_index]["is_late"] = False
    elif activity_type == "Smoke":
        max_seconds = 6 * 60  # 6 minutes
        if total_seconds > max_seconds:
            extra_seconds = total_seconds - max_seconds
            late_str = format_duration(extra_seconds)
            late_message = f"\n\n❗🔴 *LATE BY:  {late_str}* 🔴❗\n(Max allowed: 6 min)"
            data[user_id]["activities"][active_index]["is_late"] = True
        else:
            late_message = "\n\n📌 Status:  *ON TIME* ✅"
            data[user_id]["activities"][active_index]["is_late"] = False

    save_data(data)
    message = (
        f"💺 *BACK TO SEAT*\n\n👤 User:  {username}\n\n📅 Date:  *{current_date}*\n\n"
        f"⏰ Return Time:  *{current_time}*\n\n{icon} Activity:  *{activity_type}*\n\n"
        f"⏰ Gone At:  *{active['start_time']}*\n\n⏰ Back At:  *{current_time}*\n\n"
        f"⏳ Time Spent:  *{duration_str}*{late_message}\n\n✅ *Welcome back to work!*"
    )
    await update.message.reply_text(text=message, parse_mode="Markdown", reply_markup=get_main_menu())

async def handle_off_work(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    username = f"@{user.username}" if user.username else user.first_name
    user_id = str(user.id)
    now = get_now()
    current_time = now.strftime("%I:%M:%S %p")
    current_date = now.strftime("%Y-%m-%d")
    day_name = now.strftime("%A")
    data = load_data()

    if not check_work_started(data, user_id, current_date):
        await update.message.reply_text(
            f"⚠️ *ACTION DENIED!*\n\n👤 User:  {username}\n\n❌ You have *not started work yet!*\n\n"
            f"🔔 Please press  *🟢 Start Work*  first.",
            parse_mode="Markdown", reply_markup=get_main_menu()
        )
        return

    today_attendance = None
    for r in data[user_id]["attendance"]:
        if r["date"] == current_date:
            today_attendance = r
            break

    off_time = now.replace(hour=21, minute=30, second=0, microsecond=0)
    off_status = ""
    if now < off_time:
        early_str = format_duration(int((off_time - now).total_seconds()))
        off_status = (
            f"\n\n❗🔴 *EARLY LEAVE* 🔴❗\n\n⏰ Off Work Time:  *09:30:00 PM*\n\n"
            f"⏰ You Left At:  *{current_time}*\n\n⏳ Early By:  *{early_str}*"
        )
    elif now > off_time:
        over_str = format_duration(int((now - off_time).total_seconds()))
        off_status = (
            f"\n\n⏰ *OVERTIME*\n\n⏰ Off Work Time:  *09:30:00 PM*\n\n"
            f"⏰ You Left At:  *{current_time}*\n\n⏳ Overtime:  *{over_str}*"
        )
    else:
        off_status = f"\n\n📌 Status:  *ON TIME* ✅"

    for i, r in enumerate(data[user_id]["attendance"]):
        if r["date"] == current_date:
            data[user_id]["attendance"][i]["end_time"] = current_time
            data[user_id]["attendance"][i]["end_timestamp"] = now.isoformat()
            break

    today_activities = [a for a in data[user_id].get("activities", []) if a["date"] == current_date and a.get("end_time") is not None]
    washroom_list = [a for a in today_activities if a["type"] == "Washroom"]
    smoke_list = [a for a in today_activities if a["type"] == "Smoke"]
    break_list = [a for a in today_activities if a["type"] == "Break"]

    def format_activity_list(activities):
        text = ""
        for i, a in enumerate(activities):
            dur_str = format_duration(a.get("duration", 0))
            text += f"   {i+1}.  *{a['start_time']}*  -  *{a['end_time']}*  ({dur_str})\n"
        return text

    total_washroom = sum(a.get("duration", 0) for a in washroom_list)
    total_smoke = sum(a.get("duration", 0) for a in smoke_list)
    total_break = sum(a.get("duration", 0) for a in break_list)
    total_free = total_washroom + total_smoke + total_break

    start_dt = datetime.fromisoformat(today_attendance["start_timestamp"])
    total_shift = int((now - start_dt).total_seconds())
    on_desk = total_shift - total_free

    if washroom_list:
        washroom_text = f"🚻 *Washroom Breaks:*  {len(washroom_list)} times\n\n" + format_activity_list(washroom_list) + f"\n   ⏳ Total Washroom Time:  *{format_duration(total_washroom)}*"
    else:
        washroom_text = f"🚻 *Washroom Breaks:*  0 times"

    if smoke_list:
        smoke_text = f"🚬 *Smoke Breaks:*  {len(smoke_list)} times\n\n" + format_activity_list(smoke_list) + f"\n   ⏳ Total Smoke Time:  *{format_duration(total_smoke)}*"
    else:
        smoke_text = f"🚬 *Smoke Breaks:*  0 times"

    if break_list:
        break_status = "LATE ❗" if break_list[0].get("is_late", False) else "ON TIME ✅"
        break_text = f"☕ *Break:*  *{break_list[0]['start_time']}*  -  *{break_list[0]['end_time']}*\n\n   ⏳ Total Break Time:  *{format_duration(total_break)}*\n\n   📌 Status:  *{break_status}*"
    else:
        break_text = f"☕ *Break:*  Not taken"

    save_data(data)
    monthly_text = get_monthly_stats_text(data[user_id], now)

    message = (
        f"🔴 *OFF WORK - DAY COMPLETE*\n\n👤 User:  {username}\n\n"
        f"📅 Date:  *{current_date}*  ({day_name})\n\n⏰ Work Started:  *{today_attendance['start_time']}*\n\n"
        f"⏰ Work Ended:  *{current_time}*\n\n📌 Start Status:  *{today_attendance['status']}*"
        f"{off_status}\n\n━━━━━━━━━━━━━━━━━━\n\n📊 *FULL DAY PROGRESS REPORT*\n\n"
        f"━━━━━━━━━━━━━━━━━━\n\n{washroom_text}\n\n{smoke_text}\n\n{break_text}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n\n📈 *DAY SUMMARY*\n\n━━━━━━━━━━━━━━━━━━\n\n"
        f"⏰ Total Shift Time:  *{format_duration(total_shift)}*\n\n"
        f"💺 On Desk Duty:  *{format_duration(on_desk)}*\n\n"
        f"🚻 Washroom Time:  *{format_duration(total_washroom)}*\n\n"
        f"🚬 Smoke Time:  *{format_duration(total_smoke)}*\n\n"
        f"☕ Break Time:  *{format_duration(total_break)}*\n\n"
        f"⏳ Total Free Time:  *{format_duration(total_free)}*\n\n"
        f"━━━━━━━━━━━━━━━━━━\n\n{monthly_text}"
    )
    await update.message.reply_text(text=message, parse_mode="Markdown", reply_markup=get_main_menu())

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🟢 Start Work":
        await handle_start_work(update, context)
    elif text == "🚻 Washroom":
        await handle_washroom(update, context)
    elif text == "🚬 Smoke":
        await handle_smoke(update, context)
    elif text == "☕ Break":
        await handle_break(update, context)
    elif text == "💺 Back to Seat":
        await handle_back_to_seat(update, context)
    elif text == "🔴 Off Work":
        await handle_off_work(update, context)

async def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    print("✅ Bot is running...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    
    # Keep running
    import asyncio
    await asyncio.Event().wait()

if __name__ == "__main__":
    keep_alive()
    import asyncio
    asyncio.run(main())
if __name__ == "__main__":
    main()
