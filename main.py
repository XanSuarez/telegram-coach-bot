import os
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI

TOKEN = os.getenv("TOKEN")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

user_db = {}

def get_user(user_id):
    if user_id not in user_db:
        user_db[user_id] = {
            "historial": [],
            "ultimo_entreno": None,
            "estado": None,
            "datos_temp": {}
        }
    return user_db[user_id]

# -------------------------
# LÓGICA ENTRENAMIENTO
# -------------------------
def calcular_carga(historial):
    return sum([s["duracion"] for s in historial[-3:]])

def intensidad_reciente(historial):
    for s in reversed(historial[-2:]):
        if s["tipo"] in ["vo2", "umbral"]:
            return True
    return False

def decidir(fatiga, historial):
    carga = calcular_carga(historial)
    intensidad = intensidad_reciente(historial)

    if fatiga >= 8 or carga > 180:
        return "suave", "movilidad"

    if fatiga >= 6:
        return ("aerobico","suave") if intensidad else ("tempo","aerobico")

    if fatiga >= 4:
        return ("aerobico","tempo") if intensidad else ("umbral","tempo")

    return ("tempo","aerobico") if intensidad else ("vo2","umbral")

# -------------------------
# SESIONES
# -------------------------
def sesion_bici(tipo, t):
    if tipo=="suave": return f"{t}’ Z1-Z2"
    if tipo=="aerobico": return f"{t}’ Z2"
    if tipo=="tempo": return "20’ + 3x12’ tempo + 10’"
    if tipo=="umbral": return "15’ + 3x10’ FTP + 10’"
    if tipo=="vo2": return "15’ + 6x3’ fuerte + 10’"

def sesion_run(tipo, t):
    if tipo=="suave": return f"{t}’ suave"
    if tipo=="aerobico": return f"{t}’ Z2"
    if tipo=="tempo": return "10’ + 2x10’ tempo + 10’"
    if tipo=="umbral": return "10’ + 3x8’ umbral + 10’"
    if tipo=="vo2": return "10’ + 5x3’ fuerte + 10’"

# -------------------------
# GPT
# -------------------------
def preguntar_gpt(msg, user):
    ctx = user.get("ultimo_entreno")

    contexto = f"""
Fatiga: {ctx['fatiga']}/10
Tipo: {ctx['tipo']}
Carga: {ctx['carga']}
""" if ctx else ""

    r = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role":"system","content":"Eres entrenador experto en triatlón"},
            {"role":"user","content":contexto + "\n\n" + msg}
        ]
    )
    return r.choices[0].message.content

def es_pregunta(t):
    return any(x in t for x in ["?", "por", "como", "que"])

# -------------------------
# FLUJO
# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    user["estado"] = "deporte"

    teclado = [["Running","Bici"]]

    await update.message.reply_text(
        "🏃‍♂️ ¿Qué vas a entrenar?",
        reply_markup=ReplyKeyboardMarkup(teclado, one_time_keyboard=True)
    )

async def manejar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    texto = update.message.text.lower()

    # 👉 GPT conversación
    if es_pregunta(texto):
        r = preguntar_gpt(texto, user)
        await update.message.reply_text(r)
        return

    # -------------------------
    # ESTADOS
    # -------------------------

    if user["estado"] == "deporte":
        user["datos_temp"]["deporte"] = texto
        user["estado"] = "tiempo"

        teclado = [["30","45","60"],["90","120"]]

        await update.message.reply_text(
            "⏱ ¿Cuánto tiempo?",
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

        tipo1, tipo2 = decidir(fatiga, user["historial"])

        if "bici" in deporte:
            s1 = sesion_bici(tipo1, tiempo)
            s2 = sesion_bici(tipo2, tiempo)
        else:
            s1 = sesion_run(tipo1, tiempo)
            s2 = sesion_run(tipo2, tiempo)

        user["historial"].append({"tipo": tipo1, "duracion": tiempo})

        user["ultimo_entreno"] = {
            "fatiga": fatiga,
            "tipo": tipo1,
            "carga": calcular_carga(user["historial"])
        }

        user["estado"] = None

        await update.message.reply_text(
            f"""📊 Fatiga: {fatiga}/10

🎯 {tipo1.upper()}
{s1}

🔁 Alternativa:
{tipo2.upper()}
{s2}

💡 Si no te ves bien → Z2""",
            reply_markup=ReplyKeyboardRemove()
        )

# -------------------------
# APP
# -------------------------
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT, manejar))

app.run_polling()
