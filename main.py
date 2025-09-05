import sqlite3
import pytz
from datetime import datetime, timedelta, date, time
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext, JobQueue

BOT_TOKEN = input()

# Initialize main database with groups list
def init_groups_db():
    print("[DEBUG] Initializing groups database")
    conn = sqlite3.connect('groups.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS groups (
            chat_id INTEGER PRIMARY KEY
        )
    ''')
    conn.commit()
    conn.close()
    print("[DEBUG] Groups database initialized")

# Initialize database for specific group
def init_group_db(chat_id):
    db_name = f'birthdays_{chat_id}.db'
    print(f"[DEBUG] Initializing group database: {db_name}")
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            birthday TEXT  -- Format YYYY-MM-DD
        )
    ''')
    conn.commit()
    conn.close()
    print(f"[DEBUG] Group database {db_name} initialized")

# Add group into main database, if it doesn't exist
def add_group_if_not_exists(chat_id):
    print(f"[DEBUG] Checking if group {chat_id} exists in groups.db")
    conn = sqlite3.connect('groups.db')
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM groups WHERE chat_id = ?', (chat_id,))
    result = cursor.fetchone()
    print(f"[DEBUG] Group {chat_id} exists: {result is not None}")
    if not result:
        print(f"[DEBUG] Adding group {chat_id} to groups.db")
        cursor.execute('INSERT INTO groups (chat_id) VALUES (?)', (chat_id,))
        conn.commit()
        init_group_db(chat_id)
    conn.close()

