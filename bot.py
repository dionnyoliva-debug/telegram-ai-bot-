"""Bot de Telegram con IA integrada.
Responde a todo lo que le escribas usando un modelo de IA gratuito.
"""

import asyncio
import logging
import os
import sys
import time
from threading import Thread

import requests
from flask import Flask
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
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")  # token de GitHub Models (gratis)
AI_URL = "https://models.github.ai/inference/chat/completions"
AI_MODEL = "openai/gpt-4o-mini"  # modelo rápido y con buen límite gratuito
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


# --- Servidor keep-alive (para que Replit no apague el bot) ---
keep_app = Flask("")


@keep_app.route("/")
def home():
    return "Bot activo"


def keep_alive():
    """Levanta un mini servidor web en segundo plano."""
    port = int(os.environ.get("PORT", 8080))
    Thread(
        target=lambda: keep_app.run(host="0.0.0.0", port=port),
        daemon=True,
    ).start()


def obtener_historial(chat_id: int):
    """Devuelve (o crea) el historial de un usuario."""
    if chat_id not in historial:
        historial[chat_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    return historial[chat_id]


def preguntar_ia(chat_id: int, texto_usuario: str) -> str:
    """Envía el mensaje a la IA junto con el historial y devuelve la respuesta."""
    if not GITHUB_TOKEN:
        raise RuntimeError(
            "Falta la variable GITHUB_TOKEN. Créala en GitHub y configúrala en el hosting."
        )
    mensajes = obtener_historial(chat_id)
    mensajes.append({"role": "user", "content": texto_usuario})

    # Recortar historial para no exceder el límite
    if len(mensajes) > MAX_HISTORY + 1:
        mensajes = [mensajes[0]] + mensajes[-MAX_HISTORY:]
        historial[chat_id] = mensajes

    # Reintentar hasta 3 veces ante fallos intermitentes
    ultimo_error = None
    for intento in range(3):
        try:
            resp = requests.post(
                AI_URL,
                headers={
                    "Authorization": f"Bearer {GITHUB_TOKEN}",
                    "Content-Type": "application/json",
                },
                json={"model": AI_MODEL, "messages": mensajes},
                timeout=90,
            )
            resp.raise_for_status()
            respuesta = resp.json()["choices"][0]["message"]["content"]
            mensajes.append({"role": "assistant", "content": respuesta})
            return respuesta
        except Exception as e:
            ultimo_error = e
            logging.warning("Intento %d fallido al consultar la IA: %s", intento + 1, e)
            time.sleep(3)
    raise ultimo_error


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
    global TOKEN
    if not TOKEN:
        if sys.stdin.isatty():
            # Solo en el teléfono: pedir el token por teclado
            TOKEN = input("Pega el token que te dio @BotFather: ").strip()
        else:
            # En un servidor no hay teclado: el token debe venir como variable
            raise RuntimeError(
                "Falta la variable de entorno TELEGRAM_TOKEN. "
                "Configúrala en tu hosting con el token de @BotFather."
            )
    if not TOKEN:
        raise RuntimeError("Necesitas el token de @BotFather para arrancar el bot.")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))
    logging.info("Bot iniciado. Esperando mensajes...")
    keep_alive()  # mini servidor para mantener el bot despierto en Replit
    app.run_polling()


if __name__ == "__main__":
    main()
