import os
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI

# =========================
# CONFIG
# =========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

users = {}

# =========================
# UTILIDADES
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

# =========================
# MOTOR DECISIÓN
# =========================
def decidir_tipo_sesion(user):

    fatiga = user["fatiga"]
    ultimo = user.get("ultima_sesion_tipo", None)

    if fatiga >= 8:
        return "recuperacion"

    if ultimo == "intensidad":
        return "aerobico"

    if 5 <= fatiga <= 7:
        return "tempo"

    if fatiga <= 4:
        return "intensidad"

    return "aerobico"

# =========================
# MEMORIA
# =========================
def actualizar_memoria(user, tipo, duracion):
    user["ultima_sesion_tipo"] = tipo

    historial = user.get("historial", [])
    historial.append({
        "tipo": tipo,
        "duracion": duracion
    })

    user["historial"] = historial[-5:]

# =========================
# PROMPT GPT
# =========================
def generar_prompt(user, tipo_sesion):

    return f"""
Eres un entrenador profesional de triatlón.

DATOS:
- Deporte: {user["deporte"]}
- Tiempo: {user["tiempo"]} min
- Fatiga: {user["fatiga"]}/10
- Tipo sesión: {tipo_sesion}
- Métrica: {user.get("perfil", {}).get("metrica", "fc")}
- Historial: {user.get("historial", [])}

REGLAS:
- Usa zonas Z1-Z5
- No repitas sesiones típicas
- Sé específico y técnico
- Natación SIEMPRE con técnica
- Explica el por qué

FORMATO:

🏁 Contexto breve

🎯 Objetivo

🔥 Entrenamiento:
- Calentamiento
- Bloque principal
- Técnica (si aplica)
- Vuelta a la calma

🔁 Alternativa

💡 Nota entrenador
"""

def llamar_gpt(prompt):
    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "Entrenador de triatlón experto"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        return response.choices[0].message.content

    except Exception as e:
        return f"❌ Error GPT: {e}"

# =========================
# HANDLERS
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = get_user(update.effective_user.id)

    # Pregunta métrica solo 1 vez
    if "metrica" not in user["perfil"]:
        user["estado"] = "metrica"

        teclado = [["Potencia", "Frecuencia cardíaca", "Ritmo"]]

        await update.message.reply_text(
            "📊 ¿Cómo entrenas normalmente?",
            reply_markup=ReplyKeyboardMarkup(teclado, one_time_keyboard=True)
        )
        return

    user["estado"] = "deporte"

    teclado = [["Running", "Bici", "Natación"]]

    await update.message.reply_text(
        "🏃‍♂️ ¿Qué vas a entrenar hoy?",
        reply_markup=ReplyKeyboardMarkup(teclado, one_time_keyboard=True)
    )


async def manejar(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = get_user(update.effective_user.id)
    texto = update.message.text.lower()

    # =========================
    # FLUJO GUIADO
    # =========================

    if user["estado"] == "metrica":
        if "potencia" in texto:
            user["perfil"]["metrica"] = "potencia"
        elif "ritmo" in texto:
            user["perfil"]["metrica"] = "ritmo"
        else:
            user["perfil"]["metrica"] = "fc"

        user["estado"] = "deporte"

        teclado = [["Running", "Bici", "Natación"]]

        await update.message.reply_text(
            "Perfecto 👌\n\n🏃‍♂️ ¿Qué vas a entrenar hoy?",
            reply_markup=ReplyKeyboardMarkup(teclado, one_time_keyboard=True)
        )
        return


    if user["estado"] == "deporte":
        user["deporte"] = texto
        user["estado"] = "tiempo"

        await update.message.reply_text("⏱️ ¿Cuántos minutos tienes?")
        return


    if user["estado"] == "tiempo":
        if not texto.isdigit():
            await update.message.reply_text("Pon solo un número (ej: 60)")
            return

        user["tiempo"] = int(texto)
        user["estado"] = "fatiga"

        await update.message.reply_text("😵 ¿Nivel de fatiga? (0-10)")
        return


    if user["estado"] == "fatiga":
        if not texto.isdigit():
            await update.message.reply_text("Pon un número del 0 al 10")
            return

        user["fatiga"] = int(texto)

        # 🔥 GENERAR ENTRENAMIENTO
        tipo = decidir_tipo_sesion(user)
        prompt = generar_prompt(user, tipo)
        respuesta = llamar_gpt(prompt)

        await update.message.reply_text(respuesta)

        actualizar_memoria(user, tipo, user["tiempo"])
        reset_user(user)

        return


    # =========================
    # MODO CONVERSACIONAL GPT
    # =========================
    prompt = f"""
Eres un entrenador de triatlón.

Usuario dice: {texto}

Responde de forma útil, técnica y clara.
"""

    respuesta = llamar_gpt(prompt)

    await update.message.reply_text(respuesta)


# =========================
# MAIN
# =========================
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar))

print("Bot en marcha 🚀")
app.run_polling()
