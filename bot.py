import os
import telebot
from telebot import types
import subprocess
import json
import re
import ipaddress
from openai import OpenAI
from dotenv import load_dotenv

# ================= НАСТРОЙКИ =================
load_dotenv()  # Загружает переменные из .env (локально) или из окружения Render

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not BOT_TOKEN or not GEMINI_API_KEY:
    print("КРИТИЧЕСКАЯ ОШИБКА: Не заданы BOT_TOKEN или GEMINI_API_KEY в переменных окружения!")
    exit(1)

# Клиент Gemini
llm_client = OpenAI(
    api_key=GEMINI_API_KEY,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)
GEMINI_MODEL = "gemini-2.5-flash"

# Инициализация бота
bot = telebot.TeleBot(BOT_TOKEN)

# ================= ФУНКЦИИ LLM =================

def ask_llm(system_prompt: str, user_text: str) -> str:
    """Вызов Gemini через стандартный chat.completions."""
    try:
        response = llm_client.chat.completions.create(
            model=GEMINI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}
            ],
            temperature=0.3,
            max_tokens=1500
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"[Ошибка LLM: {str(e)[:200]}]"

def extract_entities(text: str) -> dict:
    """Просит LLM вытащить IP и username в JSON."""
    system = (
        "Ты — парсер данных. Извлеки из текста пользователя IP-адрес и никнейм. "
        "Верни ТОЛЬКО валидный JSON без markdown-обёрток: "
        '{"ip": "строка или null", "username": "строка или null"}. '
        "Если чего-то нет — ставь null. Не придумывай данные."
    )
    raw = ask_llm(system, text)
    clean = re.sub(r'^```json\s*|\s*```$', '', raw.strip())
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        return {"ip": None, "username": None}

# ================= ФУНКЦИИ OSINT =================

def is_valid_ip(ip_str: str) -> bool:
    try:
        ipaddress.ip_address(ip_str)
        return True
    except ValueError:
        return False

def run_openosint_ip(ip: str) -> str:
    """Вызывает openosint для IP."""
    try:
        result = subprocess.run(
            ["openosint", "ip", ip, "--json"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            return result.stdout.strip()[:2500]
        return f"Ошибка openosint: {result.stderr[:500]}"
    except FileNotFoundError:
        return "openosint не установлен на сервере."
    except subprocess.TimeoutExpired:
        return "Таймаут при проверке IP."

def run_openosint_username(username: str) -> str:
    """Вызывает openosint для username. Требует --allow-active и sherlock."""
    try:
        result = subprocess.run(
            ["openosint", "--allow-active", "username", username, "--json"],
            capture_output=True, text=True, timeout=180
        )
        if result.returncode == 0:
            return result.stdout.strip()[:2500]
        return f"Ошибка openosint: {result.stderr[:500]}"
    except FileNotFoundError:
        return "openosint не установлен на сервере."
    except subprocess.TimeoutExpired:
        return "Таймаут при поиске никнейма (Sherlock может работать долго)."

# ================= КЛАВИАТУРЫ =================

def main_menu_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("📚 База знаний", callback_data="knowledge_base"),
        types.InlineKeyboardButton("🕵️ OSINT", callback_data="osint_section"),
        types.InlineKeyboardButton("💻 Open-Source", callback_data="opensource_section")
    )
    return kb

def back_keyboard(callback_data="main_menu"):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("◀️ Назад", callback_data=callback_data))
    return kb

# ================= ОБРАБОТЧИКИ =================

