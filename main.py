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


def actualizar_memoria(user, tipo, tiempo):
    user["historial"].append({
        "tipo": tipo,
        "tiempo": tiempo
    })


# =========================
# GPT
# =========================
def llamar_gpt(prompt):

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Eres un entrenador experto en running, ciclismo y natación para triatletas. Respondes de forma estructurada, clara y profesional."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )

        return response.choices[0].message.content

    except Exception as e:
        print("❌ ERROR GPT:", e)
        return "⚠️ Error con GPT (posible cuota o API key)."


# =========================
# LÓGICA ENTRENAMIENTO
# =========================
def decidir_tipo_sesion(user):

    fatiga = user["fatiga"]

    if fatiga >= 8:
        return "recuperacion"
    elif fatiga >= 6:
        return "aerobico"
    elif fatiga >= 4:
        return "tempo"
    else:
        return "intensidad"


def generar_prompt(user, tipo):

    metrica = user.get("perfil", {}).get("metrica", "fc")
    deporte_base = user.get("perfil", {}).get("deporte_base", user["deporte"])

    # 🔥 REGLA CLAVE NATACIÓN
    formato_natacion = ""
    if "nat" in deporte_base:
        formato_natacion = """
IMPORTANTE PARA NATACIÓN:
- Estructura SIEMPRE en METROS (NO en minutos)
- Ejemplo: 200 + 4x50 + 6x100
- Incluir técnica (pull, palas, pies, drills)
"""

    return f"""
Eres un entrenador de alto nivel.

⚠️ REGLAS OBLIGATORIAS:
- SOLO entrenamiento de: {deporte_base}
- NO mezclar deportes
- NO triatlón combinado
- NO consejos genéricos
- TODO debe ser sesión estructurada

{formato_natacion}

DATOS:
- Deporte: {user["deporte"]}
- Tiempo: {user["tiempo"]} min
- Fatiga: {user["fatiga"]}/10
- Tipo: {tipo}
- Métrica: {metrica}

FORMATO:

📊 Contexto  
(resumen rápido del día)

🏁 Objetivo  

🔥 Entrenamiento  

🔹 Calentamiento  

🔹 Bloque principal  
(series claras con descansos)

🔹 Vuelta a la calma  

🔁 Alternativa  

💡 Nota entrenador  

ESTILO:
- Claro
- Profesional
- Con emojis
- Nada de texto plano largo
"""


# =========================
# START
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = get_user(update.effective_user.id)

    if "metrica" not in user["perfil"]:
        user["estado"] = "metrica"

        teclado = [["Potencia", "Ritmo", "Frecuencia cardíaca"]]

        await update.message.reply_text(
            "👋 Soy tu entrenador XS\n\n¿Con qué te guías?",
            reply_markup=ReplyKeyboardMarkup(teclado, one_time_keyboard=True)
        )
        return

    user["estado"] = "deporte"

    teclado = [["Running", "Bici", "Natación"]]

    await update.message.reply_text(
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
    # FORZAR FLUJO SIEMPRE
    # =========================
    if user["estado"] is None:

        if "metrica" not in user["perfil"]:
            user["estado"] = "metrica"

            teclado = [["Potencia", "Ritmo", "Frecuencia cardíaca"]]

            await update.message.reply_text(
                "📊 ¿Cómo te guías?",
                reply_markup=ReplyKeyboardMarkup(teclado, one_time_keyboard=True)
            )
            return

        user["estado"] = "deporte"

        teclado = [["Running", "Bici", "Natación"]]

        await update.message.reply_text(
            "💡 Necesito 3 datos:\n\n1️⃣ Deporte\n2️⃣ Tiempo\n3️⃣ Fatiga\n\n👉 ¿Qué vas a entrenar?",
            reply_markup=ReplyKeyboardMarkup(teclado, one_time_keyboard=True)
        )
        return

    # =========================
    # MÉTRICA
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
            "Perfecto 👌\n\n🏃‍♂️ ¿Qué vas a entrenar?",
            reply_markup=ReplyKeyboardMarkup(teclado, one_time_keyboard=True)
        )
        return

    # =========================
    # DEPORTE
    # =========================
    if user["estado"] == "deporte":

        user["deporte"] = texto

        # Guardar deporte base
        if "deporte_base" not in user["perfil"]:
            user["perfil"]["deporte_base"] = texto

        user["estado"] = "tiempo"

        await update.message.reply_text("⏱️ ¿Cuántos minutos tienes?")
        return

    # =========================
    # TIEMPO
    # =========================
    if user["estado"] == "tiempo":

        if not texto.isdigit():
            await update.message.reply_text("Pon un número (ej: 45)")
            return

        user["tiempo"] = int(texto)
        user["estado"] = "fatiga"

        await update.message.reply_text("😵 ¿Fatiga (0-10)?")
        return

    # =========================
    # FATIGA → GENERAR
    # =========================
    if user["estado"] == "fatiga":

        if not texto.isdigit():
            await update.message.reply_text("Pon un número del 0 al 10")
            return

        user["fatiga"] = int(texto)

        tipo = decidir_tipo_sesion(user)
        prompt = generar_prompt(user, tipo)
        respuesta = llamar_gpt(prompt)

        await update.message.reply_text(respuesta)

        actualizar_memoria(user, tipo, user["tiempo"])
        reset_user(user)

        return


# =========================
# RUN
# =========================
if __name__ == "__main__":

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar))

    print("🚀 Bot funcionando...")
    app.run_polling()
