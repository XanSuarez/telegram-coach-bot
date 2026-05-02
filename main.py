import os
import logging
import random
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)
from openai import OpenAI

# =========================
# CONFIG
# =========================
logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

# =========================
# ESTADOS
# =========================
DEPORTE, METRICA_BICI, TIEMPO, FATIGA, FEEDBACK = range(5)

# =========================
# LÓGICA ENTRENAMIENTO
# =========================
def decidir_tipo(user_data):
    fatiga = user_data["fatiga"]
    tendencia = user_data["perfil"].get("tendencia", "neutral")

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


def plantilla_base(deporte, tipo):

    base = {
        "running": {
            "recuperacion": [
                "40' Z1 + 4x20'' técnica + movilidad",
                "30' Z1 + 5 progresivos"
            ],
            "aerobico": [
                "50' Z2 continuo",
                "45' progresivo Z2-Z3"
            ],
            "tempo": [
                "3x8' Z3 (rec 2')",
                "2x12' Z3 (rec 3')"
            ],
            "intensidad": [
                "6x3' Z4 (rec 2')",
                "8x2' Z5 (rec 1')"
            ]
        },
        "bici": {
            "recuperacion": [
                "45' Z1 cadencia alta",
            ],
            "aerobico": [
                "60' Z2 + 5x1' cadencia alta",
            ],
            "tempo": [
                "3x10' Z3 (rec 3')",
            ],
            "intensidad": [
                "5x4' Z4 (rec 3')",
            ]
        },
        "natación": {
            "recuperacion": [
                "200 + 6x50 técnica + 200",
            ],
            "aerobico": [
                "300 + 8x100 Z2 (rec 15'') + 200",
            ],
            "tempo": [
                "300 + 5x200 Z3 (rec 20'') + 100",
            ],
            "intensidad": [
                "300 + 10x100 Z4 (rec 20'') + 100",
            ]
        }
    }

    return random.choice(base[deporte][tipo])


# =========================
# PROMPT GPT
# =========================
def generar_prompt(data):

    extra_bici = ""

    if data["deporte"] == "bici":
        if data["perfil"]["metrica_bici"] == "potencia":
            extra_bici = """
ZONAS POR POTENCIA (FTP):
Z1 <55%
Z2 56-75%
Z3 76-90%
Z4 91-105%
Z5 >106%

NO usar FC
"""
        else:
            extra_bici = """
ZONAS POR FCmax:
Z1 <75%
Z2 76-80%
Z3 81-85%
Z4 86-91%
Z5 >92%

NO usar potencia
"""

    return f"""
Eres entrenador profesional de triatlón.

DATOS:
- Deporte: {data["deporte"]}
- Tiempo: {data["tiempo"]} min
- Fatiga: {data["fatiga"]}/10

Base:
{data["base"]}

{extra_bici}

REGLAS:
- NO mezclar deportes
- Running y bici → por tiempo
- Natación → por metros
- Usar zonas Z1-Z5
- Estilo técnico pero claro
- No genérico, estilo entrenador real

FORMATO:

📊 Contexto

🏁 Objetivo

🔥 Entrenamiento:
🔹 Calentamiento
🔹 Bloque principal
🔹 Vuelta a la calma

🔁 Alternativa

💡 Nota entrenador
"""


def llamar_gpt(prompt):
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"⚠️ Error GPT: {e}"


# =========================
# HANDLERS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data.clear()
    context.user_data["perfil"] = {
        "tendencia": "neutral",
        "metrica_bici": "fc"
    }

    teclado = [["Running", "Bici", "Natación"]]

    await update.message.reply_text(
        "👋 XS Coach\n\n🏃‍♂️ ¿Qué vas a entrenar hoy?",
        reply_markup=ReplyKeyboardMarkup(teclado, one_time_keyboard=True, resize_keyboard=True)
    )

    return DEPORTE


