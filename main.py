import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI

# -------------------------
# CONFIG
# -------------------------
TOKEN = os.getenv("TOKEN")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# -------------------------
# BASE DE DATOS SIMPLE
# -------------------------
user_db = {}

def get_user(user_id):
    if user_id not in user_db:
        user_db[user_id] = {"historial": []}
    return user_db[user_id]

# -------------------------
# CARGA E INTENSIDAD
# -------------------------
def calcular_carga(historial):
    return sum([s["duracion"] for s in historial[-3:]])

def intensidad_reciente(historial):
    for s in reversed(historial[-2:]):
        if s["tipo"] in ["vo2", "umbral"]:
            return True
    return False

# -------------------------
# DECISIÓN ENTRENAMIENTO
# -------------------------
def decidir_con_carga(fatiga, historial):

    carga = calcular_carga(historial)
    hubo_intensidad = intensidad_reciente(historial)

    if fatiga >= 8 or carga > 180:
        return "suave", "movilidad"

    if fatiga >= 6:
        if hubo_intensidad:
            return "aerobico", "suave"
        else:
            return "tempo", "aerobico"

    if fatiga >= 4:
        if hubo_intensidad:
            return "aerobico", "tempo"
        else:
            return "umbral", "tempo"

    if fatiga <= 3:
        if hubo_intensidad:
            return "tempo", "aerobico"
        else:
            return "vo2", "umbral"

# -------------------------
# SESIONES
# -------------------------
def sesion_running(tipo, tiempo):

    if tipo == "suave":
        return f"{tiempo}’ muy suave (Z1-Z2)"

    if tipo == "aerobico":
        return f"{tiempo}’ Z2 continuo"

    if tipo == "tempo":
        return "10’ + 2x10’ tempo (rec 2’) + 10’"

    if tipo == "umbral":
        return "10’ + 3x8’ umbral (rec 2’) + 10’"

    if tipo == "vo2":
        return "10’ + 5x3’ fuerte (rec 2’) + 10’"

    return "Rodaje libre"


def sesion_bici(tipo, tiempo):

    if tipo == "suave":
        return f"{tiempo}’ Z1-Z2"

    if tipo == "aerobico":
        return f"{tiempo}’ Z2"

    if tipo == "tempo":
        if tiempo >= 90:
            return "20’ + 3x12’ tempo (rec 4’) + 10’"
        else:
            return "15’ + 2x10’ tempo + 10’"

    if tipo == "umbral":
        if tiempo >= 90:
            return "15’ + 2x15’ FTP (rec 5’) + 10’"
        else:
            return "15’ + 3x8’ FTP + 10’"

    if tipo == "vo2":
        return "15’ + 6x3’ fuerte (rec 3’) + 10’"

    return "Salida libre"

# -------------------------
# GENERADOR FINAL
# -------------------------
def generar_entreno(deporte, tiempo, fatiga, user):

    tipo1, tipo2 = decidir_con_carga(fatiga, user["historial"])

    if deporte == "running":
        s1 = sesion_running(tipo1, tiempo)
        s2 = sesion_running(tipo2, tiempo)
    else:
        s1 = sesion_bici(tipo1, tiempo)
        s2 = sesion_bici(tipo2, tiempo)

    return f"""
📊 Análisis:
Fatiga: {fatiga}/10
Carga reciente: {calcular_carga(user["historial"])} min

🎯 Opción recomendada:
{tipo1.upper()}
{s1}

🔁 Alternativa:
{tipo2.upper()}
{s2}

💡 Si no te encuentras bien → pasa a Z2 continua
"""

# -------------------------
# GUARDAR SESIÓN
# -------------------------
def guardar_sesion(user, tipo, duracion):
    user["historial"].append({
        "tipo": tipo,
        "duracion": duracion
    })

# -------------------------
# CHATGPT
# -------------------------
def preguntar_gpt(mensaje):

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": "Eres un entrenador experto en triatlón y deportes de resistencia."
            },
            {
                "role": "user",
                "content": mensaje
            }
        ]
    )

    return response.choices[0].message.content

# -------------------------
# TELEGRAM
# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏃‍♂️ Entrenador XS PRO\n\n"
        "Respóndeme así:\n\n"
        "1. Deporte (running/bici)\n"
        "2. Tiempo (min)\n"
        "3. Fatiga (0-10)\n\n"
        "Ejemplo:\n"
        "running 45 6\n\n"
        "También puedes preguntarme dudas 😉"
    )


async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE):

    texto = update.message.text.lower()

    # 👉 modo conversación (ChatGPT)
    if "?" in texto or "por que" in texto or "explica" in texto:
        respuesta = preguntar_gpt(texto)
        await update.message.reply_text(respuesta)
        return

    # 👉 modo entrenamiento
    partes = texto.split()

    try:
        deporte = partes[0]
        tiempo = int(partes[1])
        fatiga = int(partes[2])

        user = get_user(update.effective_user.id)

        respuesta = generar_entreno(deporte, tiempo, fatiga, user)

        # guardamos sesión principal
        tipo1, _ = decidir_con_carga(fatiga, user["historial"])
        guardar_sesion(user, tipo1, tiempo)

    except:
        respuesta = "❌ Formato incorrecto.\nEjemplo: running 45 6"

    await update.message.reply_text(respuesta)


app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT, responder))

app.run_polling()
