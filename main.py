import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hola 👋 Soy tu entrenador.\n\n"
        "Dime:\n"
        "Tiempo disponible\nFatiga (0-10)\nTipo de sesión"
    )

async def generar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.lower()

    if "umbral" in texto:
        respuesta = (
            "🏃‍♂️ Sesión umbral:\n\n"
            "10’ suave\n"
            "3x8’ umbral (rec 2’)\n"
            "10’ suave"
        )
    else:
        respuesta = "Dame más info 😉"

    await update.message.reply_text(respuesta)

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT, generar))

app.run_polling()