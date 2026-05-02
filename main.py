import os
import random
import logging
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

logging.basicConfig(level=logging.INFO)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

DEPORTE, METRICA_BICI, TIEMPO, FATIGA, FEEDBACK = range(5)

# =========================
# DECISIÓN ENTRENAMIENTO
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

# =========================
# GENERADOR REAL (TU ESTILO)
# =========================
def generar_sesion(user):

    deporte = user["deporte"]
    tipo = decidir_tipo(user)
    tiempo = user["tiempo"]

    # ================= RUNNING =================
    if deporte == "running":

        if tipo == "aerobico":
            return f"{tiempo}’ Z2 + 5x20'' técnica"

        if tipo == "tempo":
            return f"15' + 3x8' Z3 (rec 2') + 10'"

        if tipo == "intensidad":
            return f"15' + {random.choice(['6x3’ Z4', '8x2’ Z5'])} + 10'"

        if tipo == "recuperacion":
            return f"{tiempo}’ Z1 + movilidad"

    # ================= BICI =================
    if deporte == "bici":

        if tipo == "aerobico":
            return f"{tiempo}’ Z2 + 5x1’ cadencia alta"

        if tipo == "tempo":
            return f"20’ + 3x10’ Z3 (rec 3’) + 10’"

        if tipo == "intensidad":
            return f"15’ + 5x4’ Z4 (rec 3’) + 10’"

        if tipo == "recuperacion":
            return f"{tiempo}’ Z1 cadencia alta"

    # ================= NATACIÓN =================
    if deporte == "natacion":

        if tipo == "aerobico":
            return "300 + 6x50 técnica + 8x100 Z2 (rec 15'') + 200"

        if tipo == "tempo":
            return "300 + 5x200 Z3 (rec 20'') + 100"

        if tipo == "intensidad":
            return "300 + 10x100 Z4 (rec 20'') + 100"

        if tipo == "recuperacion":
            return "200 + 6x50 técnica + 200"

# =========================
# PROMPT GPT (CONTROLADO)
# =========================
def generar_prompt(user, base):

    extra = ""

    if user["deporte"] == "bici":

        if user.get("metrica_bici") == "potencia":
            extra = """
Usa %FTP:
Z1 <55%
Z2 56-75%
Z3 76-90%
Z4 91-105%
Z5 >106%
"""

        else:
            extra = """
Usa %FCmax:
Z1 <75%
Z2 76-80%
Z3 81-85%
Z4 86-91%
Z5 >92%
"""

    return f"""
Eres entrenador experto en triatlón.

Sesión base:
{base}

Condiciones:
- Tiempo disponible: {user["tiempo"]}
- Fatiga: {user["fatiga"]}

{extra}

REGLAS:
- NO inventar otro entrenamiento distinto
- SOLO mejorar estructura y explicación
- NO mezclar deportes
- Running/Bici → tiempo
- Natación → metros
- Usar zonas Z1-Z5
- Añadir emojis

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
        temperature=0.7
    )
    return response.choices[0].message.content

# =========================
# HANDLERS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data.clear()
    context.user_data["tendencia"] = "neutral"

    teclado = [["Running", "Bici", "Natación"]]

    await update.message.reply_text(
        "👋 XS Coach\n\n🏃‍♂️ ¿Qué vas a entrenar hoy?",
        reply_markup=ReplyKeyboardMarkup(teclado, resize_keyboard=True)
    )
    return DEPORTE

async def deporte(update: Update, context: ContextTypes.DEFAULT_TYPE):

    texto = update.message.text.lower()
    context.user_data["deporte"] = texto

    if "bici" in texto:
        teclado = [["Potencia", "Frecuencia cardiaca"]]
        await update.message.reply_text(
            "⚙️ ¿Cómo quieres trabajar?\n👉 Esto define cómo te marco las zonas",
            reply_markup=ReplyKeyboardMarkup(teclado, resize_keyboard=True)
        )
        return METRICA_BICI

    await update.message.reply_text("⏱️ ¿Cuánto tiempo tienes hoy?")
    return TIEMPO

async def metrica(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if "potencia" in update.message.text.lower():
        context.user_data["metrica_bici"] = "potencia"
    else:
        context.user_data["metrica_bici"] = "fc"

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
        await update.message.reply_text("Pon número 0-10")
        return FATIGA

    context.user_data["fatiga"] = int(update.message.text)

    base = generar_sesion(context.user_data)
    prompt = generar_prompt(context.user_data, base)
    respuesta = llamar_gpt(prompt)

    await update.message.reply_text(respuesta)

    await update.message.reply_text(
        "📊 Valora la sesión (0-5)\n0 muy fácil / 5 muy duro"
    )

    return FEEDBACK

async def feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message.text.isdigit():
        return FEEDBACK

    val = int(update.message.text)

    if val >= 4:
        context.user_data["tendencia"] = "muy_duro"
    elif val <= 1:
        context.user_data["tendencia"] = "muy_facil"
    else:
        context.user_data["tendencia"] = "neutral"

    await update.message.reply_text("✅ Ajustado para próximas sesiones")

    return ConversationHandler.END

# =========================
# RUN
# =========================
if __name__ == "__main__":

    app = ApplicationBuilder().token(os.getenv("TOKEN")).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            DEPORTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, deporte)],
            METRICA_BICI: [MessageHandler(filters.TEXT & ~filters.COMMAND, metrica)],
            TIEMPO: [MessageHandler(filters.TEXT & ~filters.COMMAND, tiempo)],
            FATIGA: [MessageHandler(filters.TEXT & ~filters.COMMAND, fatiga)],
            FEEDBACK: [MessageHandler(filters.TEXT & ~filters.COMMAND, feedback)],
        },
        fallbacks=[],
        allow_reentry=True
    )

    app.add_handler(conv)

    print("🚀 XS Coach PRO funcionando")
    app.run_polling()

