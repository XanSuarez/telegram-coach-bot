import os
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI

# =========================
# CONFIG
# =========================
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
                "tendencia": "neutral",
                "metrica_bici": None
            }
        }
    return users[user_id]


def reset_user(user):
    user["estado"] = None


# =========================
# DECISIÓN SESIÓN
# =========================
def decidir_tipo(user):
    fatiga = user["fatiga"]
    tendencia = user["perfil"]["tendencia"]

    if tendencia == "muy_duro":
        return "recuperacion"

    if fatiga >= 8:
        return "recuperacion"
    if fatiga >= 6:
        return "aerobico"
    if fatiga >= 4:
        return "tempo"
    return "intensidad"


# =========================
# PLANTILLAS
# =========================
def plantilla_running(tipo):
    return {
        "recuperacion": "Z1 continuo + técnica",
        "aerobico": "Z2 continuo",
        "tempo": "bloques Z3",
        "intensidad": "intervalos Z4-Z5"
    }[tipo]


def plantilla_bici(tipo):
    return {
        "recuperacion": "Z1 cadencia alta",
        "aerobico": "Z2 continuo",
        "tempo": "bloques Z3",
        "intensidad": "intervalos Z4"
    }[tipo]


def plantilla_natacion(tipo):
    return {
        "recuperacion": "técnica + suave",
        "aerobico": "series largas Z2",
        "tempo": "series medias Z3",
        "intensidad": "series cortas Z4"
    }[tipo]


# =========================
# GPT
# =========================
def generar_prompt(user, plantilla):

    reglas_extra = ""

    # 🚴 BICI PERSONALIZADA
    if "bici" in user["deporte"]:

        if user["perfil"].get("metrica_bici") == "potencia":

            reglas_extra = """
ZONAS CICLISMO (FTP):
- Z1: <55% FTP
- Z2: 56-75% FTP
- Z3: 76-90% FTP
- Z4: 91-105% FTP
- Z5: >106% FTP

OBLIGATORIO:
- Expresar intensidad en %FTP o vatios
- NO usar frecuencia cardiaca
"""

        else:

            reglas_extra = """
ZONAS CICLISMO (FCmax):
- Z1: <75%
- Z2: 76-80%
- Z3: 81-85%
- Z4: 86-91%
- Z5: >92%

OBLIGATORIO:
- Expresar intensidad en frecuencia cardiaca
- NO usar potencia
"""

    return f"""
Eres entrenador profesional.

Plantilla:
{plantilla}

Condiciones:
- Deporte: {user["deporte"]}
- Tiempo: {user["tiempo"]} min
- Fatiga: {user["fatiga"]}

{reglas_extra}

REGLAS:
- NO mezclar deportes
- Running/Bici → tiempo
- Natación → metros
- Usar zonas Z1-Z5
- Explicar intensidad de forma clara

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
        "👋 XS Coach\n\n🏃‍♂️ ¿Qué vas a entrenar hoy?",
        reply_markup=ReplyKeyboardMarkup(teclado, one_time_keyboard=True)
    )


# =========================
# MANEJADOR
# =========================
async def manejar(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = get_user(update.effective_user.id)
    texto = update.message.text.lower()

    # =========================
    # FEEDBACK 0-5
    # =========================
    if texto.isdigit():
        valor = int(texto)

        if 0 <= valor <= 5:

            if valor >= 4:
                user["perfil"]["tendencia"] = "muy_duro"
            elif valor <= 1:
                user["perfil"]["tendencia"] = "muy_facil"
            else:
                user["perfil"]["tendencia"] = "neutral"

            await update.message.reply_text(
                "📊 Feedback guardado\n👉 Ajusto próximos entrenamientos"
            )
            return

    # =========================
    # DEPORTE
    # =========================
    if user["estado"] == "deporte":

        user["deporte"] = texto

        # 🔥 SI ES BICI → preguntar métrica
        if "bici" in texto:

            user["estado"] = "metrica_bici"

            teclado = [["Potencia", "Frecuencia cardíaca"]]

            await update.message.reply_text(
                "⚙️ ¿Cómo te guías en bici?\n\n👉 Esto define cómo te marco las zonas",
                reply_markup=ReplyKeyboardMarkup(teclado, one_time_keyboard=True)
            )
            return

        user["estado"] = "tiempo"

        await update.message.reply_text(
            "⏱️ ¿Cuánto tiempo tienes?\n👉 Así ajusto el volumen"
        )
        return

    # =========================
    # MÉTRICA BICI
    # =========================
    if user["estado"] == "metrica_bici":

        if "potencia" in texto:
            user["perfil"]["metrica_bici"] = "potencia"
        else:
            user["perfil"]["metrica_bici"] = "fc"

        user["estado"] = "tiempo"

        await update.message.reply_text(
            "Perfecto 👌\n\n⏱️ ¿Cuánto tiempo tienes hoy?"
        )
        return

    # =========================
    # TIEMPO
    # =========================
    if user["estado"] == "tiempo":

        if not texto.isdigit():
            await update.message.reply_text("Pon minutos (ej: 60)")
            return

        user["tiempo"] = int(texto)
        user["estado"] = "fatiga"

        await update.message.reply_text(
            "😵 Como te sientes de Fatiga hoy? (0-10)\n👉 Así ajusto mejor la carga"
        )
        return

    # =========================
    # FATIGA → GENERAR
    # =========================
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

        await update.message.reply_text(respuesta)

        await update.message.reply_text(
            "📊 Valora la sesión (0-5)\n\n0 = muy fácil\n5 = muy duro"
        )

        reset_user(user)
        return


# =========================
# RUN
# =========================
print("🚀 XS Coach Endurance Bot")

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar))

app.run_polling()
