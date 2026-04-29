import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("TOKEN")

# -------------------------
# PARSEO INPUT
# -------------------------
def parse_input(texto):
    texto = texto.lower()

    deporte = "running"
    if "bici" in texto or "bike" in texto:
        deporte = "bici"
    elif "swim" in texto or "natacion" in texto:
        deporte = "swim"

    tiempo = 45
    for t in texto.split():
        if "min" in t:
            try:
                tiempo = int(t.replace("min",""))
            except:
                pass

    fatiga = 5
    for t in texto.split():
        if t.isdigit():
            f = int(t)
            if 0 <= f <= 10:
                fatiga = f

    tipo = "aerobico"
    if "umbral" in texto:
        tipo = "umbral"
    elif "vo2" in texto:
        tipo = "vo2"
    elif "tempo" in texto:
        tipo = "tempo"

    nivel = "medio"
    if "principiante" in texto:
        nivel = "principiante"
    elif "avanzado" in texto:
        nivel = "avanzado"

    return deporte, tiempo, fatiga, tipo, nivel


# -------------------------
# AJUSTE POR FATIGA
# -------------------------
def ajustar_por_fatiga(tipo, fatiga):
    if fatiga >= 8:
        return "suave"
    elif fatiga >= 6 and tipo in ["vo2"]:
        return "umbral"
    return tipo


# -------------------------
# GENERADOR SESIONES
# -------------------------
def generar_running(tiempo, tipo, nivel):

    if tipo == "suave":
        return f"""🏃 Rodaje regenerativo

⏱ {tiempo} min suaves (Z1-Z2)

💡 Enfocado en recuperación"""

    if tipo == "umbral":
        if tiempo < 40:
            bloques = "2x8'"
        elif tiempo < 60:
            bloques = "3x8'"
        else:
            bloques = "3x10'"

        return f"""🏃 Umbral

10’ suave
{bloques} a ritmo umbral (rec 2’)
10’ suave"""

    if tipo == "vo2":
        return f"""🏃 VO2max

10’ suave
5x3’ fuerte (rec 2’)
10’ suave"""

    return f"""🏃 Aeróbico

{tiempo} min Z2 continuo"""


def generar_bici(tiempo, tipo, nivel):

    if tipo == "suave":
        return f"""🚴 Rodaje suave

⏱ {tiempo} min Z1-Z2"""

    if tipo == "umbral":
        return f"""🚴 Umbral

15’ warmup
3x10’ FTP (rec 5’)
10’ cooldown"""

    if tipo == "vo2":
        return f"""🚴 VO2max

15’ warmup
6x3’ alta intensidad (rec 3’)
10’ suave"""

    return f"""🚴 Aeróbico

{tiempo} min Z2"""


def generar_swim(tiempo, tipo, nivel):

    return f"""🏊 Natación

400 suave
6x100 técnica
8x100 aeróbico medio
200 suave"""


# -------------------------
# RESPUESTA FINAL
# -------------------------
def generar_sesion(texto):

    deporte, tiempo, fatiga, tipo, nivel = parse_input(texto)

    tipo = ajustar_por_fatiga(tipo, fatiga)

    if deporte == "running":
        sesion = generar_running(tiempo, tipo, nivel)
    elif deporte == "bici":
        sesion = generar_bici(tiempo, tipo, nivel)
    else:
        sesion = generar_swim(tiempo, tipo, nivel)

    return f"""📊 Datos detectados:
- Deporte: {deporte}
- Tiempo: {tiempo} min
- Fatiga: {fatiga}/10
- Objetivo: {tipo}

----------------------

{sesion}
"""


# -------------------------
# TELEGRAM
# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hola 👋 Soy tu entrenador PRO\n\n"
        "Ejemplo:\n"
        "running 45min umbral fatiga 5 nivel medio"
    )


async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    respuesta = generar_sesion(texto)
    await update.message.reply_text(respuesta)


app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT, responder))

app.run_polling()
