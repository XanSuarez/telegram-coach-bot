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

DEPORTE, METRICA_BICI, TIEMPO, FATIGA, FEEDBACK = range(5)

# =========================
# GPT INTENCIÓN
# =========================
def detectar_intencion(texto):

    prompt = f"""
El usuario dice: "{texto}"

¿Está pidiendo un entrenamiento o ayuda para entrenar?

Responde SOLO:
SI
NO
"""

    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        return "SI" in r.choices[0].message.content.upper()
    except:
        return True  # fallback → mejor asumir que sí


# =========================
# LÓGICA
# =========================
def decidir_tipo(user):

    fatiga = user["fatiga"]
    tendencia = user.get("tendencia", "neutral")

    if tendencia == "muy_duro":
        return "recuperacion"

    if fatiga >= 8:
        return "recuperacion"
    elif fatiga >= 6:
        return "aerobico"
    elif fatiga >= 4:
        return "tempo"
    else:
        return "intensidad"


def generar_sesion(user):

    deporte = user["deporte"]
    tipo = decidir_tipo(user)
    tiempo = user["tiempo"]

    if deporte == "running":

        if tipo == "aerobico":
            return f"{tiempo}’ Z2 + 5x20'' técnica"

        if tipo == "tempo":
            return f"15' + 3x8' Z3 (rec 2') + 10'"

        if tipo == "intensidad":
            return f"15' + {random.choice(['6x3’ Z4', '8x2’ Z5'])} + 10'"

        if tipo == "recuperacion":
            return f"{tiempo}’ Z1 + movilidad"

    if deporte == "bici":

        if tipo == "aerobico":
            return f"{tiempo}’ Z2 + 5x1’ cadencia"

        if tipo == "tempo":
            return f"20’ + 3x10’ Z3 + 10’"

        if tipo == "intensidad":
            return f"15’ + 5x4’ Z4 + 10’"

        if tipo == "recuperacion":
            return f"{tiempo}’ Z1"

    if deporte == "natacion":

        if tipo == "aerobico":
            return "300 + 8x100 Z2 + 200"

        if tipo == "tempo":
            return "300 + 5x200 Z3 + 100"

        if tipo == "intensidad":
            return "300 + 10x100 Z4 + 100"

        if tipo == "recuperacion":
            return "200 + técnica + 200"


# =========================
# GPT RESPUESTA
# =========================
def generar_prompt(user, base):

    return f"""
Eres entrenador experto.

Sesión:
{base}

Condiciones:
- Tiempo: {user["tiempo"]}
- Fatiga: {user["fatiga"]}

Hazla clara, estructurada y con emojis.

FORMATO:

📊 Contexto
🏁 Objetivo
🔥 Entrenamiento
🔁 Alternativa
💡 Nota entrenador
"""


def llamar_gpt(prompt):

    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )
    return r.choices[0].message.content


# =========================
# START
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data.clear()
    context.user_data["tendencia"] = "neutral"

    teclado = [["Running", "Bici", "Natación"]]

    await update.message.reply_text(
        "👋 XS Coach\n\n¿Qué vas a entrenar hoy?",
        reply_markup=ReplyKeyboardMarkup(teclado, resize_keyboard=True)
    )

    return DEPORTE


# =========================
# AUTO START (CLAVE)
# =========================
async def auto_start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    texto = update.message.text.lower()

    if not detectar_intencion(texto):
        return

    context.user_data.clear()
    context.user_data["tendencia"] = "neutral"

    teclado = [["Running", "Bici", "Natación"]]

    await update.message.reply_text(
        "💡 Te ayudo con tu entrenamiento\n\n¿Qué vas a entrenar hoy?",
        reply_markup=ReplyKeyboardMarkup(teclado, resize_keyboard=True)
    )

    return DEPORTE


# =========================
# FLUJO
# =========================
async def deporte(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data["deporte"] = update.message.text.lower()

    await update.message.reply_text("⏱️ ¿Cuánto tiempo tienes?")
    return TIEMPO


async def tiempo(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message.text.isdigit():
        await update.message.reply_text("Pon minutos (ej: 60)")
        return TIEMPO

    context.user_data["tiempo"] = int(update.message.text)

    await update.message.reply_text("😵 Fatiga (0-10)")
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
            TIEMPO: [MessageHandler(filters.TEXT, tiempo)],
            FATIGA: [MessageHandler(filters.TEXT, fatiga)],
        },
        fallbacks=[],
        allow_reentry=True
    )

    app.add_handler(conv)

    print("🚀 Bot conversacional activo")
    app.run_polling()

