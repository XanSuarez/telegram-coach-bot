import os
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI

# =========================
# CONFIG
# =========================
TELEGRAM_TOKEN = os.getenv("TOKEN")  # En Railway: TOKEN
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TOKEN de Telegram no configurado")
if not OPENAI_API_KEY:
    raise ValueError("❌ OPENAI_API_KEY no configurado")

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
            "perfil": {},          # {"metrica": "...", "deporte_base": "..."}
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
    # Mantener últimas 5
    user["historial"] = user["historial"][-5:]


# =========================
# GPT
# =========================
def llamar_gpt(prompt: str) -> str:
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Eres un entrenador de triatlón experto. "
                        "Respondes de forma clara, estructurada y profesional."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.6
        )
        return response.choices[0].message.content
    except Exception as e:
        print("❌ ERROR GPT:", e)
        return "⚠️ Error con GPT (revisa cuota o API key)."


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

    # 🔒 Reglas de métrica (OBLIGATORIO)
    if metrica == "ritmo":
        regla_metrica = """
MÉTRICA (OBLIGATORIO):
- Usa RITMO (min/km)
- NO uses frecuencia cardiaca
- NO uses %FC
- NO uses potencia
- Puedes usar referencias: Z2, tempo, umbral, RPE
"""
    elif metrica == "potencia":
        regla_metrica = """
MÉTRICA (OBLIGATORIO):
- Usa POTENCIA (W o %FTP)
- NO uses frecuencia cardiaca
"""
    else:
        regla_metrica = """
MÉTRICA (OBLIGATORIO):
- Usa frecuencia cardiaca (zonas) o RPE
"""

    # 🏊 Regla natación
    regla_natacion = ""
    if "nat" in deporte_base:
        regla_natacion = """
NATACIÓN (OBLIGATORIO):
- Estructura SIEMPRE en METROS (NO minutos)
- Incluir técnica (pull, palas, pies, drills)
- Ejemplo: 200 + 4x50 + 6x100
"""

    return f"""
Eres un entrenador de alto nivel.

⚠️ REGLAS OBLIGATORIAS:
- SOLO entrenamiento de: {deporte_base}
- NO mezclar deportes
- NO triatlón combinado
- NO consejos genéricos
- Sesión estructurada y realista
- Evitar errores fisiológicos

{regla_metrica}
{regla_natacion}

DATOS:
- Tiempo disponible: {user["tiempo"]} min
- Fatiga: {user["fatiga"]}/10
- Tipo sesión: {tipo}

AJUSTE POR FATIGA:
- Si fatiga ≥7 → evitar alta intensidad, priorizar Z2 / controlado

FORMATO:

📊 Contexto  
(1-2 líneas coherentes con fatiga y objetivo)

🏁 Objetivo  

🔥 Entrenamiento  

🔹 Calentamiento  
(detallado)

🔹 Bloque principal  
(series claras, descansos, intensidades correctas)

🔹 Vuelta a la calma  

🔁 Alternativa  
(más suave o más dura)

💡 Nota entrenador  
(útil, concreta, no genérica)

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

    # Preguntar métrica solo una vez
    if "metrica" not in user["perfil"]:
        user["estado"] = "metrica"

        teclado = [["Potencia", "Ritmo", "Frecuencia cardíaca"]]

        await update.message.reply_text(
            "📊 Para ajustar bien la intensidad 👇\n\n¿Con qué te sueles guiar al entrenar?",
            reply_markup=ReplyKeyboardMarkup(teclado, one_time_keyboard=True)
        )
        return

    user["estado"] = "deporte"

    teclado = [["Running", "Bici", "Natación"]]

    await update.message.reply_text(
        "🏃‍♂️ Perfecto, vamos con hoy\n\n👉 ¿Qué vas a entrenar?",
        reply_markup=ReplyKeyboardMarkup(teclado, one_time_keyboard=True)
    )


# =========================
# MANEJADOR
# =========================
async def manejar(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = get_user(update.effective_user.id)
    texto = update.message.text.lower().strip()

    # =========================
    # FORZAR FLUJO SIEMPRE (si no estamos en flujo)
    # =========================
    if user["estado"] is None:

        # Si no tiene métrica → primero eso
        if "metrica" not in user["perfil"]:
            user["estado"] = "metrica"

            teclado = [["Potencia", "Ritmo", "Frecuencia cardíaca"]]

            await update.message.reply_text(
                "📊 Antes de empezar:\n\n¿Con qué te guías normalmente?",
                reply_markup=ReplyKeyboardMarkup(teclado, one_time_keyboard=True)
            )
            return

        # Si ya tiene métrica → iniciar flujo SIEMPRE
        user["estado"] = "deporte"

        teclado = [["Running", "Bici", "Natación"]]

        await update.message.reply_text(
            "💡 Para ajustar bien la sesión necesito 3 cosas:\n\n"
            "1️⃣ Deporte\n2️⃣ Tiempo disponible\n3️⃣ Fatiga\n\n"
            "👉 Empezamos:\n\n¿Qué vas a entrenar hoy?",
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
            "Perfecto 👌\n\n🏃‍♂️ ¿Qué vas a entrenar hoy?",
            reply_markup=ReplyKeyboardMarkup(teclado, one_time_keyboard=True)
        )
        return

    # =========================
    # DEPORTE
    # =========================
    if user["estado"] == "deporte":

        user["deporte"] = texto

        # Guardar deporte base si no existe
        if "deporte_base" not in user["perfil"]:
            user["perfil"]["deporte_base"] = texto

        user["estado"] = "tiempo"

        await update.message.reply_text(
            "⏱️ ¿Cuánto tiempo tienes hoy?\n\n(esto define el tipo de sesión)"
        )
        return

    # =========================
    # TIEMPO
    # =========================
    if user["estado"] == "tiempo":

        if not texto.isdigit():
            await update.message.reply_text("Pon solo un número (ej: 45)")
            return

        user["tiempo"] = int(texto)
        user["estado"] = "fatiga"

        await update.message.reply_text(
            "😵 ¿Cómo estás hoy de fatiga? (0-10)\n\n👉 Esto ajusta la carga"
        )
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
