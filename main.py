import os
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

# Configuración de Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Estados de la conversación
DEPORTE, METRICA_BICI, TIEMPO, FATIGA, FEEDBACK = range(5)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Estructura de plantillas unificada
PLANTILLAS = {
    "running": {
        "recuperacion": "Z1 continuo + técnica",
        "aerobico": "Z2 continuo",
        "tempo": "bloques Z3",
        "intensidad": "intervalos Z4-Z5"
    },
    "bici": {
        "recuperacion": "Z1 cadencia alta",
        "aerobico": "Z2 continuo",
        "tempo": "bloques Z3",
        "intensidad": "intervalos Z4"
    },
    "natación": {
        "recuperacion": "técnica + suave",
        "aerobico": "series largas Z2",
        "tempo": "series medias Z3",
        "intensidad": "series cortas Z4"
    }
}

# --- FUNCIONES DE LÓGICA ---

def decidir_tipo(fatiga, tendencia):
    if tendencia == "muy_duro" or fatiga >= 8: return "recuperacion"
    if fatiga >= 6: return "aerobico"
    if fatiga >= 4: return "tempo"
    return "intensidad"

# --- MANEJADORES DEL BOT ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Inicializamos datos del usuario en user_data (nativo de la librería)
    context.user_data['perfil'] = context.user_data.get('perfil', {"tendencia": "neutral", "metrica_bici": "fc"})
    
    teclado = [["Running", "Bici", "Natación"]]
    await update.message.reply_text(
        "👋 XS Coach\n¿Qué vamos a entrenar hoy?",
        reply_markup=ReplyKeyboardMarkup(teclado, one_time_keyboard=True, resize_keyboard=True)
    )
    return DEPORTE

async def selecc_deporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    deporte = update.message.text.lower()
    context.user_data['deporte'] = deporte

    if "bici" in deporte:
        teclado = [["Potencia", "Frecuencia cardíaca"]]
        await update.message.reply_text("⚙️ ¿Métrica en bici?", 
            reply_markup=ReplyKeyboardMarkup(teclado, one_time_keyboard=True, resize_keyboard=True))
        return METRICA_BICI
    
    await update.message.reply_text("⏱️ ¿Cuántos minutos tienes?", reply_markup=ReplyKeyboardRemove())
    return TIEMPO

async def selecc_metrica(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['perfil']['metrica_bici'] = "potencia" if "potencia" in update.message.text.lower() else "fc"
    await update.message.reply_text("⏱️ ¿Cuántos minutos tienes?", reply_markup=ReplyKeyboardRemove())
    return TIEMPO

async def selecc_tiempo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.text.isdigit():
        await update.message.reply_text("Por favor, introduce solo números.")
        return TIEMPO
    
    context.user_data['tiempo'] = int(update.message.text)
    await update.message.reply_text("😵 Fatiga actual (0-10):")
    return FATIGA

async def generar_entrenamiento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fatiga = int(update.message.text)
    ud = context.user_data
    
    tipo = decidir_tipo(fatiga, ud['perfil']['tendencia'])
    # Buscamos la plantilla de forma segura
    dep_key = "bici" if "bici" in ud['deporte'] else ("running" if "run" in ud['deporte'] else "natación")
    plantilla = PLANTILLAS[dep_key][tipo]

    # Generar prompt (puedes mantener tu lógica de reglas_extra aquí)
    # ... (omitido por brevedad, igual que tu función generar_prompt) ...
    
    await update.message.reply_text("⏳ Generando tu sesión...")
    
    # Llamada a GPT (Idealmente envuelto en un try/except)
    respuesta = "Aquí tienes tu sesión..." # respuesta = llamar_gpt(prompt)
    
    await update.message.reply_text(respuesta)
    await update.message.reply_text("📊 Valora el esfuerzo (0-5):\n0: Muy fácil | 5: Agotador")
    return FEEDBACK

async def feedback_final(update: Update, context: ContextTypes.DEFAULT_TYPE):
    valor = int(update.message.text)
    # Ajustar tendencia para la próxima sesión
    if valor >= 4: context.user_data['perfil']['tendencia'] = "muy_duro"
    elif valor <= 1: context.user_data['perfil']['tendencia'] = "muy_facil"
    else: context.user_data['perfil']['tendencia'] = "neutral"

    await update.message.reply_text("✅ Entendido. ¡Buen trabajo!")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Proceso cancelado.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

if __name__ == "__main__":
    app = ApplicationBuilder().token(os.getenv("TOKEN")).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            DEPORTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, selecc_deporte)],
            METRICA_BICI: [MessageHandler(filters.TEXT & ~filters.COMMAND, selecc_metrica)],
            TIEMPO: [MessageHandler(filters.TEXT & ~filters.COMMAND, selecc_tiempo)],
            FATIGA: [MessageHandler(filters.TEXT & ~filters.COMMAND, generar_entrenamiento)],
            FEEDBACK: [MessageHandler(filters.TEXT & ~filters.COMMAND, feedback_final)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.run_polling()