# Add birthday: reply to user's message and /add_birthday dd.mm.yyyy
async def add_birthday(update: Update, context: CallbackContext):
    chat_id = update.message.chat.id
    print(f"[DEBUG] /add_birthday called in chat {chat_id}")
    if update.message.chat.type not in ['group', 'supergroup']:
        print(f"[DEBUG] Command used in non-group chat: {update.message.chat.type}")
        await update.message.reply_text('Эта команда работает только в группах.')
        return

    if not update.message.reply_to_message:
        print("[DEBUG] No reply-to message provided")
        await update.message.reply_text('Ответьте на сообщение пользователя и используйте: /add_birthday дд.мм.гггг')
        return

    if len(context.args) != 1:
        print(f"[DEBUG] Invalid number of arguments: {context.args}")
        await update.message.reply_text('Использование: /add_birthday дд.мм.гггг (в ответ на сообщение пользователя)')
        return

    # Get user from reply
    user = update.message.reply_to_message.from_user
    user_id = user.id
    username = user.username if user.username else f"user_{user_id}"
    print(f"[DEBUG] Processing birthday for user_id: {user_id}, username: {username}")

    birthday_str = context.args[0]
    print(f"[DEBUG] Provided birthday string: {birthday_str}")

    try:
        # Convert dd.mm.yyyy to YYYY-MM-DD
        bd_date = datetime.strptime(birthday_str, '%d.%m.%Y')
        birthday = bd_date.strftime('%Y-%m-%d')
        print(f"[DEBUG] Parsed birthday: {birthday}")
    except ValueError as e:
        print(f"[DEBUG] Invalid date format: {birthday_str}, error: {e}")
        await update.message.reply_text('Неверный формат: дд.мм.гггг')
        return

    # Check if user is in group
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        print(f"[DEBUG] Chat member status for user {user_id}: {member.status}")
        if member.status in ['left', 'kicked']:
            print(f"[DEBUG] User {user_id} is not in group (status: {member.status})")
            await update.message.reply_text('Пользователь не состоит в этой группе.')
            return
    except Exception as e:
        print(f"[DEBUG] Error checking chat member status: {e}")
        await update.message.reply_text('Не удалось подтвердить наличие пользователя в группе.')
        return

    # Add group if not exists
    add_group_if_not_exists(chat_id)

    # Add to DB
    db_name = f'birthdays_{chat_id}.db'
    print(f"[DEBUG] Adding birthday to database: {db_name}")
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute('REPLACE INTO users (user_id, username, birthday) VALUES (?, ?, ?)', (user_id, username, birthday))
    conn.commit()
    cursor.execute('SELECT user_id, username, birthday FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    print(f"[DEBUG] Database entry after adding: {result}")
    conn.close()

    await update.message.reply_text(f'Добавлен день рождения для @{username}: {birthday_str}')

# Remove birthday: reply to user's message and /remove_birthday
async def remove_birthday(update: Update, context: CallbackContext):
    chat_id = update.message.chat.id
    print(f"[DEBUG] /remove_birthday called in chat {chat_id}")
    if update.message.chat.type not in ['group', 'supergroup']:
        print(f"[DEBUG] Command used in non-group chat: {update.message.chat.type}")
        await update.message.reply_text('Эта команда работает только в группах.')
        return

    if not update.message.reply_to_message:
        print("[DEBUG] No reply-to message provided")
        await update.message.reply_text('Ответьте на сообщение пользователя и используйте: /remove_birthday')
        return

    # Get user from reply
    user = update.message.reply_to_message.from_user
    user_id = user.id
    print(f"[DEBUG] Removing birthday for user_id: {user_id}")

    # Check if group exists
    add_group_if_not_exists(chat_id)

    # Remove from DB
    db_name = f'birthdays_{chat_id}.db'
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
    conn.commit()
    print(f"[DEBUG] Rows affected by deletion: {cursor.rowcount}")
    conn.close()

    username = user.username if user.username else f"user_{user_id}"
    if cursor.rowcount > 0:
        await update.message.reply_text(f'Удалён день рождения для @{username}')
    else:
        await update.message.reply_text(f'День рождения для @{username} не найден.')

# List birthdays: /list_birthdays
async def list_birthdays(update: Update, context: CallbackContext):
    chat_id = update.message.chat.id
    print(f"[DEBUG] /list_birthdays called in chat {chat_id}")
    if update.message.chat.type not in ['group', 'supergroup']:
        print(f"[DEBUG] Command used in non-group chat: {update.message.chat.type}")
        await update.message.reply_text('Эта команда работает только в группах.')
        return

    add_group_if_not_exists(chat_id)

    db_name = f'birthdays_{chat_id}.db'
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute('SELECT username, birthday FROM users')
    users = cursor.fetchall()
    conn.close()
    print(f"[DEBUG] Retrieved {len(users)} birthdays from {db_name}: {users}")

    if not users:
        await update.message.reply_text('Нет добавленных дней рождения в этой группе.')
        return

    message = 'Список дней рождения:\n'
    for username, birthday in users:
        bd_date = datetime.strptime(birthday, '%Y-%m-%d')
        display_date = bd_date.strftime('%d.%m.%Y')
        message += f'@{username}: {display_date}\n'

    await update.message.reply_text(message)

# Current time: /current_time
async def current_time(update: Update, context: CallbackContext):
    now = datetime.now()
    print(f"[DEBUG] /current_time called, current time: {now}")
    await update.message.reply_text(f'Текущее время бота: {now.strftime("%Y-%m-%d %H:%M:%S")} (локальное время сервера)')

# Daily check for all groups
async def daily_check(context: CallbackContext):
    now = datetime.now()
    today = now.date()
    print(f"[DEBUG] Running daily_check at {now} (today: {today})")

    # Get group list
    conn = sqlite3.connect('groups.db')
    cursor = conn.cursor()
    cursor.execute('SELECT chat_id FROM groups')
    groups = cursor.fetchall()
    conn.close()
    print(f"[DEBUG] Found {len(groups)} groups: {groups}")

    for (chat_id,) in groups:
        print(f"[DEBUG] Processing group: {chat_id}")
        db_name = f'birthdays_{chat_id}.db'
        conn = sqlite3.connect(db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, username, birthday FROM users')
        users = cursor.fetchall()
        conn.close()
        print(f"[DEBUG] Found {len(users)} users in group {chat_id}: {users}")

        for user_id, username, birthday_str in users:
            print(f"[DEBUG] Checking user {username} (user_id: {user_id}) with birthday {birthday_str}")
            try:
                birthday = datetime.strptime(birthday_str, '%Y-%m-%d').date()
                bd_month = birthday.month
                bd_day = birthday.day
                print(f"[DEBUG] Birthday month: {bd_month}, day: {bd_day}")

                # Calculate current_bd (nearest future or today) and previous_bd
                bd_this_year = date(today.year, bd_month, bd_day)
                if bd_this_year >= today:
                    current_bd = bd_this_year
                    previous_bd = date(today.year - 1, bd_month, bd_day)
                else:
                    current_bd = date(today.year + 1, bd_month, bd_day)
                    previous_bd = bd_this_year

                days_to_current = (current_bd - today).days
                days_since_previous = (today - previous_bd).days
                print(f"[DEBUG] For {username}: current_bd={current_bd}, previous_bd={previous_bd}, "
                      f"days_to_current={days_to_current}, days_since_previous={days_since_previous}")

                if days_to_current == 1:  # The day before: kick and notification
                    print(f"[DEBUG] Tomorrow is {username}'s birthday, attempting to ban")
                    try:
                        await context.bot.ban_chat_member(chat_id, user_id)
                        await context.bot.send_message(chat_id, f'У @{username} завтра день рождения! 🎉')
                        print(f"[DEBUG] Successfully banned {username} and sent message")
                    except Exception as e:
                        print(f"[ERROR] Failed to ban or send message for {username} in group {chat_id}: {e}")

                elif days_to_current == 0:  # On birthday: notification
                    print(f"[DEBUG] Today is {username}'s birthday, sending notification")
                    try:
                        await context.bot.send_message(chat_id, f'Сегодня у @{username} день рождения! 🥳')
                        print(f"[DEBUG] Successfully sent birthday message for {username}")
                    except Exception as e:
                        print(f"[ERROR] Failed to send birthday message for {username} in group {chat_id}: {e}")

                if days_since_previous == 1:  # A day after birthday: unban and send invite link
                    print(f"[DEBUG] One day after {username}'s birthday, attempting to unban")
                    try:
                        # Unban the user first
                        await context.bot.unban_chat_member(chat_id, user_id)
                        print(f"[DEBUG] Successfully unbanned {username}")

                        # Generate and send invite link (group is private)
                        print(f"[DEBUG] Generating invite link for {username}")
                        try:
                            invite_link = await context.bot.export_chat_invite_link(chat_id)
                            await context.bot.send_message(user_id, f'Приглашение обратно в группу: {invite_link}')
                            print(f"[DEBUG] Sent invite link to {username}: {invite_link}")
                        except Exception as e:
                            print(f"[ERROR] Failed to generate or send invite link for {username}: {e}")
                            await context.bot.send_message(chat_id, f'Не удалось отправить приглашение @{username}. Пожалуйста, свяжитесь с ним вручную.')
                            print(f"[DEBUG] Notified group about failed invite link for {username}")

                        # Notify group of user's return
                        await context.bot.send_message(chat_id, f'Пользователю @{username} отправлена ссылка-приглашение! 😎')
                        print(f"[DEBUG] Successfully sent return message for {username}")
                    except Exception as e:
                        print(f"[ERROR] Failed to unban or send message for {username} in group {chat_id}: {e}")
            except Exception as e:
                print(f"[ERROR] Error processing birthday for {username} in group {chat_id}: {e}")

def main():
    print("[DEBUG] Starting bot")
    init_groups_db()
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler('add_birthday', add_birthday))
    application.add_handler(CommandHandler('remove_birthday', remove_birthday))
    application.add_handler(CommandHandler('list_birthdays', list_birthdays))
    application.add_handler(CommandHandler('current_time', current_time))

    job_queue = application.job_queue
    print("[DEBUG] Job queue initialized")

    # Set time zone to MSK (Europe/Moscow)
    msk_tz = pytz.timezone('Europe/Moscow')
    job_time = time(hour=9, minute=0, tzinfo=msk_tz)
    print(f"[DEBUG] Scheduling daily_check job at 09:00 MSK (timezone: {msk_tz})")
    job_queue.run_daily(daily_check, time=job_time, days=(0, 1, 2, 3, 4, 5, 6))

    print("[DEBUG] Starting polling")
    application.run_polling()

if __name__ == '__main__':
    main()
