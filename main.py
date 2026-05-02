import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from openai import AsyncOpenAI

# ============================
# CONFIGURACIÓN
# ============================

TELEGRAM_TOKEN = os.getenv("TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

logging.basicConfig(level=logging.INFO)


# ============================
# SISTEMA DE SESIONES
# ============================

class UserSession:
    def __init__(self):
        self.deporte = None
        self.objetivo = None
        self.tiempo = None


class SessionManager:
    def __init__(self):
        self.sessions = {}

    def get(self, user_id):
        if user_id not in self.sessions:
            self.sessions[user_id] = UserSession()
        return self.sessions[user_id]

    def reset(self, user_id):
        self.sessions[user_id] = UserSession()


session_manager = SessionManager()


# ============================
# PLANTILLAS
# ============================

TEMPLATES = {
    "running": "Plan de running para {objetivo} con {tiempo} disponibles.",
    "bici": "Plan de ciclismo para {objetivo} con {tiempo} disponibles.",
    "natacion": "Plan de natación para {objetivo} con {tiempo} disponibles."
}


# ============================
# GENERADOR DE PROMPTS
# ============================

def generar_prompt(session: UserSession):
    base = TEMPLATES.get(session.deporte, "")

    return f"""
Eres un entrenador experto en deportes de resistencia.

{base.format(objetivo=session.objetivo, tiempo=session.tiempo)}

Genera un entrenamiento completo con esta estructura:

- Calentamiento
- Parte principal
- Vuelta a la calma
- Consejos técnicos
"""


# ============================
# CLIENTE GPT
# ============================

async def llamar_gpt(prompt: str):
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content

    except Exception as e:
        logging.error(f"Error en GPT: {e}")
        return "Hubo un error generando el entrenamiento. Inténtalo de nuevo."


# ============================
# HANDLERS
# ============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    session_manager.reset(user_id)

    await update.message.reply_text(
        "¡Hola! Soy tu entrenador de resistencia.\n"
        "Elige un deporte: running, bici o natación."
    )


async def manejar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    session = session_manager.get(user_id)
    text = update.message.text.lower()

    # Paso 1: elegir deporte
    if session.deporte is None:
        if text in ["running", "bici", "natacion"]:
            session.deporte = text
            await update.message.reply_text("Perfecto. ¿Cuál es tu objetivo?")
        else:
            await update.message.reply_text("Elige deporte: running, bici o natación.")
        return

    # Paso 2: objetivo
    if session.objetivo is None:
        session.objetivo = text
        await update.message.reply_text("¿Cuánto tiempo tienes hoy?")
        return

    # Paso 3: tiempo
    if session.tiempo is None:
        session.tiempo = text

        prompt = generar_prompt(session)
        respuesta = await llamar_gpt(prompt)

        await update.message.reply_text(respuesta)

        session_manager.reset(user_id)
        return


# ============================
# INICIO DEL BOT
# ============================

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar))

    app.run_polling()


if __name__ == "__main__":
    main()