@bot.message_handler(commands=['start', 'help'])
def cmd_start(message):
    text = (
        "👋 *Добро пожаловать в OSINT-бота!*\n\n"
        "Я помогу вам разобраться в методах разведки по открытым источникам.\n\n"
        "Выберите раздел:"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=main_menu_keyboard())

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = call.message.chat.id
    msg_id = call.message.message_id

    if call.data == "main_menu":
        bot.edit_message_text(
            "👋 *Главное меню*\n\nВыберите раздел:",
            chat_id, msg_id, parse_mode="Markdown",
            reply_markup=main_menu_keyboard()
        )
        bot.answer_callback_query(call.id)

    elif call.data == "knowledge_base":
        text = (
            "📚 *База знаний*\n\n"
            "*1. Что такое OSINT?*\n"
            "OSINT (Open-Source Intelligence) — разведка по открытым источникам. "
            "Сбор и анализ информации из общедоступных источников: соцсетей, "
            "сайтов, госреестров, СМИ.\n\n"
            "*2. Где он используется?*\n"
            "• Кибербезопасность (аудит утечек)\n"
            "• Журналистика (расследования)\n"
            "• Бизнес-разведка\n"
            "• Правоохранительные органы (в рамках закона)\n\n"
            "*3. Принцип работы OSINT*\n"
            "Планирование → Сбор данных → Обработка и верификация → Анализ → Отчёт. "
            "Только легальные публичные источники.\n\n"
            "*4. О боте*\n"
            "Это учебный прототип на базе openosint и Google Gemini. "
            "Он демонстрирует связку «естественный язык → анализ → OSINT-инструменты».\n\n"
            "*5. Что такое Open-Source?*\n"
            "Open Source — ПО с открытым исходным кодом. Примеры: Linux, Python, "
            "sherlock, theHarvester.\n\n"
            "*6. Как пользоваться ботом?*\n"
            "Нажмите «OSINT», затем просто напишите боту запрос в свободной форме. "
            "Он сам найдёт IP или никнейм и проверит их."
        )
        bot.edit_message_text(text, chat_id, msg_id, parse_mode="Markdown",
                              reply_markup=back_keyboard())
        bot.answer_callback_query(call.id)

    elif call.data == "opensource_section":
        text = (
            "💻 *Open-Source*\n\n"
            "Open Source — модель разработки, при которой исходный код "
            "программы открыт для всех.\n\n"
            "Большинство OSINT-инструментов (sherlock, holehe, openosint) "
            "являются open-source проектами.\n\n"
            "⚠️ *Важно*: открытый код не означает вседозволенность. "
            "Используйте инструменты только в законных целях."
        )
        bot.edit_message_text(text, chat_id, msg_id, parse_mode="Markdown",
                              reply_markup=back_keyboard())
        bot.answer_callback_query(call.id)

    elif call.data == "osint_section":
        text = (
            "🕵️ *OSINT-режим*\n\n"
            "Просто напишите мне, что нужно найти, в свободной форме.\n\n"
            "*Пример:*\n"
            "«Найди информацию. Вот IP: 8.8.8.8, а никнейм: john_doe»\n\n"
            "Я сам извлеку данные, проверю их через openosint "
            "(IP — пассивно, никнейм — через Sherlock) и верну результат.\n\n"
            "⚠️ *Внимание*: запросы к Sherlock могут занимать до 2–3 минут."
        )
        bot.edit_message_text(text, chat_id, msg_id, parse_mode="Markdown",
                              reply_markup=back_keyboard())
        bot.answer_callback_query(call.id)
    else:
        bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_osint_request(message):
    user_text = message.text.strip()
    if not user_text or user_text.startswith('/'):
        return

    # 1. Извлекаем сущности через LLM
    bot.send_message(message.chat.id, "🧠 Анализирую запрос...")
    entities = extract_entities(user_text)
    ip = entities.get("ip")
    username = entities.get("username")

    findings = []

    # 2. Проверяем IP
    if ip:
        if is_valid_ip(ip):
            bot.send_message(message.chat.id, f"🔍 Проверяю IP: `{ip}`...", parse_mode="Markdown")
            ip_result = run_openosint_ip(ip)
            findings.append(f"**Результат по IP {ip}:**\n{ip_result}")
        else:
            findings.append(f"⚠️ IP `{ip}` невалиден (октеты должны быть 0–255). Пропускаю.")

    # 3. Проверяем username
    if username:
        bot.send_message(message.chat.id, f"🔍 Ищу никнейм: `{username}` (это может занять время)...", parse_mode="Markdown")
        user_result = run_openosint_username(username)
        findings.append(f"**Результат по никнейму {username}:**\n{user_result}")

    if not findings:
        bot.reply_to(message, "Не нашёл в тексте ни IP, ни никнейма. Попробуйте переформулировать.")
        return

    # 4. Отправляем сырые данные в LLM для финального ответа
    raw_data = "\n\n".join(findings)
    final_system = (
        "Ты — дружелюбный OSINT-ассистент. Пользователь просил найти информацию. "
        "Вот сырые данные от инструментов. Проанализируй их, выдели главное и ответь "
        "пользователю связным текстом на русском. Если данных нет или они невалидны — так и скажи. "
        "Не выдумывай факты, которых нет в сырых данных."
    )
    final_answer = ask_llm(final_system, f"Запрос пользователя: {user_text}\n\nСырые данные:\n{raw_data}")

    bot.reply_to(message, final_answer[:4000])

# ================= ЗАПУСК =================
if __name__ == "__main__":
    print("Бот запущен...")
    bot.infinity_polling(timeout=60)