async def seleccionar_deporte(update: Update, context: ContextTypes.DEFAULT_TYPE):

    texto = update.message.text.lower()
    context.user_data["deporte"] = texto

    if "bici" in texto:
        teclado = [["Potencia", "Frecuencia cardíaca"]]

        await update.message.reply_text(
            "⚙️ ¿Cómo te guías en bici?\n👉 Esto define cómo te marco las zonas",
            reply_markup=ReplyKeyboardMarkup(teclado, one_time_keyboard=True, resize_keyboard=True)
        )
        return METRICA_BICI

    await update.message.reply_text(
        "⏱️ ¿Cuántos minutos tienes?\n👉 Ajusto volumen e intensidad"
    )
    return TIEMPO


async def seleccionar_metrica(update: Update, context: ContextTypes.DEFAULT_TYPE):

    texto = update.message.text.lower()

    if "potencia" in texto:
        context.user_data["perfil"]["metrica_bici"] = "potencia"
    else:
        context.user_data["perfil"]["metrica_bici"] = "fc"

    await update.message.reply_text("⏱️ ¿Cuánto tiempo tienes hoy?")
    return TIEMPO


async def seleccionar_tiempo(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message.text.isdigit():
        await update.message.reply_text("Pon minutos (ej: 60)")
        return TIEMPO

    context.user_data["tiempo"] = int(update.message.text)

    await update.message.reply_text(
        "😵 ¿Nivel de fatiga? (0-10)\n👉 Ajusto la carga"
    )
    return FATIGA


async def generar_entrenamiento(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message.text.isdigit():
        await update.message.reply_text("Número 0-10")
        return FATIGA

    context.user_data["fatiga"] = int(update.message.text)

    await update.message.reply_text("🤖 Generando sesión...")

    # NORMALIZAR DEPORTE
    dep = context.user_data["deporte"]

    if "run" in dep:
        deporte = "running"
    elif "bici" in dep:
        deporte = "bici"
    else:
        deporte = "natación"

    tipo = decidir_tipo(context.user_data)
    base = plantilla_base(deporte, tipo)

    data = {
        "deporte": deporte,
        "tiempo": context.user_data["tiempo"],
        "fatiga": context.user_data["fatiga"],
        "perfil": context.user_data["perfil"],
        "base": base
    }

    prompt = generar_prompt(data)
    respuesta = llamar_gpt(prompt)

    await update.message.reply_text(respuesta)

    await update.message.reply_text(
        "📊 Valora la sesión (0-5)\n\n0 = muy fácil\n5 = muy duro"
    )

    return FEEDBACK


async def feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message.text.isdigit():
        return FEEDBACK

    val = int(update.message.text)

    if val >= 4:
        context.user_data["perfil"]["tendencia"] = "muy_duro"
    elif val <= 1:
        context.user_data["perfil"]["tendencia"] = "muy_facil"
    else:
        context.user_data["perfil"]["tendencia"] = "neutral"

    await update.message.reply_text("📊 Feedback guardado 👌")

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelado", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# =========================
# RUN
# =========================
if __name__ == "__main__":

    if not TOKEN:
        print("❌ Falta TOKEN")
    else:
        app = ApplicationBuilder().token(TOKEN).build()

        conv = ConversationHandler(
            entry_points=[CommandHandler("start", start)],
            states={
                DEPORTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, seleccionar_deporte)],
                METRICA_BICI: [MessageHandler(filters.TEXT & ~filters.COMMAND, seleccionar_metrica)],
                TIEMPO: [MessageHandler(filters.TEXT & ~filters.COMMAND, seleccionar_tiempo)],
                FATIGA: [MessageHandler(filters.TEXT & ~filters.COMMAND, generar_entrenamiento)],
                FEEDBACK: [MessageHandler(filters.TEXT & ~filters.COMMAND, feedback)],
            },
            fallbacks=[CommandHandler("cancel", cancel)],
            allow_reentry=True
        )

        app.add_handler(conv)

        print("🚀 XS Coach funcionando...")
        app.run_polling()

