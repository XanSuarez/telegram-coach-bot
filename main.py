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
                {"role": "system", "content": "Eres un entrenador profesional de triatlón."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )

        return response.choices[0].message.content

    except Exception as e:
        print("❌ ERROR GPT:", e)
        return "⚠️ Error con GPT. Revisa tu cuota o API key."


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

    return f"""
Eres un entrenador de triatlón de alto nivel.

Genera UN entrenamiento COMPLETO, estructurado y profesional.

DATOS:
- Deporte: {user["deporte"]}
- Tiempo disponible: {user["tiempo"]} min
- Fatiga: {user["fatiga"]}/10
- Tipo sesión: {tipo}
- Métrica: {metrica}

REQUISITOS:
- Estructura clara con emojis
- Calentamiento
- Parte principal (series detalladas)
- Vuelta a la calma
- Explicación breve

IMPORTANTE:
- Usa zonas Z1-Z5
- Sé específico (NO genérico tipo "30 min natación")
- Incluye descansos, repeticiones y objetivos
- Nivel triatleta amateur competitivo

FORMATO:

📊 Contexto breve

🏁 Objetivo

🔥 Entrenamiento:
- Calentamiento:
- Bloque principal:
- Vuelta a la calma:

🔁 Alternativa

💡 Nota del entrenador
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
            "👋 Soy tu entrenador XS\n\nAntes de empezar:\n\n¿Con qué te guías?",
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
    # DETECTAR INTENCIÓN CON GPT
    # =========================
    if user["estado"] is None:

        prompt_intencion = f"""
El usuario ha dicho: "{texto}"

¿Está pidiendo un entrenamiento?

Responde SOLO SI o NO
"""

        decision = llamar_gpt(prompt_intencion).strip().upper()

        if "SI" in decision:

            if "metrica" not in user["perfil"]:
                user["estado"] = "metrica"

                teclado = [["Potencia", "Ritmo", "Frecuencia cardíaca"]]

                await update.message.reply_text(
                    "📊 ¿Cómo te guías normalmente?",
                    reply_markup=ReplyKeyboardMarkup(teclado, one_time_keyboard=True)
                )
                return

            user["estado"] = "deporte"

            teclado = [["Running", "Bici", "Natación"]]

            await update.message.reply_text(
                "💡 Para ajustar bien el entrenamiento:\n\n🏃‍♂️ ¿Qué vas a entrenar?",
                reply_markup=ReplyKeyboardMarkup(teclado, one_time_keyboard=True)
            )
            return

        # 👉 Conversación libre GPT
        respuesta = llamar_gpt(texto)
        await update.message.reply_text(respuesta)
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
        user["estado"] = "tiempo"

        await update.message.reply_text("⏱️ ¿Cuántos minutos tienes?")
        return

    # =========================
    # TIEMPO
    # =========================
    if user["estado"] == "tiempo":

        if not texto.isdigit():
            await update.message.reply_text("Pon solo un número (ej: 60)")
            return

        user["tiempo"] = int(texto)
        user["estado"] = "fatiga"

        await update.message.reply_text("😵 ¿Nivel de fatiga? (0-10)")
        return

    # =========================
    # FATIGA
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

    print("🚀 Bot corriendo...")
    app.run_polling()
