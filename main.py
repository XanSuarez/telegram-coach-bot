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
# START (manual)
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
# AUTO START (clave)
# =========================
async def auto_start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    # 🔒 Si ya está en flujo → no tocar
    if context.user_data.get("en_flujo"):
        return

    context.user_data.clear()
    context.user_data["en_flujo"] = True

    teclado = [["Running", "Bici", "Natación"]]

    await update.message.reply_text(
        "👋 XS Coach\n\n🏃‍♂️ ¿Qué vas a entrenar hoy?",
        reply_markup=ReplyKeyboardMarkup(teclado, resize_keyboard=True)
    )

    return DEPORTE  # 🔥 MUY IMPORTANTE

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

    if "run" in user["deporte"]:
        return f"{t}' Z2 + técnica"

    if "bici" in user["deporte"]:
        return f"{t}' Z2 + cadencia"

    return "300 + 8x100 + 200"

# =========================
# GPT
# =========================
def generar_prompt(user, base):

    extra = ""

    if "bici" in user["deporte"]:
        if user.get("metrica") == "potencia":
            extra = "Usa zonas por potencia (%FTP)"
        else:
            extra = "Usa zonas por frecuencia cardiaca"

    return f"""
Eres entrenador profesional.

Sesión:
{base}

Tiempo: {user["tiempo"]}
Fatiga: {user["fatiga"]}

{extra}

Hazla clara, estructurada y con emojis.

FORMATO:

📊 Contexto
🏁 Objetivo
🔥 Entrenamiento
🔁 Alternativa
💡 Nota entrenador
"""

def llamar_gpt(prompt):

    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        return r.choices[0].message.content
    except Exception as e:
        return f"⚠️ Error GPT: {e}"

# =========================
# FLUJO
# =========================
async def deporte(update: Update, context: ContextTypes.DEFAULT_TYPE):

    texto = update.message.text.lower()
    context.user_data["deporte"] = texto

    # 👉 SI ES BICI → pregunta métrica
    if "bici" in texto:

        teclado = [["Potencia", "Frecuencia cardiaca"]]

        await update.message.reply_text(
            "⚙️ ¿Cómo te guías en la bici?\n👉 Esto define las zonas",
            reply_markup=ReplyKeyboardMarkup(teclado, resize_keyboard=True)
        )
        return METRICA

    await update.message.reply_text(
        "⏱️ ¿Cuánto tiempo tienes?\n👉 Ajusto volumen"
    )
    return TIEMPO


async def metrica(update: Update, context: ContextTypes.DEFAULT_TYPE):

    texto = update.message.text.lower()

    if "potencia" in texto:
        context.user_data["metrica"] = "potencia"
    else:
        context.user_data["metrica"] = "fc"

    await update.message.reply_text(
        "⏱️ ¿Cuánto tiempo tienes?\n👉 Ajusto volumen"
    )
    return TIEMPO


async def tiempo(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message.text.isdigit():
        await update.message.reply_text("Pon minutos (ej: 60)")
        return TIEMPO

    context.user_data["tiempo"] = int(update.message.text)

    await update.message.reply_text(
        "😵 ¿Nivel de fatiga? (0-10)\n👉 Ajusto carga"
    )
    return FATIGA


async def fatiga(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message.text.isdigit():
        await update.message.reply_text("Pon número 0-10")
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
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.TEXT & ~filters.COMMAND, auto_start)
        ],
        states={
            DEPORTE: [MessageHandler(filters.TEXT, deporte)],
            METRICA: [MessageHandler(filters.TEXT, metrica)],
            TIEMPO: [MessageHandler(filters.TEXT, tiempo)],
            FATIGA: [MessageHandler(filters.TEXT, fatiga)],
        },
        fallbacks=[],
        allow_reentry=True
    )

    app.add_handler(conv)

    print("🚀 XS Coach funcionando correctamente")
    app.run_polling()
