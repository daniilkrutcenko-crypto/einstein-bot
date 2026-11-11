import asyncio
import logging
import os
from random import choice

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from openai import AsyncOpenAI


TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
PROXYAPI_KEY = os.getenv("PROXYAPI_KEY")

SYSTEM_PROMPT = r"""
Ты — дружелюбный и любознательный образовательный помощник в образе Альберта
Эйнштейна. Просто и точно объясняй физику и другие научные идеи, используя
понятные примеры и аналогии. Будь терпеливым, доброжелательным и поддерживай
любознательность ученика.

Строго соблюдай правила:

1. Сократовский метод: Если ученик просит решить задачу, например по математике
или физике, НИКОГДА не давай готовый ответ сразу. Задай 1–2 наводящих вопроса,
которые помогут ему самому прийти к решению, затем дождись ответа.

Если ученик дает ПРАВИЛЬНЫЙ финальный ответ, обязательно подтверди, что он
молодец, и закончи решение. Не переспрашивай и не сомневайся в правильном ответе.
Ты отлично знаешь математику. Если ученик решил верно, соглашайся с ним.

2. Мысленный эксперимент: Объясняя сложные концепции, предлагай ученику
представить мысленный эксперимент, например: «Представь, что ты находишься
в падающем лифте…».

3. Личные привычки: Иногда, но не в каждом сообщении, естественно упоминай, что
любишь играть на скрипке, пить кофе или ходить под парусом. Не вставляй эти
детали, если они не подходят к разговору.

4. Форматирование: Обязательно используй подходящие тематические эмодзи
(⚛️, 🧪, 🔭, 🧠, 💡, 📐). Выделяй важные термины жирным с помощью *текст*.

5. Язык и формулы: Всегда отвечай только на русском языке, независимо от языка
вопроса. Переводи немецкие фразы на русский. НИКОГДА не используй LaTeX
(например, \frac или \rho). Записывай формулы простыми символами или Unicode,
например: ρ = m / V.
"""

MODEL = "gpt-4o-mini"
EINSTEIN_QUOTES = (
    "💡 *«Воображение важнее знания. Знание ограничено, а воображение охватывает весь мир».* — Альберт Эйнштейн",
    "🧠 *«Самая прекрасная и глубокая эмоция, которую мы можем испытать, — это чувство тайны».* — Альберт Эйнштейн",
    "⚛️ *«Бог не играет в кости».* — Альберт Эйнштейн",
)
RIDDLES = (
    "🧠 *Загадка:* Кот Шрёдингера: пока коробка закрыта, можно ли сказать, что он только жив или только мёртв? Почему?",
    "⚛️ *Загадка:* Если в безвоздушном космосе одновременно отпустить молоток и перо, какой предмет упадёт быстрее?",
    "🔭 *Загадка:* Свет звезды летел до Земли 100 лет. Ты видишь её такой, какая она сейчас, или такой, какой она была 100 лет назад?",
)
MAX_HISTORY_MESSAGES = 10
user_histories: dict[int, list[dict[str, str]]] = {}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

dispatcher = Dispatcher()
openai_client: AsyncOpenAI | None = None


def add_to_history(user_id: int, role: str, content: str) -> None:
    history = user_histories.setdefault(user_id, [])
    history.append({"role": role, "content": content})

    while len(history) > MAX_HISTORY_MESSAGES:
        history.pop(0)
    if history and history[0]["role"] == "assistant":
        history.pop(0)


def remember_static_exchange(message: Message, reply: str) -> None:
    if message.from_user is None:
        return

    user_id = message.from_user.id
    add_to_history(user_id, "user", message.text or "")
    add_to_history(user_id, "assistant", reply)


async def answer_safely(message: Message, text: str) -> None:
    try:
        await message.answer(text)
    except TelegramBadRequest as error:
        if "can't parse entities" not in str(error).lower():
            raise

        logger.warning("Telegram rejected message formatting; retrying as plain text.")
        await message.answer(text, parse_mode=None)


@dispatcher.message(CommandStart())
async def handle_start(message: Message) -> None:
    reply = (
        "Привет! Я — твой дружелюбный проводник в мир *физики* в духе Эйнштейна. 💡\n"
        "Что хочешь исследовать?"
    )
    remember_static_exchange(message, reply)
    await answer_safely(message, reply)


@dispatcher.message(Command("quote"))
async def handle_quote(message: Message) -> None:
    reply = choice(EINSTEIN_QUOTES)
    remember_static_exchange(message, reply)
    await answer_safely(message, reply)


@dispatcher.message(Command("riddle"))
async def handle_riddle(message: Message) -> None:
    reply = choice(RIDDLES)
    remember_static_exchange(message, reply)
    await answer_safely(message, reply)


@dispatcher.message()
async def handle_message(message: Message) -> None:
    if not message.text or message.from_user is None:
        return

    user_id = message.from_user.id
    add_to_history(user_id, "user", message.text)
    history = user_histories[user_id]

    try:
        client = openai_client
        if client is None:
            raise RuntimeError("The OpenAI-compatible client has not been initialized.")

        response = await client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, *history],
        )
        answer = response.choices[0].message.content
        answer = answer or "💡 *Интересный вопрос!* Переформулируй его, пожалуйста."
    except Exception:
        logger.exception("Failed to get a response from the OpenAI-compatible API")
        answer = (
            "🧪 *Проблема с лабораторией:* сейчас не удаётся подготовить ответ. "
            "Попробуй ещё раз немного позже."
        )

    add_to_history(user_id, "assistant", answer)
    await answer_safely(message, answer)


async def main() -> None:
    global openai_client

    if not TELEGRAM_TOKEN:
        raise RuntimeError(
            "Set the TELEGRAM_TOKEN environment variable before starting the bot."
        )
    if not PROXYAPI_KEY:
        raise RuntimeError(
            "Set the PROXYAPI_KEY environment variable before starting the bot."
        )

    openai_client = AsyncOpenAI(
        api_key=PROXYAPI_KEY,
        base_url="https://api.proxyapi.ru/openai/v1",
    )
    bot = Bot(
        token=TELEGRAM_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
