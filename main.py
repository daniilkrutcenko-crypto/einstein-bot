import asyncio
import logging
import os
from random import choice
from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from openai import AsyncOpenAI

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
PROXYAPI_KEY = os.getenv("PROXYAPI_KEY")

SYSTEM_PROMPT = """Ты — дружелюбный и любознательный образовательный помощник в образе Альберта Эйнштейна. Просто и точно объясняй физику и другие научные идеи, используя понятные примеры и аналогии. Будь терпеливым, доброжелательным и поддерживай любознательность ученика.

Строго соблюдай правила:

1. Сократовский метод: Если ученик просит решить задачу, например по математике или физике, НИКОГДА не давай готовый ответ сразу. Задай 1-2 наводящих вопроса, которые помогут ему самому прийти к решению. Если ученик дает ПРАВИЛЬНЫЙ финальный ответ, обязательно похвали его и закончи решение. Не переспрашивай и не сомневайся в правильном ответе. Ты отлично знаешь математику.

2. Мысленный эксперимент: Объясняя сложные концепции, предлагай ученику представить мысленный эксперимент (например: «Представь, что ты находишься в падающем лифте...»). ВАЖНО: Если ты задаешь ученику вопрос (в рамках эксперимента или наводящий), ОСТАНОВИ генерацию текста и дождись ответа ученика. Твоя реплика должна заканчиваться знаком вопроса.

3. Личные привычки: Иногда, но не в каждом сообщении, естественно упоминай, что любишь играть на скрипке, пить кофе или ходить под парусом.

4. Форматирование: Используй тематические эмодзи (⚛️, 🧪, 🔭, 🧠, 💡, 📐) и выделяй важные термины жирным шрифтом (через *текст*).

5. Отвечай ТОЛЬКО на русском языке. Переводы немецких фраз тоже давай на русском.

6. НИКОГДА не используй LaTeX. Пиши формулы простыми символами (например, ρ = m / V, E = mc², √x).

7. Физика космоса: В космосе вдали от планет гравитация есть, но она настолько слабая, что человек ее не чувствует (невесомость). Объясняй это правильно.
"""

user_histories = {}


async def main() -> None:
    if not TELEGRAM_TOKEN:
        raise RuntimeError(
            "Set the TELEGRAM_TOKEN environment variable before starting the bot."
        )
    if not PROXYAPI_KEY:
        raise RuntimeError(
            "Set the PROXYAPI_KEY environment variable before starting the bot."
        )

    bot = Bot(
        token=TELEGRAM_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    dp = Dispatcher()

    client = AsyncOpenAI(
        api_key=PROXYAPI_KEY,
        base_url="https://api.proxyapi.ru/openai/v1",
    )

    @dp.message(Command("start"))
    async def start_command(message: types.Message):
        if message.from_user is not None:
            user_histories[message.from_user.id] = []
        await message.answer(
            "Приветствую! Я — Альберт Эйнштейн. 🧪\nДавай разберемся с твоим вопросом. О чем хочешь узнать?"
        )

    @dp.message(Command("quote"))
    async def quote_command(message: types.Message):
        quotes = [
            "Воображение важнее знания. 💡",
            "Все мы гении. Но если вы будете судить рыбу по её способности взбираться на дерево, она проживёт всю жизнь, считая себя дурой. 🐟",
            "Образование — это то, что остаётся после того, как забывается всё выученное в школе. 🎓",
            "Если вы не можете объяснить что-то просто, значит, вы сами этого не понимаете. 🧠",
        ]
        await message.answer(choice(quotes))

    @dp.message(Command("riddle"))
    async def riddle_command(message: types.Message):
        riddles = [
            "Загадка: Свет звезды летел до Земли 100 лет. Ты видишь её такой, какая она сейчас, или такой, какой она была 100 лет назад? 🔭",
            "Загадка: Кот Шредингера: жив он или мертв, пока я на него не смотрю? 🐈",
            "Загадка: Если ты летишь со скоростью света и включаешь фары, что произойдет? 🚗",
        ]
        await message.answer(choice(riddles))

    @dp.message()
    async def handle_message(message: types.Message):
        if message.from_user is None:
            return

        user_id = message.from_user.id

        if user_id not in user_histories:
            user_histories[user_id] = []

        if message.text is None:
            return

        user_histories[user_id].append({"role": "user", "content": message.text})
        if len(user_histories[user_id]) > 10:
            user_histories[user_id] = user_histories[user_id][-10:]

        sent_message = await message.answer("Секунду, я делаю расчеты в блокноте... ✍️")

        try:
            messages_to_send = [
                {"role": "system", "content": SYSTEM_PROMPT}
            ] + user_histories[user_id]
            response = await client.chat.completions.create(
                model="gpt-4o-mini", messages=messages_to_send
            )
            answer = response.choices[0].message.content

            if answer is None:
                answer = "Ой, кажется, я потерял мысль..."

            user_histories[user_id].append({"role": "assistant", "content": answer})

            try:
                await sent_message.edit_text(answer, parse_mode="Markdown")
            except TelegramBadRequest:
                await sent_message.edit_text(answer)

        except Exception as e:
            logging.error(f"API error: {e}")
            await sent_message.edit_text(
                "Ой, кажется, я перепутал формулы. Ошибка в лаборатории."
            )

    logging.info("Бот-Эйнштейн запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
