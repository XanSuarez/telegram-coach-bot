import os
import random
import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)
from openai import OpenAI

logging.basicConfig(level=logging.INFO)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

DEPORTE, METRICA, TIEMPO, FATIGA = range(4)

# =========================
# AUTO START (FUERA DEL CONV)
# =========================
async def auto_start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if context.user_data.get("en_flujo"):
        return

    context.user_data["en_flujo"] = True

    teclado = [["Running", "Bici", "Natación"]]

    await update.message.reply_text(
        "👋 XS Coach\n\n🏃‍♂️ ¿Qué vas a entrenar hoy?",
        reply_markup=ReplyKeyboardMarkup(teclado, resize_keyboard=True)
    )

# =========================
# START
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data.clear()
    context.user_data["en_flujo"] = True

    teclado = [["Running", "Bici", "Natación"]]

    await update.message.reply_text(
        "👋 XS Coach\n\n🏃‍♂️ ¿Qué vas a entrenar hoy?",
        reply_markup=ReplyKeyboardMarkup(teclado, resize_keyboard=True)
    )

    return DEPORTE

# =========================
# LÓGICA ENTRENAMIENTO
# =========================
def decidir_tipo(user):
    f = user["fatiga"]
    if f >= 8: return "recuperacion"
    if f >= 6: return "aerobico"
    if f >= 4: return "tempo"
    return "intensidad"

def generar_sesion(user):

    t = user["tiempo"]

    if user["deporte"] == "running":
        return f"{t}' Z2 + técnica"    

    if user["deporte"] == "bici":
        return f"{t}' Z2 + cadencia"

    return "300 + 8x100 + 200"

# =========================
# GPT
# =========================
def generar_prompt(user, base):

    return f"""
Eres entrenador.

Sesión:
{base}

Tiempo {user["tiempo"]}
Fatiga {user["fatiga"]}

Hazla estructurada con emojis.
"""

def llamar_gpt(prompt):

    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    return r.choices[0].message.content

# =========================
# FLUJO
# =========================
async def deporte(update: Update, context: ContextTypes.DEFAULT_TYPE):

    texto = update.message.text.lower()
    context.user_data["deporte"] = texto

    if "bici" in texto:

        teclado = [["Potencia", "Frecuencia cardiaca"]]

        await update.message.reply_text(
            "⚙️ ¿Cómo te guías?",
            reply_markup=ReplyKeyboardMarkup(teclado, resize_keyboard=True)
        )
        return METRICA

    await update.message.reply_text("⏱️ ¿Cuánto tiempo tienes?")
    return TIEMPO

async def metrica(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if "potencia" in update.message.text.lower():
        context.user_data["metrica"] = "potencia"
    else:
        context.user_data["metrica"] = "fc"

    await update.message.reply_text("⏱️ ¿Cuánto tiempo tienes?")
    return TIEMPO

async def tiempo(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message.text.isdigit():
        await update.message.reply_text("Pon minutos")
        return TIEMPO

    context.user_data["tiempo"] = int(update.message.text)

    await update.message.reply_text("😵 Fatiga 0-10")
    return FATIGA

async def fatiga(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message.text.isdigit():
        return FATIGA

    context.user_data["fatiga"] = int(update.message.text)

    await update.message.reply_text("🤖 Generando sesión...")

    base = generar_sesion(context.user_data)
    prompt = generar_prompt(context.user_data, base)
    respuesta = llamar_gpt(prompt)

    await update.message.reply_text(respuesta)

    context.user_data["en_flujo"] = False

    return ConversationHandler.END

# =========================
# RUN
# =========================
if __name__ == "__main__":

    app = ApplicationBuilder().token(os.getenv("TOKEN")).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            DEPORTE: [MessageHandler(filters.TEXT, deporte)],
            METRICA: [MessageHandler(filters.TEXT, metrica)],
            TIEMPO: [MessageHandler(filters.TEXT, tiempo)],
            FATIGA: [MessageHandler(filters.TEXT, fatiga)],
        },
        fallbacks=[],
        allow_reentry=True
    )

    # 🔥 IMPORTANTE: orden de handlers
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, auto_start))

    print("🚀 XS Coach funcionando correctamente")
    app.run_polling()
