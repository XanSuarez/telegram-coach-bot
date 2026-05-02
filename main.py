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

# Configuración básica de logs para ver errores en consola
logging.basicConfig(level=logging.INFO)

# Estados
DEPORTE, METRICA_BICI, TIEMPO, FATIGA, FEEDBACK = range(5)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --- HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Limpiamos datos previos si los hubiera
    context.user_data.clear()
    context.user_data['perfil'] = {"tendencia": "neutral", "metrica_bici": "fc"}
    
    teclado = [["Running", "Bici", "Natación"]]
    
    await update.message.reply_text(
        "👋 ¡Hola! Soy tu XS Coach.\n\n¿Qué deporte vas a entrenar hoy?",
        reply_markup=ReplyKeyboardMarkup(teclado, one_time_keyboard=True, resize_keyboard=True)
    )
    return DEPORTE

async def selecc_deporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text.lower()
    context.user_data['deporte'] = msg

    if "bici" in msg:
        teclado = [["Potencia", "Frecuencia cardíaca"]]
        await update.message.reply_text(
            "⚙️ ¿Qué métrica usas en la bici?", 
            reply_markup=ReplyKeyboardMarkup(teclado, one_time_keyboard=True, resize_keyboard=True)
        )
        return METRICA_BICI
    
    await update.message.reply_text(
        "⏱️ ¿Cuántos minutos tienes? (Ej: 60)", 
        reply_markup=ReplyKeyboardRemove()
    )
    return TIEMPO

async def selecc_metrica(update: Update, context: ContextTypes.DEFAULT_TYPE):
    metrica = "potencia" if "potencia" in update.message.text.lower() else "fc"
    context.user_data['perfil']['metrica_bici'] = metrica
    
    await update.message.reply_text("⏱️ ¿Cuántos minutos tienes para hoy?")
    return TIEMPO

async def selecc_tiempo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.text.isdigit():
        await update.message.reply_text("⚠️ Por favor, pon un número de minutos.")
        return TIEMPO
    
    context.user_data['tiempo'] = int(update.message.text)
    await update.message.reply_text("😵 ¿Nivel de fatiga actual? (0 al 10)")
    return FATIGA

async def generar_entrenamiento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.text.isdigit():
        await update.message.reply_text("⚠️ Pon un número del 0 al 10.")
        return FATIGA
    
    context.user_data['fatiga'] = int(update.message.text)
    
    await update.message.reply_text("🤖 Generando tu sesión personalizada... espera un momento.")
    
    # Aquí iría tu lógica de llamar_gpt(prompt)
    # Por ahora simulamos la respuesta:
    respuesta_ia = "✅ Sesión generada:\n\n15' Calentamiento Z1\n30' Bloques Z3\n15' Vuelta a la calma."
    
    await update.message.reply_text(respuesta_ia)
    await update.message.reply_text("📊 Valora la dificultad percibida (0-5) para ajustar tu próximo entrenamiento:")
    return FEEDBACK

async def feedback_final(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Guardar feedback y cerrar
    await update.message.reply_text("✅ Feedback guardado. ¡A darle caña!")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Entrenamiento cancelado. Usa /start cuando quieras volver.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# --- RUN ---

if __name__ == "__main__":
    TOKEN = os.getenv("TOKEN")
    if not TOKEN:
        print("❌ Error: No se encuentra el TOKEN en las variables de entorno.")
    else:
        app = ApplicationBuilder().token(TOKEN).build()

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
            # Importante: permite que /start reinicie la charla si el usuario se atasca
            allow_reentry=True 
        )

        app.add_handler(conv_handler)
        print("🚀 Bot funcionando...")
        app.run_polling()

