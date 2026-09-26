"""Bot de Telegram con IA integrada.
Responde a todo lo que le escribas usando un modelo de IA gratuito.
"""

import asyncio
import logging
import os

import requests
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# --- Configuración ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")  # se configura en el hosting, no aquí
API_URL = "https://text.pollinations.ai/openai"  # API de IA gratuita, sin key
SYSTEM_PROMPT = (
    "Eres un asistente virtual amable, útil y directo. "
    "Respondes siempre en español neutro, de forma clara y sin rodeos."
)
MAX_HISTORY = 10  # cantidad de mensajes que recuerda por usuario

# Memoria de conversaciones: chat_id -> lista de mensajes
historial = {}

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)


def obtener_historial(chat_id: int):
    """Devuelve (o crea) el historial de un usuario."""
    if chat_id not in historial:
        historial[chat_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    return historial[chat_id]


def preguntar_ia(chat_id: int, texto_usuario: str) -> str:
    """Envía el mensaje a la IA junto con el historial y devuelve la respuesta."""
    mensajes = obtener_historial(chat_id)
    mensajes.append({"role": "user", "content": texto_usuario})

    # Recortar historial para no exceder el límite
    if len(mensajes) > MAX_HISTORY + 1:
        mensajes = [mensajes[0]] + mensajes[-MAX_HISTORY:]
        historial[chat_id] = mensajes

    resp = requests.post(
        API_URL,
        json={"model": "openai", "messages": mensajes},
        timeout=90,
    )
    resp.raise_for_status()
    respuesta = resp.json()["choices"][0]["message"]["content"]

    mensajes.append({"role": "assistant", "content": respuesta})
    return respuesta


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "¡Hola! Soy tu asistente IA. Escríbeme lo que quieras y te respondo.\n\n"
        "Comandos:\n"
        "/start - mostrar este mensaje\n"
        "/clear - borrar la conversación y empezar de cero"
    )


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    historial[update.effective_chat.id] = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]
    await update.message.reply_text("Conversación borrada. Empezamos de cero.")


async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    try:
        # requests es bloqueante: lo corremos en un hilo aparte
        respuesta = await asyncio.to_thread(preguntar_ia, chat_id, update.message.text)
    except Exception as e:
        logging.error("Error al consultar la IA: %s", e)
        respuesta = (
            "Tuve un problema al responder. Espera un momento e inténtalo de nuevo."
        )
    await update.message.reply_text(respuesta)


def main():
    if not TOKEN:
        raise RuntimeError(
            "Falta la variable de entorno TELEGRAM_TOKEN. "
            "Configúrala en el hosting con el token que te dio @BotFather."
        )
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))
    logging.info("Bot iniciado. Esperando mensajes...")
    app.run_polling()


if __name__ == "__main__":
    main()
