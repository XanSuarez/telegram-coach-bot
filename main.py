import os
import random
import base64
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
# SESIONES BASE
# =========================
SESIONES = {
    "running": {
        "recuperacion": ["40' Z1 + 4x20'' técnica + 5'"],
        "aerobico": ["50' Z2 continuo + 5x20'' técnica"],
        "tempo": ["15' + 3x8' Z3 (rec 2') + 10'"],
        "intensidad": ["15' + 6x3' Z4 (rec 2') + 10'"]
    },
    "bici": {
        "recuperacion": ["45' Z1 cadencia alta"],
        "aerobico": ["60' Z2 + 5x1' cadencia"],
        "tempo": ["20' + 3x10' Z3 (rec 3') + 10'"],
        "intensidad": ["15' + 5x4' Z4 (rec 3') + 10'"]
    },
    "natación": {
        "recuperacion": ["200 + 6x50 técnica + 200"],
        "aerobico": ["300 + 8x100 Z2 + 200"],
        "tempo": ["300 + 5x200 Z3 + 100"],
        "intensidad": ["300 + 10x100 Z4 + 100"]
    }
}

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
            "perfil": {},
            "ultimo_entreno": ""
        }
    return users[user_id]

def reset_user(user):
    user["estado"] = None

# =========================
# LÓGICA
# =========================
def decidir_tipo_sesion(fatiga):
    if fatiga >= 8:
        return "recuperacion"
    if fatiga >= 6:
        return "aerobico"
    if fatiga >= 4:
        return "tempo"
    return "intensidad"

def seleccionar_base(deporte, tipo):
    if "run" in deporte:
        deporte = "running"
    elif "bici" in deporte:
        deporte = "bici"
    else:
        deporte = "natación"

    return random.choice(SESIONES[deporte][tipo])

# =========================
# GPT ENTRENAMIENTO
# =========================
def generar_prompt(user, base):

    return f"""
Eres entrenador profesional.

Sesión base:
{base}

Condiciones:
- Deporte: {user["deporte"]}
- Fatiga: {user["fatiga"]}/10
- Tiempo: {user["tiempo"]} min

Reglas:
- Usar zonas Z1-Z5
- No ritmo exacto
- Estructura clara y visual

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
        temperature=0.7
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
        "👋 Soy tu entrenador XS Coach\n\n"
        "Voy a ajustar tu sesión como un entrenador real\n\n"
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
    # COMPARTIR
    # =========================
    if "compartir" in texto:

        prompt = f"""
Texto Instagram corto para compartir entrenamiento.

Debe:
- ser motivador
- 2-3 emojis
- generar curiosidad
- mencionar entrenador digital

Máx 5 líneas
"""

        caption = llamar_gpt(prompt)

        await update.message.reply_text(
            f"🔥 Copy listo:\n\n{caption}\n\n👉 Escribe 'imagen' para tu story"
        )
        return

    # =========================
    # IMAGEN
    # =========================
    if "imagen" in texto:

        prompt = f"""
Fitness training card.

Style:
- dark background
- premium
- TrainingPeaks style
- XS Coach branding

Include:
- workout completed
- endurance training
"""

        result = client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size="1024x1024"
        )

        image_base64 = result.data[0].b64_json

        with open("entreno.png", "wb") as f:
            f.write(base64.b64decode(image_base64))

        await update.message.reply_photo(photo=open("entreno.png", "rb"))
        return

    # =========================
    # FLUJO
    # =========================
    if user["estado"] == "deporte":

        user["deporte"] = texto
        user["estado"] = "tiempo"

        await update.message.reply_text(
            "⏱️ ¿Cuánto tiempo tienes?\n👉 Ajusto volumen e intensidad"
        )
        return

    if user["estado"] == "tiempo":

        if not texto.isdigit():
            await update.message.reply_text("Pon minutos (ej: 60)")
            return

        user["tiempo"] = int(texto)
        user["estado"] = "fatiga"

        await update.message.reply_text(
            "😵 Fatiga (0-10)\n👉 Ajusto carga"
        )
        return

    if user["estado"] == "fatiga":

        if not texto.isdigit():
            await update.message.reply_text("Número 0-10")
            return

        user["fatiga"] = int(texto)

        tipo = decidir_tipo_sesion(user["fatiga"])
        base = seleccionar_base(user["deporte"], tipo)

        prompt = generar_prompt(user, base)
        respuesta = llamar_gpt(prompt)

        user["ultimo_entreno"] = respuesta

        await update.message.reply_text(respuesta)

        await update.message.reply_text(
            "📲 ¿Quieres compartirlo en redes?\nEscribe: compartir"
        )

        reset_user(user)
        return

# =========================
# RUN
# =========================
print("🚀 Bot XS Coach iniciado")

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar))

app.run_polling()
