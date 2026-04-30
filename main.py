import os
import random
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
# BASE DE SESIONES
# =========================
SESIONES = {
    "running": {
        "recuperacion": [
            "40' Z1 + 4x20'' técnica + 5' suave",
            "30' Z1 + movilidad + 5 progresivos"
        ],
        "aerobico": [
            "50' Z2 continuo + 5x20'' técnica",
            "45' progresivo Z2-Z3"
        ],
        "tempo": [
            "15' + 3x8' Z3 (rec 2') + 10'",
            "20' + 2x12' Z3 (rec 3') + 10'"
        ],
        "intensidad": [
            "15' + 6x3' Z4 (rec 2') + 10'",
            "20' + 8x2' Z5 (rec 1') + 10'"
        ]
    },
    "bici": {
        "recuperacion": ["45' Z1 cadencia alta"],
        "aerobico": ["60' Z2 + 5x1' cadencia alta"],
        "tempo": ["20' + 3x10' Z3 (rec 3') + 10'"],
        "intensidad": ["15' + 5x4' Z4 (rec 3') + 10'"]
    },
    "natación": {
        "recuperacion": ["200 + 6x50 técnica + 200"],
        "aerobico": ["300 + 6x50 técnica + 8x100 Z2 (rec 15'') + 200"],
        "tempo": ["300 + 4x50 técnica + 5x200 Z3 (rec 20'') + 100"],
        "intensidad": ["300 + 8x50 técnica + 10x100 Z4 (rec 20'') + 100"]
    }
}

# =========================
# USER HELPERS
# =========================
def get_user(user_id):
    if user_id not in users:
        users[user_id] = {
            "estado": None,
            "deporte": None,
            "tiempo": None,
            "fatiga": None,
            "perfil": {},
            "historial": []
        }
    return users[user_id]

def reset_user(user):
    user["estado"] = None
    user["deporte"] = None
    user["tiempo"] = None
    user["fatiga"] = None

def actualizar_memoria(user, tipo):
    user["historial"].append(tipo)
    user["historial"] = user["historial"][-3:]

# =========================
# LÓGICA ENTRENAMIENTO
# =========================
def decidir_tipo_sesion(user):
    fatiga = user["fatiga"]
    ultimo = user["historial"][-1] if user["historial"] else None

    if fatiga >= 8:
        return "recuperacion"
    if ultimo == "intensidad":
        return "aerobico"
    if fatiga >= 6:
        return "aerobico"
    if fatiga >= 4:
        return "tempo"
    return "intensidad"

def seleccionar_base(user, tipo):
    deporte = user["deporte"]

    if "run" in deporte:
        deporte = "running"
    elif "bici" in deporte:
        deporte = "bici"
    else:
        deporte = "natación"

    base = random.choice(SESIONES[deporte][tipo])
    return deporte, base

# =========================
# GPT
# =========================
def generar_prompt(user, tipo, base):

    return f"""
Eres un entrenador profesional de resistencia.

Sesión base:
{base}

Condiciones:
- Deporte: {user["deporte"]}
- Fatiga: {user["fatiga"]}/10
- Tiempo disponible: {user["tiempo"]} min

Reglas:
- Usar Z1-Z5
- NO ritmo en min/km
- NO %FC
- Mantener lógica real de entrenamiento
- Estructura clara tipo entrenador élite

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
# START
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = get_user(update.effective_user.id)

    user["estado"] = "metrica"

    await update.message.reply_text(
        "📊 Para ajustar bien la intensidad 👇\n\n"
        "¿Sueles entrenar por zonas o sensaciones?\n\n"
        "👉 Esto me ayuda a adaptar los ritmos a tu realidad"
    )

# =========================
# MANEJADOR PRINCIPAL
# =========================
async def manejar(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = get_user(update.effective_user.id)
    texto = update.message.text.lower()

    # =========================
    # MÉTRICA
    # =========================
    if user["estado"] == "metrica":

        user["perfil"]["metrica"] = "zonas"

        user["estado"] = "deporte"

        teclado = [["Running", "Bici", "Natación"]]

        await update.message.reply_text(
            "Perfecto 👌\n\n"
            "🏃‍♂️ ¿Qué vas a entrenar hoy?",
            reply_markup=ReplyKeyboardMarkup(teclado, one_time_keyboard=True)
        )
        return

    # =========================
    # DEPORTE
    # =========================
    if user["estado"] == "deporte":

        user["deporte"] = texto
        user["estado"] = "tiempo"

        await update.message.reply_text(
            "⏱️ ¿Cuántos minutos tienes hoy?\n\n"
            "👉 Así ajusto volumen e intensidad"
        )
        return

    # =========================
    # TIEMPO
    # =========================
    if user["estado"] == "tiempo":

        if not texto.isdigit():
            await update.message.reply_text("Pon un número (ej: 60)")
            return

        user["tiempo"] = int(texto)
        user["estado"] = "fatiga"

        await update.message.reply_text(
            "😵 ¿Cómo estás hoy de fatiga?\n\n"
            "0 = fresco | 10 = destruido"
        )
        return

    # =========================
    # FATIGA → ENTRENAMIENTO
    # =========================
    if user["estado"] == "fatiga":

        if not texto.isdigit():
            await update.message.reply_text("Pon un número del 0 al 10")
            return

        user["fatiga"] = int(texto)

        tipo = decidir_tipo_sesion(user)
        deporte, base = seleccionar_base(user, tipo)

        prompt = generar_prompt(user, tipo, base)
        respuesta = llamar_gpt(prompt)

        await update.message.reply_text(respuesta)

        actualizar_memoria(user, tipo)
        reset_user(user)

        return

# =========================
# RUN
# =========================
print("🚀 Iniciando bot...")

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar))

print("📡 Bot activo")

app.run_polling()
