import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("TOKEN")

# -------------------------
# DECISIÓN ENTRENAMIENTO
# -------------------------
def decidir_tipo(fatiga, ayer_intensidad):

    if fatiga >= 8:
        return "suave", "movilidad"

    if fatiga >= 6:
        if ayer_intensidad:
            return "aerobico", "suave"
        else:
            return "umbral", "aerobico"

    if fatiga <= 5:
        if ayer_intensidad:
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
        return "15’ + 2x12’ tempo + 10’"

    if tipo == "umbral":
        return "15’ + 3x10’ FTP + 10’"

    if tipo == "vo2":
        return "15’ + 6x3’ fuerte + 10’"

    return "Salida libre"


# -------------------------
# GENERADOR FINAL
# -------------------------
def generar_entreno(deporte, tiempo, fatiga, ayer):

    tipo1, tipo2 = decidir_tipo(fatiga, ayer)

    if deporte == "running":
        s1 = sesion_running(tipo1, tiempo)
        s2 = sesion_running(tipo2, tiempo)
    else:
        s1 = sesion_bici(tipo1, tiempo)
        s2 = sesion_bici(tipo2, tiempo)

    return f"""
📊 Análisis:
Fatiga: {fatiga}/10
Ayer intensidad: {"Sí" if ayer else "No"}

🎯 Opción recomendada:
{tipo1.upper()}
{s1}

🔁 Alternativa:
{tipo2.upper()}
{s2}

💡 Ajustado automáticamente según carga reciente
"""


# -------------------------
# TELEGRAM
# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏃‍♂️ Entrenador XS\n\n"
        "Respóndeme así:\n\n"
        "1. Deporte (running/bici)\n"
        "2. Tiempo (min)\n"
        "3. Fatiga (0-10)\n"
        "4. Ayer intensidad (si/no)\n\n"
        "Ejemplo:\n"
        "running 45 6 si"
    )


async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.lower().split()

    try:
        deporte = texto[0]
        tiempo = int(texto[1])
        fatiga = int(texto[2])
        ayer = texto[3] == "si"

        respuesta = generar_entreno(deporte, tiempo, fatiga, ayer)

    except:
        respuesta = "❌ Formato incorrecto.\nEjemplo: running 45 6 si"

    await update.message.reply_text(respuesta)


app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT, responder))

app.run_polling()
