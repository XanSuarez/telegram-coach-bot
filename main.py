import os
import random
import base64
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI

TELEGRAM_TOKEN = os.getenv("TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

users = {}

# =========================
# USER
# =========================
def get_user(user_id):
    if user_id not in users:
        users[user_id] = {
            "estado": None,
            "deporte": None,
            "tiempo": None,
            "fatiga": None,
            "perfil": {
                "tendencia": "neutral",  # carga percibida
            },
            "historial": [],
            "ultimo_entreno": ""
        }
    return users[user_id]

def reset_user(user):
    user["estado"] = None

# =========================
# PLANTILLAS CERRADAS
# =========================
def plantilla_running(tipo):
    if tipo == "recuperacion":
        return "Z1 continuo + técnica ligera"
    if tipo == "aerobico":
        return "Z2 continuo + técnica"
    if tipo == "tempo":
        return "bloques Z3"
    return "intervalos Z4-Z5"

def plantilla_bici(tipo):
    if tipo == "recuperacion":
        return "Z1 cadencia alta"
    if tipo == "aerobico":
        return "Z2 continuo + cadencia"
    if tipo == "tempo":
        return "bloques Z3"
    return "intervalos Z4"

def plantilla_natacion(tipo):
    if tipo == "recuperacion":
        return "técnica + suave"
    if tipo == "aerobico":
        return "series largas Z2"
    if tipo == "tempo":
        return "series medias Z3"
    return "series cortas Z4"

# =========================
# DECISIÓN SESIÓN
# =========================
def decidir_tipo(user):
    fatiga = user["fatiga"]
    tendencia = user["perfil"]["tendencia"]

    if tendencia == "fatiga_alta":
        return "recuperacion"

    if fatiga >= 8:
        return "recuperacion"
    if fatiga >= 6:
        return "aerobico"
    if fatiga >= 4:
        return "tempo"
    return "intensidad"

# =========================
# GPT (RELLENA PLANTILLA)
# =========================
def generar_prompt(user, plantilla):

    return f"""
Eres entrenador profesional.

IMPORTANTE:
- NO inventar estructura
- SOLO desarrollar esta plantilla:
{plantilla}

Condiciones:
- Deporte: {user["deporte"]}
- Tiempo: {user["tiempo"]} min
- Fatiga: {user["fatiga"]}

Reglas:
- Running/Bici → minutos
- Natación → metros
- Zonas Z1-Z5
- NO mezclar deportes

Formato:

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
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.6
    )
    return response.choices[0].message.content

# =========================
# START
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)

    user["estado"] = "deporte"

    teclado = [["Running", "Bici", "Natación"]]

    await update.message.reply_text(
        "👋 XS Coach activo\n\n"
        "🏃‍♂️ ¿Qué vas a entrenar hoy?",
        reply_markup=ReplyKeyboardMarkup(teclado, one_time_keyboard=True)
    )

# =========================
# MANEJADOR
# =========================
async def manejar(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = get_user(update.effective_user.id)
    texto = update.message.text.lower()

    # =========================
    # FEEDBACK USUARIO
    # =========================
    if texto in ["muy duro", "duro", "fácil", "perfecto"]:

        if texto in ["muy duro", "duro"]:
            user["perfil"]["tendencia"] = "fatiga_alta"
        elif texto == "fácil":
            user["perfil"]["tendencia"] = "corto"
        else:
            user["perfil"]["tendencia"] = "neutral"

        await update.message.reply_text(
            "📊 Feedback guardado\n👉 Ajustaré los próximos entrenamientos"
        )
        return

    # =========================
    # FLUJO
    # =========================
    if user["estado"] == "deporte":
        user["deporte"] = texto
        user["estado"] = "tiempo"

        await update.message.reply_text(
            "⏱️ ¿Cuánto tiempo tienes para entrenar hoy?\n👉 Así ajusto el volumen"
        )
        return

    if user["estado"] == "tiempo":
        if not texto.isdigit():
            await update.message.reply_text("Pon minutos (ej: 60)")
            return

        user["tiempo"] = int(texto)
        user["estado"] = "fatiga"

        await update.message.reply_text(
            "😵 Cuánta fatiga sientes hoy (0-10)\n👉 Así ajusto la carga"
        )
        return

    if user["estado"] == "fatiga":

        if not texto.isdigit():
            await update.message.reply_text("Número 0-10")
            return

        user["fatiga"] = int(texto)

        tipo = decidir_tipo(user)

        if "run" in user["deporte"]:
            plantilla = plantilla_running(tipo)
        elif "bici" in user["deporte"]:
            plantilla = plantilla_bici(tipo)
        else:
            plantilla = plantilla_natacion(tipo)

        prompt = generar_prompt(user, plantilla)
        respuesta = llamar_gpt(prompt)

        user["ultimo_entreno"] = respuesta

        await update.message.reply_text(respuesta)

        await update.message.reply_text(
            "📊 ¿Cómo ha ido la sesión?\nResponde: fácil / perfecto / duro"
        )

        reset_user(user)
        return

# =========================
# RUN
# =========================
print("🚀 XS Coach PRO activo")

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar))

app.run_polling()
