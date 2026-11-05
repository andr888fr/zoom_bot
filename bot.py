import os
import requests
from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import Application, MessageHandler, ContextTypes, filters
from groq import Groq
import asyncio

# Получаем токены из переменных окружения Render
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL_NAME = "qwen/qwen-2.5-72b-instruct:free"

# Инициализация клиентов
groq_client = Groq(api_key=GROQ_API_KEY)
app = Flask(__name__)

# Инициализируем бота напрямую для отправки ответов через requests или через PTB
bot = Bot(token=TOKEN)
telegram_app = Application.builder().token(TOKEN).build()

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return
        
    audio_file = message.audio or message.voice or message.document
    if not audio_file:
        await message.reply_text("Пожалуйста, отправь аудиофайл (.m4a, .mp3, .ogg) или голосовое сообщение.")
        return

    await message.reply_text("📥 Принял файл, скачиваю и отправляю на расшифровку в Groq...")

    try:
        file = await context.bot.get_file(audio_file.file_id)
        file_path = "temp_audio.m4a"
        await file.download_to_drive(file_path)

        with open(file_path, "rb") as f:
            transcription = groq_client.audio.transcriptions.create(
                file=(file_path, f.read()),
                model="whisper-large-v3",
                response_format="text"
            )
        
        if os.path.exists(file_path):
            os.remove(file_path)

        if not transcription.strip():
            await message.reply_text("❌ Не удалось распознать речь в файле.")
            return

        await message.reply_text("✍️ Расшифровка готова! Анализирую и структурирую через OpenRouter...")

        prompt = (
            "Ты профессиональный бизнес-аналитик. Проанализируй текст расшифровки созвона. "
            "Выдели ключевые моменты, задачи, договоренности и краткую суть. "
            "Структурируй ответ четко и понятно:\n\n" + transcription
        )

        response = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": MODEL_NAME,
                "messages": [{"role": "user", "content": prompt}]
            }
        )

        res_json = response.json()
        if "choices" in res_json:
            result_text = res_json["choices"][0]["message"]["content"]
            await message.reply_text(result_text)
        else:
            await message.reply_text(f"⚠️ Ошибка от OpenRouter: {res_json}")

    except Exception as e:
        await message.reply_text(f"❌ Произошла ошибка при обработке: {e}")

telegram_app.add_handler(MessageHandler(filters.ALL, handle_audio))

# Создаем глобальный event loop для обработки вебхуков без пересоздания
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
loop.run_until_complete(telegram_app.initialize())

@app.route("/")
def index():
    return "Bot is running!"

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    if request.method == "POST":
        json_data = request.get_json(force=True)
        update = Update.de_json(json_data, telegram_app.bot)
        
        # Передаем обновление в уже существующий цикл событий
        asyncio.run_coroutine_threadsafe(telegram_app.process_update(update), loop)
        
    return "OK", 200

async def setup_webhook():
    if WEBHOOK_URL:
        await telegram_app.bot.set_webhook(url=f"{WEBHOOK_URL}/{TOKEN}")

if __name__ == "__main__":
    loop.run_until_complete(setup_webhook())
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
