from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InputFile
from aiogram.utils import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
import os
import shutil
import mimetypes
from PIL import Image
import zipfile
from mutagen.id3 import ID3, TIT2, TPE1, APIC, ID3NoHeaderError
from mutagen.mp3 import MP3
import subprocess
from dotenv import load_dotenv

load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

# Состояния
class SongState(StatesGroup):
    waiting_for_mp3 = State()
    waiting_for_cover = State()
    waiting_for_artist = State()
    waiting_for_title = State()

# Кнопка
start_keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
start_keyboard.add(KeyboardButton("Отправить песню"))

# Папка для временных файлов
os.makedirs("temp", exist_ok=True)

@dp.message_handler(commands=['start'])
@dp.message_handler(lambda message: message.text == "Отправить песню")
async def start_handler(message: types.Message):
    await message.answer("Пожалуйста, отправьте MP3-файл.", reply_markup=start_keyboard)
    await SongState.waiting_for_mp3.set()

@dp.message_handler(content_types=types.ContentType.AUDIO, state=SongState.waiting_for_mp3)
async def handle_mp3(message: types.Message, state: FSMContext):
    file_path = f"temp/{message.from_user.id}_input.mp3"
    await message.audio.download(destination_file=file_path)
    await state.update_data(mp3_path=file_path)
    await message.answer("Теперь отправьте обложку (изображение PNG или JPG).")
    await SongState.waiting_for_cover.set()

@dp.message_handler(content_types=[types.ContentType.PHOTO, types.ContentType.DOCUMENT], state=SongState.waiting_for_cover)
async def handle_cover(message: types.Message, state: FSMContext):
    if message.photo:
        photo = message.photo[-1]
    else:
        photo = message.document

    cover_path = f"temp/{message.from_user.id}_cover.jpg"
    await photo.download(destination_file=cover_path)
    await state.update_data(cover_path=cover_path)
    await message.answer("Введите имя исполнителя:")
    await SongState.waiting_for_artist.set()

@dp.message_handler(state=SongState.waiting_for_artist)
async def handle_artist(message: types.Message, state: FSMContext):
    await state.update_data(artist=message.text)
    await message.answer("Теперь введите название песни:")
    await SongState.waiting_for_title.set()

@dp.message_handler(state=SongState.waiting_for_title)
async def handle_title(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    artist = user_data['artist']
    title = message.text
    mp3_path = user_data['mp3_path']
    cover_path = user_data['cover_path']

    output_mp3_path = f"temp/{message.from_user.id}_output.mp3"
    output_zip_path = f"temp/{artist} - {title}.zip"

    shutil.copy(mp3_path, output_mp3_path)

    # Вставляем теги и обложку с mutagen
    audio = MP3(output_mp3_path, ID3=ID3)
    try:
        if audio.tags is None:
            audio.add_tags()

    except ID3NoHeaderError:
        pass

    audio.tags.add(TIT2(encoding=3, text=title))
    audio.tags.add(TPE1(encoding=3, text=artist))

    with open(cover_path, "rb") as img:
        audio.tags.add(
            APIC(
                encoding=3,
                mime='image/jpeg',  # Лучше использовать JPEG
                type=3,
                desc='Cover',
                data=img.read()
            )
        )

    audio.save()

    # Архивируем mp3
    with zipfile.ZipFile(output_zip_path, 'w') as zipf:
        zipf.write(output_mp3_path, arcname=f"{artist} - {title}.mp3")

    # Отправляем архив
    await bot.send_document(
        chat_id=message.chat.id,
        document=InputFile(output_zip_path),
        caption="✅ Готово! В ZIP-архиве находится MP3 с обложкой. После распаковки обложка будет видна."
    )

    # Очистка
    for path in [mp3_path, cover_path, output_mp3_path, output_zip_path]:
        if os.path.exists(path):
            os.remove(path)

    await message.answer("Хотите обработать ещё? Нажмите 'Отправить песню' или /start.", reply_markup=start_keyboard)
    await state.finish()

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)

# import threading
# import http.server
# import socketserver
# import os

# def run_dummy_server():
#     PORT = int(os.environ.get("PORT", 8080))
#     Handler = http.server.SimpleHTTPRequestHandler
#     with socketserver.TCPServer(("", PORT), Handler) as httpd:
#         httpd.serve_forever()

# threading.Thread(target=run_dummy_server).start()
