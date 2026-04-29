import os
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI

TOKEN = os.getenv("TOKEN")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# -------------------------
# BASE DE DATOS
# -------------------------
user_db = {}

def get_user(user_id):
    if user_id not in user_db:
        user_db[user_id] = {
            "historial": [],
            "ultimo_entreno": None,
            "estado": None,
            "datos_temp": {}
            "perfil": {}
        }
    return user_db[user_id]

def tiene_contexto(user):
    return user.get("ultimo_entreno") is not None

# -------------------------
# GPT (FORMATO PRO)
# -------------------------
def preguntar_gpt(msg, user):

    historial = user.get("historial", [])
    ultimo = user.get("ultimo_entreno")

    contexto = f"""
Eres un entrenador profesional de triatlón.

IMPORTANTE:
- NO generes entrenamientos si faltan datos
- Responde claro, estructurado y práctico
- Usa emojis para mejorar lectura
- Nada de texto largo tipo blog

Contexto atleta:
- Últimas sesiones: {[s["tipo"] for s in historial[-3:]]}
- Carga reciente: {sum([s["duracion"] for s in historial[-3:]])} min
- Último entreno: {ultimo}

Formato:

📊 Contexto breve

🎯 Respuesta / ajuste / explicación

🔁 Alternativa si aplica

💡 Nota breve
"""

    prompt = contexto + f"\n\nMensaje del atleta:\n{msg}"

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}]
        )

        return response.choices[0].message.content

    except Exception as e:
        print("ERROR GPT:", e)
        return "⚠️ Error conectando con el entrenador."

# -------------------------
# GENERAR ENTRENAMIENTO CON GPT
# -------------------------
def generar_entreno_gpt(user, deporte, tiempo, fatiga):

    historial = user.get("historial", [])
    carga = sum([s["duracion"] for s in historial[-3:]])
    metrica = user.get("perfil", {}).get("metrica", "fc")

    prompt = f"""
Eres un entrenador profesional de triatlón.

Genera SOLO un entrenamiento para HOY.

Datos:
- Deporte: {deporte}
- Tiempo: {tiempo} min
- Fatiga: {fatiga}/10
- Carga reciente: {carga}
- Últimas sesiones: {[s["tipo"] for s in historial[-3:]]}
- Métrica principal: {metrica}

REGLAS:
- Estructura clara
- No plan semanal
- Ajustar intensidad a fatiga
- Incluir descansos
- Añadir alternativa
Si la métrica es:
- potencia → usa %FTP o vatios
- ritmo → usa min/km
- fc → usa zonas de frecuencia cardiaca o RPE
Nunca mezcles métricas.
Si la fatiga es ≥7:
- Evita VO2, umbral o trabajo estructurado exigente
- Prioriza recuperación activa o rodaje muy suave
Si el atleta no usa potencia:
- NO uses FTP
- Usa zonas de frecuencia cardíaca o RPE

FORMATO:

📊 Fatiga: X/10

🎯 Entrenamiento:
- Calentamiento:
- Bloque principal:
- Vuelta a la calma:

🔁 Alternativa:

💡 Nota breve entrenador
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    return response.choices[0].message.content

# -------------------------
# START
# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)

    # 👇 SI NO TIENE MÉTRICA → preguntar primero
    if "metrica" not in user["perfil"]:
        user["estado"] = "metrica"

        teclado = [["Potencia","Ritmo","Frecuencia cardiaca"]]

        await update.message.reply_text(
            "⚙️ ¿Cómo sueles entrenar?",
            reply_markup=ReplyKeyboardMarkup(teclado, one_time_keyboard=True)
        )
        return

    user["estado"] = "deporte"
    ...

# -------------------------
# MANEJADOR PRINCIPAL
# -------------------------
async def manejar(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = get_user(update.effective_user.id)
    texto = update.message.text.lower()

    # -------------------------
    # 1. MÉTRICA (PRIMERO DE TODO)
    # -------------------------
    if user["estado"] == "metrica":

        if "potencia" in texto:
            user["perfil"]["metrica"] = "potencia"
        elif "ritmo" in texto:
            user["perfil"]["metrica"] = "ritmo"
        else:
            user["perfil"]["metrica"] = "fc"

        user["estado"] = "deporte"

        teclado = [["Running","Bici"]]

        await update.message.reply_text(
            "Perfecto 👌\n\n¿Qué vas a entrenar hoy?",
            reply_markup=ReplyKeyboardMarkup(teclado, one_time_keyboard=True)
        )
        return

    # -------------------------
    # 2. SIN PERFIL → PEDIR MÉTRICA
    # -------------------------
    if "metrica" not in user.get("perfil", {}):

        user["estado"] = "metrica"

        teclado = [["Potencia","Ritmo","Frecuencia cardiaca"]]

        await update.message.reply_text(
            "⚙️ ¿Cómo sueles entrenar?",
            reply_markup=ReplyKeyboardMarkup(teclado, one_time_keyboard=True)
        )
        return

    # -------------------------
    # 3. SIN CONTEXTO → INICIAR FLUJO
    # -------------------------
    if not tiene_contexto(user) and user["estado"] is None:

        user["estado"] = "deporte"

        teclado = [["Running", "Bici"]]

        await update.message.reply_text(
            "🏃‍♂️ Antes de recomendarte nada necesito algunos datos\n\n¿Qué vas a entrenar?",
            reply_markup=ReplyKeyboardMarkup(teclado, one_time_keyboard=True)
        )
        return

    # -------------------------
    # 4. FLUJO GUIADO
    # -------------------------
    if user["estado"] == "deporte":
        user["datos_temp"]["deporte"] = texto
        user["estado"] = "tiempo"

        teclado = [["30","45","60"],["90","120"]]

        await update.message.reply_text(
            "⏱ ¿Cuánto tiempo tienes?",
            reply_markup=ReplyKeyboardMarkup(teclado, one_time_keyboard=True)
        )
        return

    if user["estado"] == "tiempo":
        user["datos_temp"]["tiempo"] = int(texto)
        user["estado"] = "fatiga"

        teclado = [["1","2","3","4","5"],["6","7","8","9","10"]]

        await update.message.reply_text(
            "😵 ¿Nivel de fatiga?",
            reply_markup=ReplyKeyboardMarkup(teclado, one_time_keyboard=True)
        )
        return

    if user["estado"] == "fatiga":
        fatiga = int(texto)
        deporte = user["datos_temp"]["deporte"]
        tiempo = user["datos_temp"]["tiempo"]

        respuesta = generar_entreno_gpt(user, deporte, tiempo, fatiga)

        user["historial"].append({
            "tipo": "auto",
            "duracion": tiempo
        })

        user["ultimo_entreno"] = {
            "deporte": deporte,
            "tiempo": tiempo,
            "fatiga": fatiga
        }

        user["estado"] = None

        await update.message.reply_text(
            respuesta,
            reply_markup=ReplyKeyboardRemove()
        )
        return

    # -------------------------
    # 5. MODO CONVERSACIÓN (GPT)
    # -------------------------
    if user["estado"] is None:
        respuesta = preguntar_gpt(texto, user)
        await update.message.reply_text(respuesta)
        return

# -------------------------
# APP
# -------------------------
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT, manejar))

app.run_polling()
