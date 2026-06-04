import json
import os
import calendar
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import pytz
from keep_alive import keep_alive

# ============ SETTINGS ============
BOT_TOKEN = "8810391523:AAFYaOzSOhPMCpdmhufVSq_H9pE_IMH83WU"
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
    year = now.year
    month = now.month
    return calendar.monthrange(year, month)[1]

def get_monthly_stats(user_data, now):
    current_month = now.strftime("%Y-%m")
    monthly_records = [
        r for r in user_data.get("attendance", [])
        if r["date"].startswith(current_month)
    ]
    present_days = len(monthly_records)
    late_days = len([r for r in monthly_records if r.get("is_late", False)])

    # Total days in month
    total_days = get_total_days_in_month(now)

    # Days passed so far in this month (including today)
    days_passed = now.day

    # Off days = past days where user didn't start work
    off_days = days_passed - present_days
    if off_days < 0:
        off_days = 0

    return {
        "total_days": total_days,
        "present_days": present_days,
        "late_days": late_days,
        "off_days": off_days
    }

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

# ============ MAIN MENU (Bottom Keyboard) ============
def get_main_menu():
    keyboard = [
        [KeyboardButton("🟢 Start Work"), KeyboardButton("🚻 Washroom")],
        [KeyboardButton("🚬 Smoke"), KeyboardButton("☕ Break")],
        [KeyboardButton("💺 Back to Seat"), KeyboardButton("🔴 Off Work")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ============ /start COMMAND ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏢 *EMPLOYEE ATTENDANCE SYSTEM*\n\n"
        "👋 Welcome! Please select an action from the buttons below.",
        reply_markup=get_main_menu(),
        parse_mode="Markdown"
    )

# ============ START WORK ============
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
        data[user_id] = {
            "username": username,
            "attendance": [],
            "activities": []
        }

    # Check if already started work today
    today_records = [
        r for r in data[user_id]["attendance"]
        if r["date"] == current_date
    ]

    if today_records:
        message = (
            f"⚠️ *ALREADY AT WORK!*\n\n"
            f"👤 User:  {username}\n\n"
            f"❌ You are *already in work!*\n\n"
            f"📅 Date:  *{current_date}*\n\n"
            f"⏰ Started At:  *{today_records[0]['start_time']}*\n\n"
            f"🔔 Please press  *🔴 Off Work*  first to end your shift."
        )
        await update.message.reply_text(
            message,
            parse_mode="Markdown",
            reply_markup=get_main_menu()
        )
        return

    is_late = now > scheduled_time
    late_message = ""

    if is_late:
        late_duration = now - scheduled_time
        total_seconds = int(late_duration.total_seconds())
        late_time_str = format_duration(total_seconds)

        late_message = (
            f"\n\n❗🔴 *LATE ARRIVAL* 🔴❗\n\n"
            f"⏰ Scheduled Time:  *{scheduled_str}*\n\n"
            f"⏰ Arrival Time:  *{current_time}*\n\n"
            f"⏳ Late By:  *{late_time_str}*"
        )
        status = "LATE ❗"
    else:
        status = "ON TIME ✅"

    attendance_record = {
        "date": current_date,
        "day": day_name,
        "start_time": current_time,
        "start_timestamp": now.isoformat(),
        "status": status,
        "is_late": is_late,
        "shift_type": shift_type,
        "end_time": None,
        "end_timestamp": None
    }

    data[user_id]["attendance"].append(attendance_record)
    save_data(data)

    monthly_text = get_monthly_stats_text(data[user_id], now)

    message = (
        f"🟢 *WORK STARTED* 🟢\n\n"
        f"👤 User:  {username}\n\n"
        f"📅 Date:  *{current_date}*  ({day_name})\n\n"
        f"⏰ Time:  *{current_time}*\n\n"
        f"📌 Shift:  *{shift_type}*\n\n"
        f"📌 Status:  *{status}*"
        f"{late_message}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"{monthly_text}"
    )

    await update.message.reply_text(
        text=message,
        parse_mode="Markdown",
        reply_markup=get_main_menu()
    )

# ============ CHECK WORK STARTED ============
def check_work_started(data, user_id, current_date):
    if user_id not in data:
        return False
    today_records = [
        r for r in data[user_id].get("attendance", [])
        if r["date"] == current_date
    ]
    return len(today_records) > 0

# ============ WASHROOM ============
async def handle_washroom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    username = f"@{user.username}" if user.username else user.first_name
    user_id = str(user.id)

    now = get_now()
    current_time = now.strftime("%I:%M:%S %p")
    current_date = now.strftime("%Y-%m-%d")

    data = load_data()

    # Check if work started
    if not check_work_started(data, user_id, current_date):
        await update.message.reply_text(
            f"⚠️ *ACTION DENIED!*\n\n"
            f"👤 User:  {username}\n\n"
            f"❌ You have *not started work yet!*\n\n"
            f"🔔 Please press  *🟢 Start Work*  first.",
            parse_mode="Markdown",
            reply_markup=get_main_menu()
        )
        return

    # Check if already on activity
    active = [
        a for a in data[user_id].get("activities", [])
        if a["date"] == current_date and a.get("end_time") is None
    ]

    if active:
        await update.message.reply_text(
            f"⚠️ *ACTION DENIED!*\n\n"
            f"👤 User:  {username}\n\n"
            f"❌ You are *already engaged in {active[0]['type']}* activity!\n\n"
            f"🔔 Please press  *💺 Back to Seat*  first.",
            parse_mode="Markdown",
            reply_markup=get_main_menu()
        )
        return

    activity = {
        "date": current_date,
        "type": "Washroom",
        "start_time": current_time,
        "start_timestamp": now.isoformat(),
        "end_time": None,
        "end_timestamp": None,
        "duration": None
    }

    if "activities" not in data[user_id]:
        data[user_id]["activities"] = []

    data[user_id]["activities"].append(activity)
    save_data(data)

    message = (
        f"🚻 *WASHROOM BREAK*\n\n"
        f"👤 User:  {username}\n\n"
        f"📅 Date:  *{current_date}*\n\n"
        f"⏰ Time:  *{current_time}*\n\n"
        f"✅ Washroom break  *registered!*\n\n"
        f"🔓 You have *permission to go.*\n\n"
        f"🔔 Please press  *💺 Back to Seat*  when you return."
    )

    await update.message.reply_text(
        text=message,
        parse_mode="Markdown",
        reply_markup=get_main_menu()
    )

# ============ SMOKE ============
async def handle_smoke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    username = f"@{user.username}" if user.username else user.first_name
    user_id = str(user.id)

    now = get_now()
    current_time = now.strftime("%I:%M:%S %p")
    current_date = now.strftime("%Y-%m-%d")

    data = load_data()

    if not check_work_started(data, user_id, current_date):
        await update.message.reply_text(
            f"⚠️ *ACTION DENIED!*\n\n"
            f"👤 User:  {username}\n\n"
            f"❌ You have *not started work yet!*\n\n"
            f"🔔 Please press  *🟢 Start Work*  first.",
            parse_mode="Markdown",
            reply_markup=get_main_menu()
        )
        return

    active = [
        a for a in data[user_id].get("activities", [])
        if a["date"] == current_date and a.get("end_time") is None
    ]

    if active:
        await update.message.reply_text(
            f"⚠️ *ACTION DENIED!*\n\n"
            f"👤 User:  {username}\n\n"
            f"❌ You are *already engaged in {active[0]['type']}* activity!\n\n"
            f"🔔 Please press  *💺 Back to Seat*  first.",
            parse_mode="Markdown",
            reply_markup=get_main_menu()
        )
        return

    activity = {
        "date": current_date,
        "type": "Smoke",
        "start_time": current_time,
        "start_timestamp": now.isoformat(),
        "end_time": None,
        "end_timestamp": None,
        "duration": None
    }

    if "activities" not in data[user_id]:
        data[user_id]["activities"] = []

    data[user_id]["activities"].append(activity)
    save_data(data)

    message = (
        f"🚬 *SMOKE BREAK*\n\n"
        f"👤 User:  {username}\n\n"
        f"📅 Date:  *{current_date}*\n\n"
        f"⏰ Time:  *{current_time}*\n\n"
        f"✅ Smoke break  *registered!*\n\n"
        f"🔓 You have *permission to go.*\n\n"
        f"🔔 Please press  *💺 Back to Seat*  when you return."
    )

    await update.message.reply_text(
        text=message,
        parse_mode="Markdown",
        reply_markup=get_main_menu()
    )

# ============ BREAK ============
async def handle_break(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    username = f"@{user.username}" if user.username else user.first_name
    user_id = str(user.id)

    now = get_now()
    current_time = now.strftime("%I:%M:%S %p")
    current_date = now.strftime("%Y-%m-%d")

    data = load_data()

    if not check_work_started(data, user_id, current_date):
        await update.message.reply_text(
            f"⚠️ *ACTION DENIED!*\n\n"
            f"👤 User:  {username}\n\n"
            f"❌ You have *not started work yet!*\n\n"
            f"🔔 Please press  *🟢 Start Work*  first.",
            parse_mode="Markdown",
            reply_markup=get_main_menu()
        )
        return

    active = [
        a for a in data[user_id].get("activities", [])
        if a["date"] == current_date and a.get("end_time") is None
    ]

    if active:
        await update.message.reply_text(
            f"⚠️ *ACTION DENIED!*\n\n"
            f"👤 User:  {username}\n\n"
            f"❌ You are *already engaged in {active[0]['type']}* activity!\n\n"
            f"🔔 Please press  *💺 Back to Seat*  first.",
            parse_mode="Markdown",
            reply_markup=get_main_menu()
        )
        return

    deadline = now.replace(hour=15, minute=0, second=0, microsecond=0)
    deadline_str = "03:00:00 PM"

    activity = {
        "date": current_date,
        "type": "Break",
        "start_time": current_time,
        "start_timestamp": now.isoformat(),
        "end_time": None,
        "end_timestamp": None,
        "duration": None,
        "deadline": deadline_str,
        "deadline_timestamp": deadline.isoformat()
    }

    if "activities" not in data[user_id]:
        data[user_id]["activities"] = []

    data[user_id]["activities"].append(activity)
    save_data(data)

    message = (
        f"☕ *BREAK STARTED*\n\n"
        f"👤 User:  {username}\n\n"
        f"📅 Date:  *{current_date}*\n\n"
        f"⏰ Break Start:  *{current_time}*\n\n"
        f"⏳ Break Duration:  *1 Hour*\n\n"
        f"⏰ You must be back by:  *{deadline_str}*\n\n"
        f"🔔 Please press  *💺 Back to Seat*  when you return."
    )

    await update.message.reply_text(
        text=message,
        parse_mode="Markdown",
        reply_markup=get_main_menu()
    )

# ============ BACK TO SEAT ============
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
            f"⚠️ *ACTION DENIED!*\n\n"
            f"👤 User:  {username}\n\n"
            f"❌ You have *not started work yet!*\n\n"
            f"🔔 Please press  *🟢 Start Work*  first.",
            parse_mode="Markdown",
            reply_markup=get_main_menu()
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
            f"⚠️ *ACTION DENIED!*\n\n"
            f"👤 User:  {username}\n\n"
            f"❌ You are *not engaged in any activity!*\n\n"
            f"🔔 No active  *Washroom / Smoke / Break*  found.",
            parse_mode="Markdown",
            reply_markup=get_main_menu()
        )
        return

    start_dt = datetime.fromisoformat(active["start_timestamp"])
    duration = now - start_dt
    total_seconds = int(duration.total_seconds())
    duration_str = format_duration(total_seconds)

    data[user_id]["activities"][active_index]["end_time"] = current_time
    data[user_id]["activities"][active_index]["end_timestamp"] = now.isoformat()
    data[user_id]["activities"][active_index]["duration"] = total_seconds

    activity_type = active["type"]
    if activity_type == "Washroom":
        icon = "🚻"
    elif activity_type == "Smoke":
        icon = "🚬"
    elif activity_type == "Break":
        icon = "☕"
    else:
        icon = "📌"

    late_message = ""
    if activity_type == "Break":
        deadline_dt = datetime.fromisoformat(active["deadline_timestamp"])
        if now > deadline_dt:
            late_dur = now - deadline_dt
            late_total = int(late_dur.total_seconds())
            late_str = format_duration(late_total)
            late_message = f"\n\n❗🔴 *LATE BY:  {late_str}* 🔴❗"
            data[user_id]["activities"][active_index]["is_late"] = True
        else:
            late_message = "\n\n📌 Status:  *ON TIME* ✅"
            data[user_id]["activities"][active_index]["is_late"] = False

    save_data(data)

    message = (
        f"💺 *BACK TO SEAT*\n\n"
        f"👤 User:  {username}\n\n"
        f"📅 Date:  *{current_date}*\n\n"
        f"⏰ Return Time:  *{current_time}*\n\n"
        f"{icon} Activity:  *{activity_type}*\n\n"
        f"⏰ Gone At:  *{active['start_time']}*\n\n"
        f"⏰ Back At:  *{current_time}*\n\n"
        f"⏳ Time Spent:  *{duration_str}*"
        f"{late_message}\n\n"
        f"✅ *Welcome back to work!*"
    )

    await update.message.reply_text(
        text=message,
        parse_mode="Markdown",
        reply_markup=get_main_menu()
    )

# ============ OFF WORK ============
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
            f"⚠️ *ACTION DENIED!*\n\n"
            f"👤 User:  {username}\n\n"
            f"❌ You have *not started work yet!*\n\n"
            f"🔔 Please press  *🟢 Start Work*  first.",
            parse_mode="Markdown",
            reply_markup=get_main_menu()
        )
        return

    today_attendance = None
    for i, r in enumerate(data[user_id]["attendance"]):
        if r["date"] == current_date:
            today_attendance = r
            break

    off_time = now.replace(hour=21, minute=30, second=0, microsecond=0)
    off_time_str = "09:30:00 PM"

    off_status = ""
    if now < off_time:
        early_dur = off_time - now
        early_total = int(early_dur.total_seconds())
        early_str = format_duration(early_total)
        off_status = (
            f"\n\n❗🔴 *EARLY LEAVE* 🔴❗\n\n"
            f"⏰ Off Work Time:  *{off_time_str}*\n\n"
            f"⏰ You Left At:  *{current_time}*\n\n"
            f"⏳ Early By:  *{early_str}*"
        )
    elif now > off_time:
        over_dur = now - off_time
        over_total = int(over_dur.total_seconds())
        over_str = format_duration(over_total)
        off_status = (
            f"\n\n⏰ *OVERTIME*\n\n"
            f"⏰ Off Work Time:  *{off_time_str}*\n\n"
            f"⏰ You Left At:  *{current_time}*\n\n"
            f"⏳ Overtime:  *{over_str}*"
        )
    else:
        off_status = f"\n\n📌 Status:  *ON TIME* ✅"

    for i, r in enumerate(data[user_id]["attendance"]):
        if r["date"] == current_date:
            data[user_id]["attendance"][i]["end_time"] = current_time
            data[user_id]["attendance"][i]["end_timestamp"] = now.isoformat()
            break

    today_activities = [
        a for a in data[user_id].get("activities", [])
        if a["date"] == current_date and a.get("end_time") is not None
    ]

    washroom_list = [a for a in today_activities if a["type"] == "Washroom"]
    smoke_list = [a for a in today_activities if a["type"] == "Smoke"]
    break_list = [a for a in today_activities if a["type"] == "Break"]

    def format_activity_list(activities):
        text = ""
        for i, a in enumerate(activities):
            dur = a.get("duration", 0)
            dur_str = format_duration(dur)
            text += f"   {i+1}.  *{a['start_time']}*  -  *{a['end_time']}*  ({dur_str})\n"
        return text

    total_washroom = sum(a.get("duration", 0) for a in washroom_list)
    total_smoke = sum(a.get("duration", 0) for a in smoke_list)
    total_break = sum(a.get("duration", 0) for a in break_list)
    total_free = total_washroom + total_smoke + total_break

    start_dt = datetime.fromisoformat(today_attendance["start_timestamp"])
    total_shift = int((now - start_dt).total_seconds())
    on_desk = total_shift - total_free

    washroom_text = ""
    if washroom_list:
        washroom_text = f"🚻 *Washroom Breaks:*  {len(washroom_list)} times\n\n"
        washroom_text += format_activity_list(washroom_list)
        washroom_text += f"\n   ⏳ Total Washroom Time:  *{format_duration(total_washroom)}*"
    else:
        washroom_text = f"🚻 *Washroom Breaks:*  0 times"

    smoke_text = ""
    if smoke_list:
        smoke_text = f"🚬 *Smoke Breaks:*  {len(smoke_list)} times\n\n"
        smoke_text += format_activity_list(smoke_list)
        smoke_text += f"\n   ⏳ Total Smoke Time:  *{format_duration(total_smoke)}*"
    else:
        smoke_text = f"🚬 *Smoke Breaks:*  0 times"

    break_text = ""
    if break_list:
        break_late = break_list[0].get("is_late", False)
        break_status = "LATE ❗" if break_late else "ON TIME ✅"
        break_text = f"☕ *Break:*  *{break_list[0]['start_time']}*  -  *{break_list[0]['end_time']}*\n\n"
        break_text += f"   ⏳ Total Break Time:  *{format_duration(total_break)}*\n\n"
        break_text += f"   📌 Status:  *{break_status}*"
    else:
        break_text = f"☕ *Break:*  Not taken"

    save_data(data)
    monthly_text = get_monthly_stats_text(data[user_id], now)

    message = (
        f"🔴 *OFF WORK - DAY COMPLETE*\n\n"
        f"👤 User:  {username}\n\n"
        f"📅 Date:  *{current_date}*  ({day_name})\n\n"
        f"⏰ Work Started:  *{today_attendance['start_time']}*\n\n"
        f"⏰ Work Ended:  *{current_time}*\n\n"
        f"📌 Start Status:  *{today_attendance['status']}*"
        f"{off_status}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 *FULL DAY PROGRESS REPORT*\n\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"{washroom_text}\n\n"
        f"{smoke_text}\n\n"
        f"{break_text}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"📈 *DAY SUMMARY*\n\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"⏰ Total Shift Time:  *{format_duration(total_shift)}*\n\n"
        f"💺 On Desk Duty:  *{format_duration(on_desk)}*\n\n"
        f"🚻 Washroom Time:  *{format_duration(total_washroom)}*\n\n"
        f"🚬 Smoke Time:  *{format_duration(total_smoke)}*\n\n"
        f"☕ Break Time:  *{format_duration(total_break)}*\n\n"
        f"⏳ Total Free Time:  *{format_duration(total_free)}*\n\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"{monthly_text}"
    )

    await update.message.reply_text(
        text=message,
        parse_mode="Markdown",
        reply_markup=get_main_menu()
    )

# ============ MESSAGE HANDLER ============
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

# ============ MAIN ============
def main():
    keep_alive()
    
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    print("✅ Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()