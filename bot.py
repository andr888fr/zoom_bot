import os
import requests
from flask import Flask, request
from telegram import Update
from telegram.ext import Application
from telegram.ext import MessageHandler, filters, ContextTypes
from groq import Groq

TOKEN = os.environ.get("9018636983:AAHMlG5up_kjfNW0cL6UrvZKMniu0nhG6Os")
GROQ_API_KEY = os.environ.get("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 ")
OPENROUTER_API_KEY = os.environ.get("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")
WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# Мощная бесплатная модель с огромным контекстом на OpenRouter
MODEL_NAME = "qwen/qwen-2.5-72b-instruct:free"

app = Flask(__name__)
telegram_app = None

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.audio or update.message.document or update.message.voice
    if not document:
        await update.message.reply_text("👋 Привет! Отправь мне файл созвона (.m4a или .mp3), и я сделаю подробный отчет.")
        return

    await update.message.reply_text("📥 Файл принят в облако! Отправляю в Groq на мгновенную расшифровку...")

    file = await context.bot.get_file(document.file_id)
    audio_path = "temp_audio.m4a"
    await file.download_to_drive(audio_path)

    try:
        # 1. Быстрая транскрипция через Groq (Whisper)
        client = Groq(api_key=GROQ_API_KEY)
        with open(audio_path, "rb") as f:
            transcript = client.audio.transcriptions.create(
                file=("audio.m4a", f.read()),
                model="whisper-large-v3-turbo",
                language="ru",
                response_format="text"
            )

        await update.message.reply_text("⚡ Текст готов! Анализирую созвон и собираю отчет без потери деталей...")

        # 2. Умный промпт для сбора информации под любые типы созвонов
        prompt = f"""
Ты — профессиональный исполнительный директор и бизнес-аналитик. Твоя задача — проанализировать расшифровку созвона и составить исчерпывающий, структурированный отчет на русском языке. 

Встречи бывают разными (информационные, стратегические, планерки с задачами, обсуждения проектов). Адаптируйся под контекст встречи, но **ни в коем случае не теряй важные детали, цифры, имена, договоренности и контекст**.

Текст расшифровки созвона:
{transcript}

Оформи отчет строго по следующей структуре (пропускай блоки, если они вообще не применимы к конкретной встрече, но старайся раскрыть всё максимально полно):

1. **📌 Главная цель и контекст встречи**
   - О чем созвон, какую задачу решали участники, каков главный итог.

2. **👥 Участники и роли (если определяются по контексту)**
   - Кто что предлагал, кто за что выступал или отчитывался.

3. **🔑 Ключевые тезисы, инсайты и факты**
   - Все важные идеи, цифры, аргументы, проблемы или технические нюансы, которые обсуждались.

4. **📋 Принятые решения и выводы**
   - К чему пришли участники, какие договоренности зафиксированы.

5. **🛠️ Задачи, поручения и дедлайны (Action Items)**
   - Четкий список: кто, что должен сделать и (если упоминалось) в какие сроки. Если задач не было, напиши «Задачи в рамках созвона не ставились».

6. **⚠️ Открытые вопросы и риски**
   - Что осталось нерешенным, какие вопросы перенесены на следующий раз.

Пиши структурированно, профессионально, используя списки и выделения жирным шрифтом для ключевых смыслов. «Воду» отсекай, всю полезную суть сохраняй на 100%.
"""

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "HTTP-Referer": "https://github.com",
            "X-Title": "Zoom Summary Bot",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": MODEL_NAME,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2  # Низкая температура для максимальной точности фактов
        }

        response = requests.post(OPENROUTER_URL, headers=headers, json=payload)
        
        if response.status_code == 200:
            summary = response.json()["choices"][0]["message"]["content"]
            # Отправляем длинный отчет частями, чтобы Telegram не ругался на лимит символов
            for i in range(0, len(summary), 4000):
                await update.message.reply_text(summary[i:i+4000], parse_mode="Markdown")
        else:
            await update.message.reply_text(f"❌ Ошибка от OpenRouter: {response.text}")

    except Exception as e:
        await update.message.reply_text(f"❌ Произошла ошибка при обработке: {e}")
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), telegram_app.bot)
    telegram_app.update_queue.put_nowait(update)
    return "ok", 200

@app.route("/")
def index():
    return "Bot is alive!", 200

async def setup_webhook():
    global telegram_app
    telegram_app = Application.builder().token(TOKEN).build()
    telegram_app.add_handler(MessageHandler(filters.AUDIO | filters.DOCUMENT | filters.VOICE, handle_audio))
    await telegram_app.initialize()
    if WEBHOOK_URL:
        await telegram_app.bot.set_webhook(url=f"{WEBHOOK_URL}/{TOKEN}")
    await telegram_app.start()

if __name__ == "__main__":
    import asyncio
    asyncio.run(setup_webhook())
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
