"""
SO'Z TARJIMASI TELEGRAM BOTI
-----------------------------
O'rnatish:
    pip install "python-telegram-bot[job-queue]" --upgrade

Ishga tushirish:
    1. Telegramda @BotFather ga yozing -> /newbot -> nom bering -> TOKEN oling
       (Agar avvalgi tokeningiz biror joyda oshkor bo'lgan bo'lsa, BotFather'da
       "Revoke current token" qilib, YANGI token oling!)
    2. Tokenni muhit o'zgaruvchisi orqali bering (kodga yozmang):

         Linux/macOS:
             export BOT_TOKEN="sizning_tokeningiz"
             python tarjima_bot.py

         Windows (PowerShell):
             $env:BOT_TOKEN="sizning_tokeningiz"
             python tarjima_bot.py

    3. Do'stlaringizga botingiz linkini yuboring (masalan t.me/SizningBotUsername)

Har bir chat (shaxsiy yoki guruh) uchun o'yin holati alohida saqlanadi
(context.chat_data orqali) VA diskka yoziladi (bot_persistence.pkl fayliga),
shuning uchun:
  - Bir nechta do'stingiz yoki guruh bir vaqtning o'zida bemalol o'ynashi mumkin;
  - Foydalanuvchi botdan chiqib qayta kirsa — qoldirgan joyidan davom etadi;
  - Botni qayta ishga tushirsangiz ham (server qayta yuklansa ham),
    hech kimning taraqqiyoti yo'qolmaydi.

Bosh sahifaga (0-so'zdan) qaytib, taraqqiyotni butunlay bekor qilish uchun
/reset buyrug'i beriladi — bu bot tasodifan bosilib ketmasligi uchun avval
maxsus so'zni ("BOSHIDAN") kiritib tasdiqlashni so'raydi.
"""

import os
import re
import random
import asyncio
import logging
from urllib.parse import quote
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    PicklePersistence,
    filters,
)

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

# Taraqqiyotni bosh sahifaga qaytarish uchun kiritilishi shart bo'lgan maxsus so'z
RESET_KEYWORD = "boshidan"
# O'yinni to'xtatib turish uchun istalgan payt yozilishi mumkin bo'lgan maxsus so'z
STOP_KEYWORD = "stop"
# Holatni diskda saqlaydigan fayl (bot qayta ishga tushsa ham taraqqiyot yo'qolmasligi uchun)
PERSISTENCE_FILE = "bot_persistence.pkl"

# ---- Mem ovozli xabarlar (ixtiyoriy) ----
# Ushbu papkaga tegishli .ogg fayllarni joylashtirsangiz, bot ularni avtomatik yuboradi.
# Fayl topilmasa, bot xatosiz davom etadi (ovozsiz).
SOUNDS_DIR = "sounds"
SOUND_FAIL_FILENAME = "block_fail.ogg"       # 10 tadan 5 ta yoki undan kam to'g'ri bo'lsa
SOUND_PERFECT_FILENAME = "block_perfect.ogg"  # 10 tadan 10 ta to'g'ri bo'lsa
FAIL_THRESHOLD = 5  # shu sondan kam yoki teng bo'lsa "fail" ovozi/matni yuboriladi

# Audio fayllar hali qo'shilmagan bo'lsa ham, mem gaplari matn sifatida chiqib turadi.
# Keyinchalik /mnt/.../sounds papkasiga tegishli .ogg fayllarni qo'ysangiz,
# ular ushbu matn bilan BIRGA ovozli xabar sifatida ham yuboriladi.
MEME_FAIL_TEXT = "A uka, chichvording endi! 😂"
MEME_PERFECT_TEXT = "Odamlariyam aqlliroq ekan, og'a, bu yerdi! 🔥"



def normalize(text: str) -> str:
    """Javobni solishtirish uchun standartlashtiradi: kichik harf,
    ortiqcha bo'shliqlar, tinish belgilari va apostrof turlarini bir xillaydi."""
    text = text.strip().lower()
    text = text.rstrip(".,!?;: ")
    for ch in ["’", "‘", "ʻ", "`", "´"]:
        text = text.replace(ch, "'")
    return text


def strip_clarifier(translation: str) -> str:
    """Tarjimadagi qavs ichidagi izohni ('burchak (joy)' -> 'burchak') olib tashlaydi"""
    return re.sub(r"\s*\([^)]*\)", "", translation).strip()


def is_answer_correct(user_text: str, correct_translation: str) -> bool:
    """Foydalanuvchi javobini tarjima bilan solishtiradi. Agar tarjimada qavs ichida
    qo'shimcha izoh bo'lsa ('burchak (joy)'), izohsiz asosiy so'z ('burchak') ham
    to'g'ri javob sifatida qabul qilinadi."""
    user_norm = normalize(user_text)
    full_norm = normalize(correct_translation)
    core_norm = normalize(strip_clarifier(correct_translation))
    return user_norm in {full_norm, core_norm}

# ================== TOKEN ==================
# Token endi kodda emas — muhit o'zgaruvchisidan olinadi.
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError(
        "BOT_TOKEN muhit o'zgaruvchisi topilmadi.\n"
        "Iltimos, botni ishga tushirishdan oldin uni belgilang, masalan:\n"
        '  export BOT_TOKEN="sizning_tokeningiz"   (Linux/macOS)\n'
        '  $env:BOT_TOKEN="sizning_tokeningiz"     (Windows PowerShell)'
    )
# ============================================

# ================== SO'ZLAR RO'YXATI ==================
WORDS = {
    "apple": "olma",
    "book": "kitob",
    "house": "uy",
    "water": "suv",
    "friend": "do'st",
    "school": "maktab",
    "sun": "quyosh",
    "love": "sevgi",
    "table": "stol",
    "window": "deraza",
    "name": "ism",
    "city": "shahar",
    "computer": "kompyuter",
    "language": "til",
    "music": "musiqa",
    "family": "oila",
    "car": "mashina",
    "food": "ovqat",
    "time": "vaqt",
    "money": "pul",
    "happiness": "baxt",
    "dream": "orzu",
    "journey": "sayohat",
    "adventure": "sarguzasht",
    "knowledge": "bilim",
    "health": "sog'lik",
    "freedom": "erkinlik",
    "peace": "tinchlik",
    "friendship": "do'stlik",
    "myself": "o'zim",
    "place": "joy",
    "world": "dunyo",
    "plate": "tovoq",
    "chair": "stul",
    "door": "eshik",
    "floor": "pol",
    "ceiling": "shift",
    "wall": "devor",
    "roof": "tom",
    "garden": "bog'",
    "flower": "gul",
    "tree": "daraxt",
    "river": "daryo",
    "mountain": "tog'",
    "sea": "dengiz",
    "ocean": "okean",
    "sky": "osmon",
    "star": "yulduz",
    "moon": "oy",
    "cloud": "bulut",
    "rain": "yomg'ir",
    "snow": "qor",
    "wind": "shamol",
    "storm": "bo'ron",
    "lightning": "chaqmoq",
    "thunder": "momaqaldiroq",
    "fire": "olov",
    "earth": "yer",
    "air": "havo",
    "space": "kosmos",
    "planet": "sayyora",
    "father": "ota",
    "mother": "ona",
    "brother": "aka",
    "sister": "opa",
    "uncle": "amaki",
    "aunt": "xola",
    "cousin": "amakivachcha",
    "grandfather": "bobo",
    "grandmother": "buvi",
    "baby": "chaqaloq",
    "child": "bola",
    "teenager": "o'smir",
    "adult": "katta",
    "elderly": "keksa",
    "afraid": "qo'rqqan",
    "brave": "jasur",
    "happy": "baxtli",
    "sad": "xafa",
    "angry": "g'azablangan",
    "surprised": "hayratlangan",
    "tired": "charchagan",
    "hungry": "och",
    "thirsty": "chanqoq",
    "aggressive": "hujumkor",
    "calm": "sokin",
    "confident": "o'ziga ishongan",
    "curious": "qiziquvchan",
    "friendly": "do'stona",
    "generous": "saxiy",
    "honest": "halol",
    "kind": "mehribon",
    "lazy": "dangasa",
    "polite": "odobli",
    "rude": "beodob",
    "selfish": "o'zini o'ylaydigan",
    "smart": "aqilli",
    "stubborn": "qaysar",
    "thoughtful": "o'ylab qiladigan",
    "trustworthy": "ishonchli",
    "chemical": "kimyoviy",
    "physical": "jismoniy",
    "biological": "biologik",
    "mathematical": "matematik",
    "historical": "tarixiy",
    "geographical": "geografik",
    "political": "siyosiy",
    "economic": "iqtisodiy",
    "climatic": "iqlimiy",
    "cultural": "madaniy",
    "social": "ijtimoiy",
    "technological": "texnologik",
    "psychological": "psixologik",
    "philosophical": "falsafiy",
    "religious": "diniy",
    "artistic": "badiiy",
    "musical": "musiqiy",
    "literary": "adabiy",
    "scientific": "ilmiy",
    "medical": "tibbiy",
    "engineering": "muhandislik",
    "architectural": "me'moriy",
    "agricultural": "qishloq xo'jaligi",
    "industrial": "sanoat",
    "transport": "transport",
    "communication": "aloqa",
    "energy": "energiya",
    "environment": "atrof muhit",
    "one": "bir",
    "two": "ikki",
    "three": "uch",
    "four": "to'rt",
    "five": "besh",
    "six": "olti",
    "seven": "yetti",
    "eight": "sakkiz",
    "nine": "to'qqiz",
    "ten": "o'n",
    "eleven": "o'n bir",
    "twelve": "o'n ikki",
    "thirteen": "o'n uch",
    "fourteen": "o'n to'rt",
    "fifteen": "o'n besh",
    "sixteen": "o'n olti",
    "seventeen": "o'n yetti",
    "eighteen": "o'n sakkiz",
    "nineteen": "o'n to'qqiz",
    "twenty": "yigirma",
    "thirty": "o'ttiz",
    "forty": "qirq",
    "fifty": "ellik",
    "sixty": "oltmish",
    "seventy": "yetmish",
    "eighty": "sakson",
    "ninety": "to'qson",
    "hundred": "yuz",
    "thousand": "ming",
    "million": "million",
    "zero": "nol",
    "first": "birinchi",
    "second": "ikkinchi",
    "third": "uchinchi",
    "fourth": "to'rtinchi",
    "fifth": "beshinchi",
    "red": "qizil",
    "blue": "ko'k",
    "green": "yashil",
    "yellow": "sariq",
    "black": "qora",
    "white": "oq",
    "purple": "binafsha",
    "pink": "pushti",
    "brown": "jigarrang",
    "gray": "kulrang",
    "gold": "oltin rang",
    "silver": "kumush rang",
    "dog": "it",
    "cat": "mushuk",
    "bird": "qush",
    "fish": "baliq",
    "horse": "ot",
    "cow": "sigir",
    "sheep": "qo'y",
    "goat": "echki",
    "pig": "cho'chqa",
    "chicken": "tovuq",
    "duck": "o'rdak",
    "rabbit": "quyon",
    "mouse": "sichqon",
    "rat": "kalamush",
    "wolf": "bo'ri",
    "fox": "tulki",
    "bear": "ayiq",
    "lion": "sher",
    "tiger": "yo'lbars",
    "elephant": "fil",
    "monkey": "maymun",
    "deer": "kiyik",
    "camel": "tuya",
    "donkey": "eshak",
    "snake": "ilon",
    "frog": "qurbaqa",
    "turtle": "toshbaqa",
    "lizard": "kaltakesak",
    "crocodile": "timsoh",
    "butterfly": "kapalak",
    "bee": "asalari",
    "ant": "chumoli",
    "spider": "o'rgimchak",
    "mosquito": "chivin",
    "worm": "qurt",
    "eagle": "burgut",
    "owl": "boyqush",
    "sparrow": "chumchuq",
    "crow": "qarg'a",
    "parrot": "to'tiqush",
    "dolphin": "delfin",
    "whale": "kit",
    "shark": "akula",
    "octopus": "sakkizoyoq",
    "crab": "qisqichbaqa",
    "penguin": "pingvin",
    "kangaroo": "kenguru",
    "giraffe": "jirafa",
    "zebra": "zebra",
    "squirrel": "olmaxon",
    "hedgehog": "tipratikan",
    "bat": "ko'rshapalak",
    "goose": "g'oz",
    "turkey": "Turkiya",
    "peacock": "tovus",
    "head": "bosh",
    "hair": "soch",
    "face": "yuz",
    "eye": "ko'z",
    "ear": "quloq",
    "nose": "burun",
    "mouth": "og'iz",
    "tooth": "tish",
    "tongue": "til",
    "lip": "lab",
    "chin": "iyak",
    "neck": "bo'yin",
    "shoulder": "yelka",
    "arm": "qo'l",
    "elbow": "tirsak",
    "finger": "barmoq",
    "nail": "mix",
    "chest": "ko'krak",
    "back": "orqa",
    "stomach": "qorin",
    "leg": "oyoq",
    "knee": "tizza",
    "ankle": "to'piq",
    "heart": "yurak",
    "brain": "miya",
    "skin": "teri",
    "bone": "suyak",
    "blood": "qon",
    "lung": "o'pka",
    "liver": "jigar",
    "bread": "non",
    "meat": "go'sht",
    "rice": "guruch",
    "egg": "tuxum",
    "milk": "sut",
    "cheese": "pishloq",
    "butter": "sariyog'",
    "sugar": "shakar",
    "salt": "tuz",
    "oil": "moy",
    "soup": "sho'rva",
    "salad": "salat",
    "sauce": "sous",
    "juice": "sharbat",
    "tea": "choy",
    "coffee": "qahva",
    "wine": "vino",
    "beer": "pivo",
    "honey": "asal",
    "jam": "murabbo",
    "cake": "tort",
    "cookie": "pechenye",
    "chocolate": "shokolad",
    "potato": "kartoshka",
    "tomato": "pomidor",
    "onion": "piyoz",
    "carrot": "sabzi",
    "cucumber": "bodring",
    "cabbage": "karam",
    "garlic": "sarimsoq",
    "corn": "makkajo'xori",
    "bean": "loviya",
    "banana": "banan",
    "orange": "apelsin",
    "lemon": "limon",
    "grape": "uzum",
    "watermelon": "tarvuz",
    "melon": "qovun",
    "pear": "nok",
    "peach": "shaftoli",
    "cherry": "gilos",
    "strawberry": "qulupnay",
    "plum": "olcha",
    "pomegranate": "anor",
    "walnut": "yong'oq",
    "almond": "bodom",
    "raisin": "mayiz",
    "fig": "anjir",
    "pineapple": "ananas",
    "mango": "mango",
    "breakfast": "nonushta",
    "lunch": "tushlik",
    "dinner": "kechki ovqat",
    "meal": "ovqat",
    "restaurant": "restoran",
    "cafe": "kafe",
    "menu": "menyu",
    "recipe": "retsept",
    "flour": "un",
    "dough": "xamir",
    "yogurt": "qatiq",
    "spice": "ziravor",
    "vinegar": "sirka",
    "go": "bormoq",
    "come": "kelmoq",
    "eat": "yemoq",
    "drink": "ichmoq",
    "sleep": "uxlamoq",
    "wake up": "uyg'onmoq",
    "walk": "yurmoq",
    "run": "yugurmoq",
    "jump": "sakramoq",
    "sit": "o'tirmoq",
    "stand": "turmoq",
    "speak": "gapirmoq",
    "talk": "suhbatlashmoq",
    "listen": "eshitmoq",
    "hear": "eshitib olmoq",
    "see": "ko'rmoq",
    "watch": "soat",
    "look": "qaramoq",
    "read": "o'qimoq",
    "write": "yozmoq",
    "draw": "chizmoq",
    "sing": "qo'shiq aytmoq",
    "dance": "raqsga tushmoq",
    "play": "o'ynamoq",
    "work": "ishlamoq",
    "study": "o'qimoq",
    "learn": "o'rganmoq",
    "teach": "o'qitmoq",
    "think": "o'ylamoq",
    "know": "bilmoq",
    "understand": "tushunmoq",
    "remember": "eslamoq",
    "forget": "unutmoq",
    "like": "yoqtirmoq",
    "hate": "yomon ko'rmoq",
    "want": "xohlamoq",
    "need": "kerak bo'lmoq",
    "help": "yordam bermoq",
    "give": "bermoq",
    "take": "olmoq",
    "buy": "sotib olmoq",
    "sell": "sotmoq",
    "pay": "to'lamoq",
    "open": "ochmoq",
    "close": "yopmoq",
    "start": "boshlamoq",
    "finish": "tugatmoq",
    "stop": "to'xtamoq",
    "wait": "kutmoq",
    "try": "urinmoq",
    "win": "g'alaba qozonmoq",
    "lose": "yutqazmoq",
    "build": "qurmoq",
    "break": "sindirmoq",
    "fix": "tuzatmoq",
    "clean": "toza",
    "wash": "yuvmoq",
    "cook": "pishirmoq",
    "cut": "kesmoq",
    "carry": "ko'tarmoq",
    "bring": "olib kelmoq",
    "send": "yubormoq",
    "receive": "qabul qilmoq",
    "call": "qo'ng'iroq qilmoq",
    "ask": "so'ramoq",
    "answer": "javob",
    "explain": "tushuntirmoq",
    "show": "ko'rsatmoq",
    "find": "topmoq",
    "search": "qidirmoq",
    "travel": "sayohat qilmoq",
    "fly": "uchmoq",
    "drive": "haydamoq",
    "swim": "suzmoq",
    "climb": "tirmashmoq",
    "fall": "yiqilmoq",
    "push": "itarmoq",
    "pull": "tortmoq",
    "throw": "otmoq",
    "catch": "ushlamoq",
    "touch": "teginmoq",
    "smell": "hidlamoq",
    "taste": "tatib ko'rmoq",
    "feel": "his qilmoq",
    "laugh": "kulmoq",
    "cry": "yig'lamoq",
    "smile": "jilmaymoq",
    "shout": "baqirmoq",
    "whisper": "shivirlamoq",
    "lie down": "yotmoq",
    "live": "yashamoq",
    "die": "o'lmoq",
    "grow": "o'smoq",
    "change": "o'zgartirmoq",
    "move": "harakat qilmoq",
    "stay": "qolmoq",
    "leave": "ketmoq",
    "arrive": "yetib kelmoq",
    "return": "qaytmoq",
    "visit": "tashrif buyurmoq",
    "invite": "taklif qilmoq",
    "marry": "turmush qurmoq",
    "meet": "uchrashmoq",
    "introduce": "tanishtirmoq",
    "agree": "rozi bo'lmoq",
    "decide": "qaror qilmoq",
    "choose": "tanlamoq",
    "believe": "ishonmoq",
    "hope": "umid qilmoq",
    "plan": "reja tuzmoq",
    "imagine": "tasavvur qilmoq",
    "create": "yaratmoq",
    "invent": "ixtiro qilmoq",
    "discover": "kashf qilmoq",
    "protect": "himoya qilmoq",
    "save": "saqlamoq",
    "spend": "sarflamoq",
    "earn": "topmoq",
    "borrow": "qarz olmoq",
    "lend": "qarz bermoq",
    "count": "sanamoq",
    "measure": "o'lchamoq",
    "compare": "taqqoslamoq",
    "describe": "tasvirlamoq",
    "translate": "tarjima qilmoq",
    "repeat": "takrorlamoq",
    "continue": "davom ettirmoq",
    "prepare": "tayyorlamoq",
    "organize": "tashkil qilmoq",
    "celebrate": "nishonlamoq",
    "enjoy": "zavqlanmoq",
    "relax": "dam olmoq",
    "hurry": "shoshilmoq",
    "complain": "shikoyat qilmoq",
    "apologize": "uzr so'ramoq",
    "thank": "rahmat aytmoq",
    "congratulate": "tabriklamoq",
    "warn": "ogohlantirmoq",
    "advise": "maslahat bermoq",
    "suggest": "taklif qilmoq",
    "allow": "ruxsat bermoq",
    "forbid": "taqiqlamoq",
    "promise": "va'da bermoq",
    "refuse": "rad etmoq",
    "accept": "qabul qilmoq",
    "deny": "inkor etmoq",
    "admit": "tan olmoq",
    "prove": "isbotlamoq",
    "guess": "taxmin qilmoq",
    "solve": "hal qilmoq",
    "check": "tekshirmoq",
    "test": "sinamoq",
    "succeed": "muvaffaqiyat qozonmoq",
    "fail": "muvaffaqiyatsizlikka uchramoq",
    "big": "katta",
    "small": "kichik",
    "tall": "baland",
    "short": "past",
    "long": "uzun",
    "wide": "keng",
    "narrow": "tor",
    "heavy": "og'ir",
    "light": "yengil",
    "fast": "tez",
    "slow": "sekin",
    "new": "yangi",
    "old": "eski",
    "young": "yosh",
    "beautiful": "chiroyli",
    "ugly": "xunuk",
    "good": "yaxshi",
    "bad": "yomon",
    "dirty": "iflos",
    "easy": "oson",
    "difficult": "qiyin",
    "strong": "kuchli",
    "weak": "kuchsiz",
    "rich": "boy",
    "poor": "kambag'al",
    "expensive": "qimmat",
    "cheap": "arzon",
    "full": "to'liq",
    "empty": "bo'sh",
    "hot": "issiq",
    "cold": "sovuq",
    "warm": "iliq",
    "cool": "salqin",
    "dry": "quruq",
    "wet": "ho'l",
    "loud": "baland",
    "quiet": "jim",
    "bright": "yorug'",
    "dark": "qorong'i",
    "soft": "yumshoq",
    "hard": "qattiq",
    "smooth": "silliq",
    "sharp": "o'tkir",
    "sweet": "shirin",
    "sour": "nordon",
    "bitter": "achchiq",
    "salty": "sho'r",
    "delicious": "mazali",
    "fresh": "yangi",
    "rotten": "chirigan",
    "straight": "to'g'ri",
    "flat": "tekis",
    "round": "dumaloq",
    "thick": "qalin",
    "thin": "ingichka",
    "deep": "chuqur",
    "shallow": "sayoz",
    "near": "yaqin",
    "far": "uzoq",
    "early": "erta",
    "late": "kech",
    "important": "muhim",
    "useful": "foydali",
    "possible": "mumkin",
    "correct": "to'g'ri",
    "wrong": "noto'g'ri",
    "true": "haqiqiy",
    "false": "yolg'on",
    "same": "bir xil",
    "different": "boshqa",
    "similar": "o'xshash",
    "free": "bepul",
    "busy": "band",
    "sick": "kasal",
    "healthy": "sog'lom",
    "safe": "xavfsiz",
    "dangerous": "xavfli",
    "famous": "mashhur",
    "interesting": "qiziqarli",
    "boring": "zerikarli",
    "funny": "kulgili",
    "serious": "jiddiy",
    "strange": "g'alati",
    "normal": "oddiy",
    "special": "maxsus",
    "rare": "kamdan-kam",
    "private": "shaxsiy",
    "modern": "zamonaviy",
    "ancient": "qadimiy",
    "simple": "oddiy",
    "complicated": "murakkab",
    "clear": "aniq",
    "comfortable": "qulay",
    "patient": "sabrli",
    "careful": "ehtiyotkor",
    "doctor": "shifokor",
    "nurse": "hamshira",
    "teacher": "o'qituvchi",
    "student": "talaba",
    "engineer": "muhandis",
    "lawyer": "advokat",
    "judge": "sudya",
    "soldier": "askar",
    "farmer": "dehqon",
    "worker": "ishchi",
    "manager": "menejer",
    "director": "direktor",
    "businessman": "tadbirkor",
    "accountant": "buxgalter",
    "secretary": "kotib",
    "driver": "haydovchi",
    "pilot": "uchuvchi",
    "sailor": "dengizchi",
    "waiter": "ofitsiant",
    "cashier": "kassir",
    "salesperson": "sotuvchi",
    "hairdresser": "sartarosh",
    "tailor": "tikuvchi",
    "carpenter": "duradgor",
    "electrician": "elektrik",
    "plumber": "santexnik",
    "painter": "rassom",
    "photographer": "fotograf",
    "journalist": "jurnalist",
    "writer": "yozuvchi",
    "poet": "shoir",
    "singer": "qo'shiqchi",
    "musician": "musiqachi",
    "actor": "aktyor",
    "athlete": "sportchi",
    "scientist": "olim",
    "architect": "arxitektor",
    "designer": "dizayner",
    "programmer": "dasturchi",
    "translator": "tarjimon",
    "librarian": "kutubxonachi",
    "veterinarian": "veterinar",
    "dentist": "stomatolog",
    "surgeon": "jarroh",
    "pharmacist": "dorixonachi",
    "banker": "bankir",
    "president": "prezident",
    "minister": "vazir",
    "mayor": "hokim",
    "shirt": "ko'ylak",
    "t-shirt": "futbolka",
    "pants": "shim",
    "jeans": "jinsi shim",
    "skirt": "yubka",
    "dress": "libos",
    "suit": "kostyum",
    "jacket": "kurtka",
    "coat": "palto",
    "sweater": "sviter",
    "socks": "paypoq",
    "shoes": "poyabzal",
    "boots": "etik",
    "sandals": "sandal",
    "hat": "shlyapa",
    "cap": "kepka",
    "scarf": "sharf",
    "gloves": "qo'lqop",
    "belt": "kamar",
    "tie": "galstuk",
    "underwear": "ichki kiyim",
    "pajamas": "pijama",
    "uniform": "forma",
    "button": "tugma",
    "pocket": "cho'ntak",
    "glasses": "ko'zoynak",
    "ring": "uzuk",
    "necklace": "marjon",
    "earring": "sirg'a",
    "bracelet": "bilakuzuk",
    "umbrella": "soyabon",
    "bag": "sumka",
    "backpack": "ryukzak",
    "wallet": "hamyon",
    "bed": "karavot",
    "sofa": "divan",
    "desk": "yozuv stoli",
    "shelf": "javon",
    "wardrobe": "shkaf",
    "mirror": "oyna",
    "lamp": "lampa",
    "carpet": "gilam",
    "curtain": "parda",
    "pillow": "yostiq",
    "blanket": "ko'rpa",
    "towel": "sochiq",
    "soap": "sovun",
    "toothbrush": "tish cho'tkasi",
    "toothpaste": "tish pastasi",
    "comb": "taroq",
    "shampoo": "shampun",
    "key": "kalit",
    "lock": "qulf",
    "candle": "sham",
    "broom": "supurgi",
    "bucket": "chelak",
    "kitchen": "oshxona",
    "bathroom": "hammom",
    "bedroom": "yotoqxona",
    "stairs": "zinapoya",
    "refrigerator": "muzlatgich",
    "stove": "gaz plita",
    "oven": "duxovka",
    "microwave": "mikroto'lqinli pech",
    "sink": "rakovina",
    "washing machine": "kir yuvish mashinasi",
    "vacuum cleaner": "changyutgich",
    "television": "televizor",
    "radio": "radio",
    "telephone": "telefon",
    "forest": "o'rmon",
    "desert": "sahro",
    "island": "orol",
    "valley": "vodiy",
    "hill": "tepalik",
    "lake": "ko'l",
    "waterfall": "sharshara",
    "cave": "g'or",
    "rock": "qoya",
    "stone": "tosh",
    "sand": "qum",
    "soil": "tuproq",
    "grass": "o't",
    "leaf": "barg",
    "branch": "shox",
    "root": "ildiz",
    "seed": "urug'",
    "field": "dala",
    "farm": "ferma",
    "village": "qishloq",
    "country": "mamlakat",
    "continent": "qit'a",
    "border": "chegara",
    "map": "xarita",
    "north": "shimol",
    "south": "janub",
    "east": "sharq",
    "west": "g'arb",
    "climate": "iqlim",
    "season": "fasl",
    "volcano": "vulqon",
    "earthquake": "zilzila",
    "day": "kun",
    "night": "tun",
    "morning": "ertalab",
    "afternoon": "kunduzi",
    "evening": "kechqurun",
    "week": "hafta",
    "month": "oy",
    "year": "yil",
    "today": "bugun",
    "tomorrow": "ertaga",
    "yesterday": "kecha",
    "now": "hozir",
    "later": "keyinroq",
    "soon": "tez orada",
    "monday": "dushanba",
    "tuesday": "seshanba",
    "wednesday": "chorshanba",
    "thursday": "payshanba",
    "friday": "juma",
    "saturday": "shanba",
    "sunday": "yakshanba",
    "january": "yanvar",
    "february": "fevral",
    "march": "mart",
    "april": "aprel",
    "june": "iyun",
    "july": "iyul",
    "august": "avgust",
    "september": "sentyabr",
    "october": "oktyabr",
    "november": "noyabr",
    "december": "dekabr",
    "spring": "bahor",
    "summer": "yoz",
    "autumn": "kuz",
    "winter": "qish",
    "hour": "soat",
    "minute": "daqiqa",
    "century": "asr",
    "holiday": "bayram",
    "birthday": "tug'ilgan kun",
    "weekend": "dam olish kuni",
    "calendar": "kalendar",
    "sunny": "quyoshli",
    "cloudy": "bulutli",
    "windy": "shamolli",
    "foggy": "tumanli",
    "temperature": "harorat",
    "humidity": "namlik",
    "joy": "quvonch",
    "fear": "qo'rquv",
    "anger": "g'azab",
    "surprise": "hayrat",
    "shame": "uyat",
    "pride": "g'urur",
    "jealousy": "hasad",
    "worry": "tashvish",
    "stress": "stress",
    "excitement": "hayajon",
    "boredom": "zerikish",
    "loneliness": "yolg'izlik",
    "gratitude": "minnatdorchilik",
    "regret": "afsus",
    "confusion": "chalkashlik",
    "satisfaction": "qoniqish",
    "classroom": "sinf xonasi",
    "lesson": "dars",
    "homework": "uy vazifasi",
    "exam": "imtihon",
    "grade": "baho",
    "pencil": "qalam",
    "pen": "ruchka",
    "notebook": "daftar",
    "eraser": "o'chirg'ich",
    "ruler": "chizg'ich",
    "blackboard": "doska",
    "textbook": "darslik",
    "university": "universitet",
    "college": "kollej",
    "kindergarten": "bog'cha",
    "principal": "direktor",
    "classmate": "sinfdosh",
    "subject": "fan",
    "mathematics": "matematika",
    "geography": "geografiya",
    "literature": "adabiyot",
    "chemistry": "kimyo",
    "physics": "fizika",
    "biology": "biologiya",
    "lecture": "ma'ruza",
    "scholarship": "stipendiya",
    "library": "kutubxona",
    "phone": "telefon",
    "smartphone": "smartfon",
    "internet": "internet",
    "website": "veb-sayt",
    "email": "elektron pochta",
    "password": "parol",
    "camera": "kamera",
    "video": "video",
    "photo": "foto",
    "application": "ilova",
    "software": "dasturiy ta'minot",
    "keyboard": "klaviatura",
    "screen": "ekran",
    "battery": "batareya",
    "charger": "zaryadlovchi",
    "printer": "printer",
    "network": "tarmoq",
    "file": "fayl",
    "data": "ma'lumot",
    "robot": "robot",
    "satellite": "sun'iy yo'ldosh",
    "football": "futbol",
    "basketball": "basketbol",
    "volleyball": "voleybol",
    "tennis": "tennis",
    "swimming": "suzish",
    "running": "yugurish",
    "boxing": "boks",
    "wrestling": "kurash",
    "chess": "shaxmat",
    "game": "o'yin",
    "ball": "to'p",
    "team": "jamoa",
    "player": "o'yinchi",
    "coach": "murabbiy",
    "match": "musobaqa",
    "championship": "chempionat",
    "medal": "medal",
    "race": "poyga",
    "bus": "avtobus",
    "train": "poyezd",
    "airplane": "samolyot",
    "bicycle": "velosiped",
    "motorcycle": "mototsikl",
    "ship": "kema",
    "boat": "qayiq",
    "taxi": "taksi",
    "truck": "yuk mashinasi",
    "subway": "metro",
    "road": "yo'l",
    "bridge": "ko'prik",
    "airport": "aeroport",
    "station": "vokzal",
    "ticket": "chipta",
    "traffic": "tirbandlik",
    "hammer": "bolg'a",
    "screwdriver": "otvyortka",
    "knife": "pichoq",
    "scissors": "qaychi",
    "rope": "arqon",
    "ladder": "narvon",
    "saw": "arra",
    "needle": "igna",
    "thread": "ip",
    "uzbekistan": "O'zbekiston",
    "russia": "Rossiya",
    "america": "Amerika",
    "england": "Angliya",
    "france": "Fransiya",
    "germany": "Germaniya",
    "china": "Xitoy",
    "japan": "Yaponiya",
    "india": "Hindiston",
    "korea": "Koreya",
    "hospital": "kasalxona",
    "medicine": "dori",
    "pill": "tabletka",
    "injection": "ukol",
    "fever": "isitma",
    "headache": "bosh og'rig'i",
    "cough": "yo'tal",
    "pain": "og'riq",
    "wound": "jarohat",
    "bandage": "bint",
    "allergy": "allergiya",
    "vaccine": "vaksina",
    "pharmacy": "dorixona",
    "market": "bozor",
    "shop": "do'kon",
    "price": "narx",
    "discount": "chegirma",
    "customer": "mijoz",
    "receipt": "chek",
    "coin": "tanga",
    "bank": "bank",
    "salary": "maosh",
    "profit": "foyda",
    "budget": "byudjet",
    "tax": "soliq",
    "question": "savol",
    "problem": "muammo",
    "solution": "yechim",
    "idea": "g'oya",
    "opinion": "fikr",
    "example": "misol",
    "list": "ro'yxat",
    "letter": "xat",
    "message": "xabar",
    "news": "yangilik",
    "story": "hikoya",
    "novel": "roman",
    "poem": "she'r",
    "song": "qo'shiq",
    "picture": "rasm",
    "image": "tasvir",
    "sound": "tovush",
    "noise": "shovqin",
    "silence": "sukunat",
    "shadow": "soya",
    "gate": "darvoza",
    "fence": "to'siq",
    "yard": "hovli",
    "street": "ko'cha",
    "neighborhood": "mahalla",
    "building": "bino",
    "factory": "zavod",
    "office": "ofis",
    "church": "cherkov",
    "mosque": "masjid",
    "museum": "muzey",
    "theater": "teatr",
    "cinema": "kinoteatr",
    "park": "park",
    "zoo": "hayvonot bog'i",
    "stadium": "stadion",
    "hotel": "mehmonxona",
    "prison": "qamoqxona",
    "always": "doim",
    "never": "hech qachon",
    "sometimes": "ba'zan",
    "often": "tez-tez",
    "usually": "odatda",
    "here": "bu yerda",
    "there": "u yerda",
    "inside": "ichida",
    "outside": "tashqarida",
    "above": "yuqorida",
    "below": "pastda",
    "between": "o'rtasida",
    "behind": "orqasida",
    "under": "ostida",
    "because": "chunki",
    "quickly": "tezda",
    "slowly": "sekinlik bilan",
    "suddenly": "to'satdan",
    "finally": "nihoyat",
    "maybe": "balki",
    "together": "birga",
    "alone": "yolg'iz",

    # --- Qo'shimcha so'zlar (3-partiya) ---
    "yourself": "o'zing",
    "himself": "o'zi (erkak)",
    "herself": "o'zi (ayol)",
    "ourselves": "o'zimiz",
    "themselves": "o'zlari",
    "someone": "kimdir",
    "something": "nimadir",
    "everyone": "hamma",
    "everything": "hammasi",
    "nobody": "hech kim",
    "nothing": "hech narsa",
    "anyone": "birortasi",
    "anything": "biror narsa",
    "what": "nima",
    "who": "kim",
    "where": "qayerda",
    "when": "qachon",
    "why": "nega",
    "how": "qanday",
    "which": "qaysi",
    "whose": "kimniki",
    "although": "garchi",
    "unless": "agar...bo'lmasa",
    "while": "esa/vaqtida",
    "whereas": "holbuki",
    "therefore": "shuning uchun",
    "however": "biroq",
    "moreover": "bundan tashqari",
    "nevertheless": "shunga qaramay",
    "toward": "tomon",
    "against": "qarshi",
    "among": "orasida",
    "during": "davomida",
    "within": "ichida (vaqt)",
    "upon": "ustiga",
    "except": "tashqari",
    "some": "ba'zi",
    "any": "biror",
    "many": "ko'p",
    "much": "juda ko'p",
    "few": "kam",
    "little": "ozgina",
    "all": "hamma",
    "none": "hech biri",
    "both": "ikkalasi",
    "each": "har biri",
    "every": "har bir",
    "several": "bir nechta",
    "enough": "yetarli",
    "goal": "maqsad",
    "purpose": "maqsad",
    "reason": "sabab",
    "cause": "sabab",
    "effect": "ta'sir",
    "result": "natija",
    "outcome": "yakun",
    "process": "jarayon",
    "method": "usul",
    "system": "tizim",
    "structure": "tuzilma",
    "function": "vazifa",
    "role": "rol",
    "task": "vazifa",
    "duty": "burch",
    "responsibility": "mas'uliyat",
    "rule": "qoida",
    "regulation": "qoidalar",
    "policy": "siyosat",
    "agreement": "kelishuv",
    "contract": "shartnoma",
    "deal": "bitim",
    "negotiation": "muzokara",
    "meeting": "uchrashuv",
    "conference": "konferensiya",
    "seminar": "seminar",
    "presentation": "taqdimot",
    "report": "hisobot",
    "document": "hujjat",
    "form": "shakl/blank",
    "certificate": "sertifikat",
    "license": "litsenziya",
    "permit": "ruxsatnoma",
    "visa": "viza",
    "passport": "pasport",
    "identity": "shaxs",
    "signature": "imzo",
    "stamp": "muhr",
    "wood": "yog'och",
    "metal": "metall",
    "iron": "temir",
    "steel": "po'lat",
    "copper": "mis",
    "plastic": "plastmassa",
    "glass": "shisha",
    "paper": "qog'oz",
    "cotton": "paxta",
    "wool": "jun",
    "silk": "ipak",
    "leather": "teri (material)",
    "rubber": "rezina",
    "cement": "sement",
    "brick": "g'isht",
    "marble": "marmar",
    "diamond": "olmos",
    "pearl": "marvarid",
    "circle": "aylana",
    "triangle": "uchburchak",
    "rectangle": "to'g'ri to'rtburchak",
    "oval": "oval",
    "cube": "kub",
    "sphere": "shar",
    "line": "chiziq",
    "point": "nuqta",
    "angle": "burchak",
    "kilogram": "kilogramm",
    "gram": "gramm",
    "liter": "litr",
    "meter": "metr",
    "kilometer": "kilometr",
    "centimeter": "santimetr",
    "ton": "tonna",
    "percent": "foiz",
    "degree": "gradus",
    "left": "chap",
    "right": "o'ng",
    "forward": "oldinga",
    "backward": "orqaga",
    "up": "yuqoriga",
    "down": "pastga",
    "top": "yuqori qism",
    "bottom": "pastki qism",
    "middle": "o'rta",
    "center": "markaz",
    "corner": "burchak (joy)",
    "edge": "chekka",
    "side": "tomon",
    "guitar": "gitara",
    "piano": "pianino",
    "violin": "skripka",
    "drum": "baraban",
    "flute": "nay",
    "trumpet": "truba",
    "microphone": "mikrofon",
    "racket": "raketka",
    "net": "to'r",
    "helmet": "kaska",
    "skateboard": "skeytbord",
    "stapler": "stepler",
    "paperclip": "qog'oz qisqichi",
    "envelope": "konvert",
    "folder": "papka",
    "calculator": "kalkulyator",
    "engine": "dvigatel",
    "wheel": "g'ildirak",
    "tire": "shina",
    "brake": "tormoz",
    "steering wheel": "rul",
    "headlight": "far",
    "seatbelt": "xavfsizlik kamari",
    "fuel": "yoqilg'i",
    "gasoline": "benzin",
    "fry": "qovurmoq",
    "boil": "qaynatmoq",
    "bake": "pishirmoq (non)",
    "grill": "gril qilmoq",
    "roast": "qovurmoq (go'sht)",
    "mix": "aralashtirmoq",
    "chop": "maydalamoq",
    "peel": "tozalamoq (po'stlog'ini)",
    "slice": "bo'laklarga kesmoq",
    "bumpy": "notekis",
    "sticky": "yopishqoq",
    "slippery": "sirg'anchiq",
    "fluffy": "momiq",
    "hurricane": "bo'ron (uragan)",
    "tornado": "smerch",
    "drought": "qurg'oqchilik",
    "rainbow": "kamalak",
    "wedding": "to'y",
    "party": "ziyofat",
    "ceremony": "marosim",
    "festival": "festival",
    "parade": "parad",
    "gift": "sovg'a",
    "present": "sovg'a",
    "decoration": "bezak",
    "balloon": "sharcha",
    "fireworks": "otashinlar",
    "husband": "er",
    "wife": "xotin",
    "son": "o'g'il",
    "daughter": "qiz",
    "nephew": "jiyan (o'g'il)",
    "niece": "jiyan (qiz)",
    "twin": "egizak",
    "widow": "beva",
    "orphan": "yetim",
    "government": "hukumat",
    "parliament": "parlament",
    "election": "saylov",
    "vote": "ovoz berish",
    "citizen": "fuqaro",
    "nation": "millat",
    "embassy": "elchixona",
    "ambassador": "elchi",
    "treaty": "shartnoma (xalqaro)",
    "war": "urush",
    "army": "armiya",
    "navy": "harbiy-dengiz flot",
    "weapon": "qurol",
    "gun": "miltiq",
    "sword": "qilich",
    "shield": "qalqon",
    "victory": "g'alaba",
    "defeat": "mag'lubiyat",
    "enemy": "dushman",
    "ally": "ittifoqchi",
    "company": "kompaniya",
    "corporation": "korporatsiya",
    "industry": "sanoat",
    "trade": "savdo",
    "export": "eksport",
    "import": "import",
    "investment": "investitsiya",
    "stock": "aksiya",
    "share": "ulush",
    "currency": "valyuta",
    "dollar": "dollar",
    "income": "daromad",
    "expense": "xarajat",
    "debt": "qarz",
    "wealth": "boylik",
    "poverty": "qashshoqlik",
    "experiment": "tajriba",
    "laboratory": "laboratoriya",
    "theory": "nazariya",
    "hypothesis": "gipoteza",
    "atom": "atom",
    "molecule": "molekula",
    "cell": "hujayra",
    "gene": "gen",
    "virus": "virus",
    "bacteria": "bakteriya",
    "gravity": "tortishish kuchi",
    "electricity": "elektr",
    "magnet": "magnit",
    "element": "element",
    "mixture": "aralashma",
    "oxygen": "kislorod",
    "hydrogen": "vodorod",
    "carbon": "uglerod",
    "nitrogen": "azot",
    "peninsula": "yarim orol",
    "canyon": "kanyon",
    "glacier": "muzlik",
    "plateau": "platо",
    "coast": "qirg'oq",
    "harbor": "port",
    "bay": "ko'rfaz",
    "strait": "bo'g'oz",
    "equator": "ekvator",
    "altitude": "balandlik",
    "galaxy": "galaktika",
    "universe": "koinot",
    "comet": "kometa",
    "asteroid": "asteroid",
    "orbit": "orbita",
    "astronaut": "astronavt",
    "spaceship": "kosmik kema",
    "telescope": "teleskop",
    "suitcase": "chamadon",
    "luggage": "yuk (bagaj)",
    "reservation": "bron",
    "appointment": "uchrashuv (belgilangan)",
    "schedule": "jadval",
    "timetable": "jadval",
    "deadline": "muddat",
    "opportunity": "imkoniyat",
    "challenge": "qiyinchilik",
    "achievement": "yutuq",
    "success": "muvaffaqiyat",
    "failure": "muvaffaqiyatsizlik",
    "mistake": "xato",
    "experience": "tajriba",
    "skill": "mahorat",
    "talent": "iste'dod",
    "habit": "odat",
    "routine": "kundalik tartib",
    "lifestyle": "turmush tarzi",
    "behavior": "xulq-atvor",
    "personality": "shaxsiyat",
    "character": "xarakter",
    "attitude": "munosabat",
    "mood": "kayfiyat",
    "atmosphere": "muhit (kayfiyat)",
    "situation": "vaziyat",
    "condition": "sharoit",
    "event": "voqea",
    "incident": "hodisa",
    "accident": "baxtsiz hodisa",
    "emergency": "favqulodda holat",
    "crisis": "inqiroz",
    "disaster": "falokat",
    "improvement": "yaxshilanish",
    "progress": "taraqqiyot",
    "development": "rivojlanish",
    "impact": "ta'sir",
    "influence": "ta'sir",
    "benefit": "foyda",
    "advantage": "afzallik",
    "disadvantage": "kamchilik",
    "risk": "xavf",
    "loyal": "sodiq",
    "ambitious": "shuhratparast",
    "creative": "ijodkor",
    "responsible": "mas'uliyatli",
    "reliable": "ishonchli",
    "flexible": "moslashuvchan",
    "optimistic": "optimist",
    "pessimistic": "pessimist",
    "cheerful": "quvnoq",
    "gentle": "muloyim",
    "wise": "dono",
    "foolish": "ahmoq",
    "arrive early": "erta kelmoq",
    "wake": "uyg'onmoq",
    "yawn": "esnamoq",
    "sneeze": "aksirmoq",
    "breathe": "nafas olmoq",
    "sweat": "terlamoq",
    "shiver": "titramoq",
    "blink": "ko'z qisib qo'ymoq",
    "wink": "ko'z qisib ishora qilmoq",
    "nod": "bosh irg'amoq",
    "point at": "ko'rsatmoq (barmoq bilan)",
    "wave": "qo'l silkitmoq",
    "hug": "quchoqlamoq",
    "kiss": "o'pmoq",
    "shake hands": "qo'l siqmoq",
    "bow": "ta'zim qilmoq",
    "kneel": "tiz cho'kmoq",
    "crawl": "emaklamoq",
    "hop": "sakramoq (bir oyoqda)",
    "skip": "sakrab-sakrab yurmoq",
    "slide": "sirg'anmoq",
    "roll": "dumalamoq",
    "spin": "aylanmoq",
    "shake": "silkitmoq",
    "squeeze": "siqmoq",
    "stretch": "cho'zilmoq",
    "bend": "egilmoq",
    "lift": "ko'tarmoq",
    "drop": "tushirib yubormoq",
    "hide": "yashirmoq",
    "seek": "qidirmoq",
    "escape": "qochmoq",
    "chase": "quvmoq",
    "follow": "ergashmoq",
    "guide": "yo'l ko'rsatmoq",
    "lead": "boshchilik qilmoq",
    "obey": "bo'ysunmoq",
    "rebel": "isyon ko'tarmoq",
    "argue": "bahslashmoq",
    "compete": "raqobatlashmoq",
    "cooperate": "hamkorlik qilmoq",
    "compromise": "murosaga kelmoq",
    "trust": "ishonmoq",
    "doubt": "shubhalanmoq",
    "suspect": "gumon qilmoq",
    "blame": "ayblamoq",
    "forgive": "kechirmoq",
    "punish": "jazolamoq",
    "reward": "mukofotlamoq",
    "praise": "maqtamoq",
    "criticize": "tanqid qilmoq",
    "insult": "haqorat qilmoq",
    "encourage": "ilhomlantirmoq",
    "discourage": "hafsalasini pir qilmoq",
    "motivate": "rag'batlantirmoq",
    "inspire": "ilhomlantirmoq",
    "impress": "hayratda qoldirmoq",
    "annoy": "bezovta qilmoq",
    "bother": "bezovta qilmoq",
    "disturb": "xalaqit bermoq",
    "interrupt": "gapini bo'lmoq",
    "distract": "e'tiborni chalg'itmoq",
    "focus": "diqqatni jamlamoq",
    "concentrate": "diqqatni jamlamoq",
    "recognize": "tanimoq",
    "identify": "aniqlamoq",
    "notice": "payqamoq",
    "observe": "kuzatmoq",
    "ignore": "e'tibor bermaslik",
    "avoid": "qochmoq (oldini olmoq)",
    "prevent": "oldini olmoq",
    "reduce": "kamaytirmoq",
    "increase": "ko'paytirmoq",
    "improve": "yaxshilamoq",
    "develop": "rivojlantirmoq",
    "achieve": "erishmoq",
    "accomplish": "amalga oshirmoq",
    "fulfill": "bajarmoq",
    "produce": "ishlab chiqarmoq",
    "manufacture": "ishlab chiqarmoq",
    "supply": "ta'minlamoq",
    "deliver": "yetkazib bermoq",
    "distribute": "tarqatmoq",
    "collect": "yig'moq",
    "gather": "yig'moq",
    "combine": "birlashtirmoq",
    "separate": "ajratmoq",
    "divide": "bo'lmoq",
    "connect": "bog'lamoq",
    "disconnect": "uzmoq",
    "attach": "biriktirmoq",
    "remove": "olib tashlamoq",
    "insert": "kiritmoq",
    "replace": "almashtirmoq",
    "install": "o'rnatmoq",
    "upgrade": "yaxshilamoq (texnika)",
    "update": "yangilamoq",
    "download": "yuklab olmoq",
    "upload": "yuklamoq",
    "quality": "sifat",
    "quantity": "miqdor",
    "value": "qiymat",
    "cost": "xarajat/narx",
    "level": "daraja",
    "stage": "bosqich",
    "phase": "bosqich",
    "period": "davr",
    "era": "davr (tarixiy)",
    "generation": "avlod",
    "population": "aholi",
    "society": "jamiyat",
    "community": "jamoa",
    "culture": "madaniyat",
    "tradition": "an'ana",
    "custom": "urf-odat",
    "belief": "e'tiqod",
    "values": "qadriyatlar",
    "principle": "tamoyil",
    "standard": "standart",
    "criterion": "mezon",
    "requirement": "talab",
    "limit": "chegara",
    "boundary": "chegara",
    "capacity": "sig'im/imkoniyat",
    "ability": "qobiliyat",
    "power": "kuch/hokimiyat",
    "authority": "hokimiyat",
    "control": "nazorat",
    "independence": "mustaqillik",
    "equality": "tenglik",
    "justice": "adolat",
    "truth": "haqiqat",
    "fact": "fakt",
    "evidence": "dalil",
    "proof": "isbot",
    "argument": "dalil/bahs",
    "debate": "munozara",
    "discussion": "muhokama",
    "conversation": "suhbat",
    "dialogue": "muloqot",
    "connection": "bog'liqlik",
    "relationship": "munosabat",
    "partnership": "sheriklik",
    "cooperation": "hamkorlik",
    "conflict": "ziddiyat",
    "competition": "raqobat",
}
# ========================================================

TIME_LIMIT = 15  # soniya
BAR_LENGTH = 10   # progress-bar segmentlari soni
BLOCK_SIZE = 10   # bir "blok"dagi so'zlar soni — hammasi to'g'ri bo'lmaguncha keyingisiga o'tilmaydi

# Aniqlikka qarab beriladigan darajalar (eng yuqoridan pastga tartiblangan)
LEAGUES = [
    (95, "💎", "Olmos"),
    (85, "🥇", "Oltin"),
    (70, "🥈", "Kumush"),
    (50, "🥉", "Bronza"),
    (0, "🌱", "Boshlang'ich"),
]


def get_league(accuracy: int):
    """Aniqlik foiziga qarab (emoji, nom) qaytaradi"""
    for threshold, emoji, name in LEAGUES:
        if accuracy >= threshold:
            return emoji, name
    return LEAGUES[-1][1], LEAGUES[-1][2]


def divider(emoji: str = "✨") -> str:
    return f"{emoji}━━━━━━━━━━━━━━━━━━{emoji}"


def progress_bar(pos: int, total: int) -> str:
    """0..total oralig'ida vizual progress-bar hosil qiladi: ▓▓▓░░░░░░░ 3/10"""
    filled = int(BAR_LENGTH * pos / total) if total else 0
    bar = "▓" * filled + "░" * (BAR_LENGTH - filled)
    return f"{bar}  {pos}/{total}"


def streak_badge(streak: int) -> str:
    """Ketma-ket to'g'ri javoblar uchun kichik belgi qaytaradi."""
    if streak >= 5:
        return f" 🔥x{streak}"
    if streak >= 3:
        return f" ⚡x{streak}"
    return ""


def build_referral_link(bot_username: str, user_id: int) -> str:
    """Foydalanuvchiga xos taklif havolasini yasaydi"""
    return f"https://t.me/{bot_username}?start=ref_{user_id}"


def share_button(link: str, text: str) -> InlineKeyboardButton:
    """Telegram'ning o'z 'ulashish' oynasini ochadigan tugma yasaydi"""
    share_url = f"https://t.me/share/url?url={quote(link, safe='')}&text={quote(text, safe='')}"
    return InlineKeyboardButton("📤 Do'stlarga ulashish", url=share_url)


def restart_keyboard(share_link: str = None, share_text: str = None) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton("🔄 Qaytadan boshlash", callback_data="restart_game")]]
    if share_link:
        rows.append([share_button(share_link, share_text or "Meni ham urinib ko'r!")])
    return InlineKeyboardMarkup(rows)


async def send_meme_voice(chat_id: int, context: ContextTypes.DEFAULT_TYPE, sound_key: str, filename: str):
    """Mavjud bo'lsa, tegishli mem ovozli xabarini yuboradi. Fayl topilmasa yoki xatolik
    yuz bersa, botning ishlashiga xalaqit bermasdan jimgina o'tkazib yuboradi.
    Bir marta yuborilgan fayl Telegram'da file_id sifatida keshlanadi — shuning uchun
    keyingi safar diskdan qayta o'qib, qayta yuklanmaydi (tezroq ishlaydi)."""
    cache = context.bot_data.setdefault("sound_file_ids", {})
    file_id = cache.get(sound_key)

    try:
        if file_id:
            await context.bot.send_voice(chat_id, voice=file_id)
            return

        path = os.path.join(SOUNDS_DIR, filename)
        if not os.path.exists(path):
            return  # Audio fayl hali joylashtirilmagan — xatosiz o'tkazib yuboramiz

        with open(path, "rb") as audio_file:
            sent = await context.bot.send_voice(chat_id, voice=audio_file)

        if sent and getattr(sent, "voice", None):
            cache[sound_key] = sent.voice.file_id
    except Exception as e:
        logging.getLogger(__name__).warning(f"Ovozli xabar yuborilmadi ({sound_key}): {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start buyrug'i - agar taraqqiyot bo'lsa davom ettiradi, aks holda yangi o'yin boshlaydi.
    Agar /start ref_<user_id> ko'rinishida (taklif havolasi orqali) kelsa, taklif qilgan
    foydalanuvchiga bonus hisoblanadi."""
    chat_id = update.effective_chat.id
    reply_fn = update.message.reply_text
    user = update.effective_user

    # ---- Taklif havolasi orqali kirilganmi, tekshiramiz ----
    if context.args and user:
        payload = context.args[0]
        if payload.startswith("ref_"):
            await credit_referral(context, referrer_id_str=payload[4:], invitee=user)

    if has_active_progress(context):
        await resume_game(chat_id, context, reply_fn)
    else:
        await launch_game(chat_id, context, reply_fn, user_id=user.id if user else None,
                           user_name=(user.first_name if user else "Do'stimiz"))


async def credit_referral(context: ContextTypes.DEFAULT_TYPE, referrer_id_str: str, invitee):
    """Taklif havolasi orqali yangi foydalanuvchi kirsa, taklif qilganga bonus yozadi
    (har bir taklif qilingan odam faqat bir marta hisoblanadi)."""
    try:
        referrer_id = int(referrer_id_str)
    except ValueError:
        return

    if referrer_id == invitee.id:
        return  # o'zini-o'zi "taklif qilishi"ning oldini olamiz

    credited = context.bot_data.setdefault("referral_credited_users", set())
    if invitee.id in credited:
        return  # bu odam avvalroq allaqachon hisoblangan

    credited.add(invitee.id)

    referrals = context.bot_data.setdefault("referrals", {})
    entry = referrals.setdefault(str(referrer_id), {"count": 0, "name": "Foydalanuvchi"})
    entry["count"] += 1

    try:
        await context.bot.send_message(
            referrer_id,
            f"🎉 <b>{invitee.first_name}</b> sizning taklifingiz bilan botga qo'shildi!\n"
            f"🎁 Jami taklif qilganlaringiz: <b>{entry['count']}</b>",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass  # taklif qilgan odam botni bloklagan bo'lishi mumkin


async def invite_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/invite - foydalanuvchiga shaxsiy taklif havolasini beradi"""
    user = update.effective_user
    bot_username = context.bot.username
    link = build_referral_link(bot_username, user.id)

    referrals = context.bot_data.setdefault("referrals", {})
    entry = referrals.setdefault(str(user.id), {"count": 0, "name": user.first_name})
    entry["name"] = user.first_name  # ismi o'zgargan bo'lsa yangilaymiz
    my_count = entry["count"]

    share_text = "🎮 Men \"So'z Tarjimasi\" botida ingliz tili so'zlarini o'rganyapman! Sen ham urinib ko'r:"

    await update.message.reply_text(
        f"{divider('🎁')}\n"
        "   <b>DO'STLARINGIZNI TAKLIF QILING</b>\n"
        f"{divider('🎁')}\n\n"
        f"Sizning shaxsiy havolangiz:\n<code>{link}</code>\n\n"
        f"🎉 Hozirgacha taklif qilganlaringiz: <b>{my_count}</b>\n\n"
        "Do'stlaringiz shu havola orqali kirsa, sizga xabar beriladi!",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[share_button(link, share_text)]]),
    )


def has_active_progress(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Diskda/saqlangan holatda tugallanmagan o'yin borligini tekshiradi"""
    return bool(context.chat_data.get("words_list")) and not context.chat_data.get("finished", True)


async def resume_game(chat_id: int, context: ContextTypes.DEFAULT_TYPE, reply_fn):
    """Foydalanuvchi qayta kirganda (yoki to'xtatilgandan keyin), qoldirgan joyidan davom ettiradi"""
    block_start = context.chat_data.get("block_start", 0)
    total_words = len(context.chat_data.get("words_list", []))
    score = context.chat_data.get("score", 0)
    wrong = context.chat_data.get("wrong", 0)
    was_paused = context.chat_data.get("paused", False)

    # Vaqt tugash taymeri qayta ishga tushirilishi kerak (chunki bot qayta yuklangan bo'lishi mumkin)
    context.chat_data["answered"] = True
    context.chat_data["paused"] = False

    header = "▶️ <b>Davom etamiz!</b>" if was_paused else "👋 <b>Xush kelibsiz, davom etamiz!</b>"

    await reply_fn(
        f"{header}\n\n"
        f"Siz {block_start}-so'zgacha yetgansiz (jami {total_words} tadan).\n"
        f"✅ To'g'ri: <b>{score}</b>   ❌ Noto'g'ri: <b>{wrong}</b>\n\n"
        "Qoldirgan joyingizdan davom etamiz 👇\n\n"
        f"ℹ️ Butunlay <b>boshidan</b> boshlamoqchi bo'lsangiz — /reset\n"
        f"⏸ O'yinni to'xtatib turish uchun — /stop yoki shunchaki <code>STOP</code> deb yozing.",
        parse_mode=ParseMode.HTML,
    )
    await send_next_word(chat_id, context)


async def pause_game(chat_id: int, context: ContextTypes.DEFAULT_TYPE, reply_fn):
    """O'yinni to'xtatib turadi: taymerni bekor qiladi va holatni saqlab qo'yadi"""
    if not has_active_progress(context):
        await reply_fn("Hozircha faol o'yin yo'q. Yangi o'yin boshlash uchun /start yuboring.")
        return

    old_jobs = context.job_queue.get_jobs_by_name(f"timeout_{chat_id}")
    for job in old_jobs:
        job.schedule_removal()

    context.chat_data["answered"] = True
    context.chat_data["paused"] = True

    score = context.chat_data.get("score", 0)
    wrong = context.chat_data.get("wrong", 0)
    block_start = context.chat_data.get("block_start", 0)

    await reply_fn(
        f"{divider('⏸')}\n"
        "     <b>O'YIN TO'XTATILDI</b>\n"
        f"{divider('⏸')}\n\n"
        "<pre>"
        f"So'z    : {block_start}-dan\n"
        f"To'g'ri : {score}\n"
        f"Xato    : {wrong}"
        "</pre>\n"
        "💾 Taraqqiyotingiz to'liq saqlandi.\n"
        "▶️ Davom ettirish uchun istalgan payt /start yozing.",
        parse_mode=ParseMode.HTML,
    )


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/stop buyrug'i — o'yinni to'xtatib turadi"""
    await pause_game(update.effective_chat.id, context, update.message.reply_text)


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/reset - bosh sahifaga qaytishni so'raydi, lekin avval maxsus so'z bilan tasdiqlashni talab qiladi"""
    if not has_active_progress(context):
        await update.message.reply_text(
            "Hozircha faol taraqqiyot yo'q. Yangi o'yin boshlash uchun /start buyrug'ini yuboring."
        )
        return

    context.chat_data["awaiting_reset_confirmation"] = True
    await update.message.reply_text(
        "⚠️ <b>Diqqat!</b> Bu amal butun taraqqiyotingizni (barcha ballaringiz bilan) "
        "o'chirib, o'yinni <b>boshidan</b> boshlaydi.\n\n"
        f"Tasdiqlash uchun quyidagi so'zni aynan yozing: <code>{RESET_KEYWORD.upper()}</code>\n\n"
        "Agar fikringizdan qaytsangiz, istalgan boshqa xabar yuboring — hech narsa o'chirilmaydi.",
        parse_mode=ParseMode.HTML,
    )


async def restart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """'🔄 Qaytadan boshlash' tugmasi bosilganda ishlaydi (faqat o'yin allaqachon tugagan bo'lsa chiqadi)"""
    query = update.callback_query
    await query.answer()
    user = query.from_user
    await launch_game(
        update.effective_chat.id, context, query.message.reply_text,
        user_id=user.id if user else None, user_name=(user.first_name if user else "Do'stimiz"),
    )


def make_block(words_list, block_start: int):
    """words_list ichidan navbatdagi BLOCK_SIZE ta so'zni (aralashtirilgan holda) qaytaradi"""
    block = words_list[block_start: block_start + BLOCK_SIZE]
    block = list(block)
    random.shuffle(block)
    return block


async def launch_game(chat_id: int, context: ContextTypes.DEFAULT_TYPE, reply_fn,
                       user_id: int = None, user_name: str = "Do'stimiz"):
    """O'yinni boshlash uchun umumiy funksiya (/start va tugma uchun ishlatiladi)"""
    words_list = list(WORDS.items())
    random.shuffle(words_list)

    context.chat_data["words_list"] = words_list
    context.chat_data["block_start"] = 0                       # umumiy ro'yxatda joriy blok boshlanishi
    context.chat_data["block_words"] = make_block(words_list, 0)  # joriy urinishdagi 10 ta so'z
    context.chat_data["pos_in_block"] = 0                       # blok ichidagi joriy pozitsiya
    context.chat_data["block_correct"] = 0                      # joriy urinishda to'g'ri javoblar soni
    context.chat_data["attempt_number"] = 1                     # joriy blokka nechinchi urinish
    context.chat_data["score"] = 0
    context.chat_data["wrong"] = 0
    context.chat_data["streak"] = 0
    context.chat_data["answered"] = True  # keyingi so'zga o'tishga ruxsat beradi
    context.chat_data["finished"] = False
    context.chat_data["awaiting_reset_confirmation"] = False
    context.chat_data["paused"] = False
    context.chat_data["user_id"] = user_id
    context.chat_data["user_name"] = user_name

    # ---- Kichik "yuklanmoqda" animatsiyasi (chiroyli, jonli taassurot uchun) ----
    try:
        await context.bot.send_chat_action(chat_id, action="typing")
    except Exception:
        pass

    loading_msg = await reply_fn("🎮 Yuklanmoqda")
    for suffix in (".", "..", "...", " ✨"):
        try:
            await asyncio.sleep(0.35)
            await loading_msg.edit_text(f"🎮 Yuklanmoqda{suffix}")
        except Exception:
            break

    total_words = len(words_list)
    welcome_text = (
        f"{divider('🎮')}\n"
        f"   <b>SO'Z TARJIMASI</b>\n"
        f"{divider('🎮')}\n\n"
        f"Salom, <b>{user_name}</b>! 👋\n\n"
        "Men ingliz so'zini yuboraman — siz uning o'zbekcha tarjimasini yozib javob bering.\n\n"
        "<pre>"
        f"📚 Jami so'zlar : {total_words}\n"
        f"📦 Blok hajmi   : {BLOCK_SIZE} ta\n"
        f"⏱ Vaqt limiti  : {TIME_LIMIT} soniya"
        "</pre>\n"
        f"❗️ Har bir <b>{BLOCK_SIZE} talik blok</b>ni <b>hammasini to'g'ri</b> topmaguningizcha "
        "keyingi so'zlarga o'tilmaydi!\n\n"
        "💾 Taraqqiyotingiz avtomatik saqlanadi.\n"
        "🏠 Boshidan boshlash: /reset\n"
        "⏸ To'xtatib turish: /stop yoki shunchaki <code>STOP</code> deb yozing\n"
        "🏆 Reyting jadvali: /top\n"
        "🎁 Do'st taklif qilish: /invite\n\n"
        f"{divider('🚀')}"
    )

    try:
        await loading_msg.edit_text(welcome_text, parse_mode=ParseMode.HTML)
    except Exception:
        await reply_fn(welcome_text, parse_mode=ParseMode.HTML)

    await send_next_word(chat_id, context)


async def send_next_word(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Joriy blokdagi keyingi so'zni yuboradi; blok tugagan bo'lsa, natijaga qarab
    keyingi blokka o'tadi yoki xuddi shu blokni qaytadan boshlaydi."""
    old_jobs = context.job_queue.get_jobs_by_name(f"timeout_{chat_id}")
    for job in old_jobs:
        job.schedule_removal()

    words_list = context.chat_data.get("words_list", [])
    total_words = len(words_list)

    block_words = context.chat_data.get("block_words", [])
    pos = context.chat_data.get("pos_in_block", 0)

    # ---- Blok tugagan bo'lsa: natijani baholaymiz ----
    if pos >= len(block_words):
        block_size = len(block_words)
        block_correct = context.chat_data.get("block_correct", 0)
        block_start = context.chat_data.get("block_start", 0)

        if block_correct == block_size:
            # ✅ Blok mukammal topildi — keyingi blokka o'tamiz
            accuracy_now = round(100 * context.chat_data.get("score", 0) /
                                  max(1, context.chat_data.get("score", 0) + context.chat_data.get("wrong", 0)))
            league_emoji, league_name = get_league(accuracy_now)
            is_perfect_meme = (block_size == 10)
            meme_line = f'\n🎙️ <i>"{MEME_PERFECT_TEXT}"</i>' if is_perfect_meme else ""
            await context.bot.send_message(
                chat_id,
                f"{divider('🎉')}\n"
                f"✅ <b>BLOK YAKUNLANDI!</b>\n"
                f"{divider('🎉')}\n"
                "<pre>"
                f"To'g'ri  : {block_size}/{block_size}  🌟\n"
                f"Daraja   : {league_emoji} {league_name}"
                "</pre>\n"
                "Zo'r ketyapsiz! Keyingi so'zlarga o'tamiz →"
                f"{meme_line}",
                parse_mode=ParseMode.HTML,
            )
            if is_perfect_meme:
                await send_meme_voice(chat_id, context, "perfect", SOUND_PERFECT_FILENAME)

            new_block_start = block_start + block_size
            if new_block_start >= total_words:
                # Butun so'zlar ro'yxati tugadi — o'yin tugadi
                await send_final_summary(chat_id, context)
                return

            context.chat_data["block_start"] = new_block_start
            context.chat_data["block_words"] = make_block(words_list, new_block_start)
            context.chat_data["pos_in_block"] = 0
            context.chat_data["block_correct"] = 0
            context.chat_data["attempt_number"] = 1
        else:
            # ❌ Hammasi to'g'ri emas — xuddi shu blok qaytadan (aralashtirilgan holda)
            wrong_in_block = block_size - block_correct
            attempt = context.chat_data.get("attempt_number", 1)
            is_fail_meme = (block_size == 10 and block_correct <= FAIL_THRESHOLD)
            meme_line = f'\n🎙️ <i>"{MEME_FAIL_TEXT}"</i>' if is_fail_meme else ""
            await context.bot.send_message(
                chat_id,
                f"{divider('🔁')}\n"
                f"😅 <b>DEYARLI!</b>\n"
                f"{divider('🔁')}\n"
                "<pre>"
                f"To'g'ri  : {block_correct}/{block_size}\n"
                f"Xato     : {wrong_in_block}/{block_size}\n"
                f"Urinish  : #{attempt + 1}"
                "</pre>\n"
                "Bu blokni <b>hammasi to'g'ri</b> bo'lguncha yechamiz — siz uddalaysiz! 💪"
                f"{meme_line}",
                parse_mode=ParseMode.HTML,
            )
            if is_fail_meme:
                await send_meme_voice(chat_id, context, "fail", SOUND_FAIL_FILENAME)

            random.shuffle(block_words)
            context.chat_data["block_words"] = block_words
            context.chat_data["pos_in_block"] = 0
            context.chat_data["block_correct"] = 0
            context.chat_data["attempt_number"] = attempt + 1

        # Yangilangan holatni qayta o'qib, joriy so'zni yuboramiz
        block_words = context.chat_data["block_words"]
        pos = 0

    # ---- Joriy so'zni yuboramiz ----
    word, translation = block_words[pos]
    context.chat_data["current_word"] = word
    context.chat_data["current_translation"] = translation
    context.chat_data["answered"] = False

    bar = progress_bar(pos, len(block_words))
    streak_txt = streak_badge(context.chat_data.get("streak", 0))
    block_start = context.chat_data.get("block_start", 0)
    block_label = f"{block_start + 1}-{block_start + len(block_words)}-so'zlar"

    try:
        await context.bot.send_chat_action(chat_id, action="typing")
    except Exception:
        pass

    await context.bot.send_message(
        chat_id,
        f"📦 <i>{block_label}</i>\n"
        f"<code>{bar}</code>{streak_txt}\n\n"
        f"🔤 So'z: <b>{word.capitalize()}</b>",
        parse_mode=ParseMode.HTML,
    )

    context.job_queue.run_once(
        timeout_callback, TIME_LIMIT, chat_id=chat_id, name=f"timeout_{chat_id}"
    )


async def send_final_summary(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Barcha so'zlar bloklari muvaffaqiyatli tugatilganda yakuniy xabar"""
    score = context.chat_data.get("score", 0)
    wrong = context.chat_data.get("wrong", 0)
    total_answers = score + wrong
    accuracy = round(100 * score / total_answers) if total_answers else 0
    context.chat_data["finished"] = True

    league_emoji, league_name = get_league(accuracy)

    # ---- Global reytingni yangilaymiz ----
    update_leaderboard(context, chat_id, accuracy)

    # ---- Ulashish uchun shaxsiy havola va matn tayyorlaymiz ----
    user_id = context.chat_data.get("user_id")
    share_link = None
    share_text = None
    if user_id:
        share_link = build_referral_link(context.bot.username, user_id)
        share_text = (
            f"🎮 Men \"So'z Tarjimasi\" botida {score} ta so'zni {accuracy}% aniqlik bilan "
            f"topdim va {league_emoji} {league_name} darajaga yetdim! Sen ham urinib ko'r:"
        )

    await context.bot.send_message(
        chat_id,
        f"{divider('🏁')}\n"
        "     🏆 <b>O'YIN TUGADI!</b> 🏆\n"
        f"{divider('🏁')}\n\n"
        "Siz har bir 10 talik blokni to'liq (10/10) topib, oxirigacha yetib keldingiz!\n\n"
        "<pre>"
        f"✅ To'g'ri   : {score}\n"
        f"❌ Xato      : {wrong}\n"
        f"🎯 Aniqlik   : {accuracy}%"
        "</pre>\n"
        f"{league_emoji} Sizning darajangiz: <b>{league_name}</b>\n\n"
        "🏆 Reytingni ko'rish uchun: /top\n"
        "🎁 Do'stlaringizni taklif qiling: /invite\n\n"
        "Qaytadan boshlash uchun quyidagi tugmani bosing 👇",
        parse_mode=ParseMode.HTML,
        reply_markup=restart_keyboard(share_link, share_text),
    )



def update_leaderboard(context: ContextTypes.DEFAULT_TYPE, chat_id: int, accuracy: int):
    """Global reyting (bot_data) ni yangilaydi — barcha foydalanuvchilar orasida"""
    user_id = context.chat_data.get("user_id")
    user_name = context.chat_data.get("user_name", "Foydalanuvchi")
    if user_id is None:
        return

    leaderboard = context.bot_data.setdefault("leaderboard", {})
    entry = leaderboard.setdefault(str(user_id), {
        "name": user_name, "games_completed": 0, "best_accuracy": 0,
    })
    entry["name"] = user_name
    entry["games_completed"] += 1
    entry["best_accuracy"] = max(entry["best_accuracy"], accuracy)


async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/top - eng yaxshi natijalar va eng ko'p taklif qilganlar reytingini ko'rsatadi"""
    leaderboard = context.bot_data.get("leaderboard", {})
    referrals = context.bot_data.get("referrals", {})

    if not leaderboard and not referrals:
        await update.message.reply_text(
            "🏆 Reyting hali bo'sh. Birinchi bo'lib o'yinni to'liq tugating va reytingga chiqing!"
        )
        return

    lines = []

    if leaderboard:
        ranked = sorted(
            leaderboard.values(),
            key=lambda e: (e["games_completed"], e["best_accuracy"]),
            reverse=True,
        )[:10]

        medals = ["🥇", "🥈", "🥉"]
        lines += [f"{divider('🏆')}", "   <b>ENG YAXSHI O'YINCHILAR</b>", f"{divider('🏆')}", "<pre>"]
        for i, entry in enumerate(ranked):
            medal = medals[i] if i < 3 else f"{i + 1}."
            name = entry["name"][:14]
            lines.append(f"{medal:<3} {name:<14} {entry['games_completed']:>2} o'yin  {entry['best_accuracy']:>3}%")
        lines.append("</pre>")

    if referrals:
        # Ismni avval referrals yozuvidan, topilmasa asosiy reytingdan olamiz
        name_lookup = {uid: e.get("name", "Foydalanuvchi") for uid, e in leaderboard.items()}

        ranked_refs = sorted(
            referrals.items(), key=lambda kv: kv[1]["count"], reverse=True
        )[:5]

        lines += ["", f"{divider('🎁')}", "   <b>ENG KO'P TAKLIF QILGANLAR</b>", f"{divider('🎁')}", "<pre>"]
        medals = ["🥇", "🥈", "🥉"]
        for i, (uid, entry) in enumerate(ranked_refs):
            medal = medals[i] if i < 3 else f"{i + 1}."
            name = entry.get("name") or name_lookup.get(uid, "Foydalanuvchi")
            name = name[:14]
            lines.append(f"{medal:<3} {name:<14} {entry['count']:>3} ta taklif")
        lines.append("</pre>")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def timeout_callback(context: ContextTypes.DEFAULT_TYPE):
    """Vaqt tugaganda chaqiriladi"""
    chat_id = context.job.chat_id
    if context.chat_data.get("answered", True):
        return

    context.chat_data["answered"] = True
    context.chat_data["wrong"] = context.chat_data.get("wrong", 0) + 1
    context.chat_data["streak"] = 0
    translation = context.chat_data.get("current_translation", "")

    await context.bot.send_message(
        chat_id,
        f"⏰ Vaqt tugadi! To'g'ri javob: <b>{translation.capitalize()}</b>",
        parse_mode=ParseMode.HTML,
    )

    context.chat_data["pos_in_block"] = context.chat_data.get("pos_in_block", 0) + 1
    await send_next_word(chat_id, context)


async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi yuborgan matnli javobni tekshiradi"""
    chat_id = update.effective_chat.id
    user = update.effective_user

    # ---- 1) Bosh sahifaga qaytish tasdiqlanishini kutayotgan bo'lsak ----
    if context.chat_data.get("awaiting_reset_confirmation"):
        context.chat_data["awaiting_reset_confirmation"] = False
        if normalize(update.message.text) == RESET_KEYWORD:
            await update.message.reply_text(
                "✅ Taraqqiyot tozalandi. Yangi o'yin boshlanmoqda...",
                parse_mode=ParseMode.HTML,
            )
            await launch_game(
                chat_id, context, update.message.reply_text,
                user_id=user.id if user else context.chat_data.get("user_id"),
                user_name=(user.first_name if user else context.chat_data.get("user_name", "Do'stimiz")),
            )
        else:
            await update.message.reply_text(
                "❎ Bekor qilindi — taraqqiyotingiz saqlanib qoldi. O'yinni davom ettiramiz."
            )
        return

    # ---- 2) "STOP" so'zi — o'yinni istalgan payt to'xtatib turish uchun ----
    if normalize(update.message.text) == STOP_KEYWORD:
        await pause_game(chat_id, context, update.message.reply_text)
        return

    # ---- 3) O'yin hozir to'xtatilgan holatda bo'lsa ----
    if context.chat_data.get("paused"):
        await update.message.reply_text(
            "⏸ O'yin hozir to'xtatilgan. Davom ettirish uchun /start yuboring."
        )
        return

    if "current_translation" not in context.chat_data:
        if context.chat_data.get("finished"):
            await update.message.reply_text(
                "O'yin allaqachon tugagan. Qaytadan boshlash uchun /start buyrug'ini yuboring."
            )
        else:
            await update.message.reply_text("O'yinni boshlash uchun /start buyrug'ini yuboring.")
        return

    if context.chat_data.get("answered", True):
        return

    context.chat_data["answered"] = True

    old_jobs = context.job_queue.get_jobs_by_name(f"timeout_{chat_id}")
    for job in old_jobs:
        job.schedule_removal()

    correct_translation = context.chat_data["current_translation"]

    if is_answer_correct(update.message.text, correct_translation):
        context.chat_data["score"] = context.chat_data.get("score", 0) + 1
        context.chat_data["block_correct"] = context.chat_data.get("block_correct", 0) + 1
        context.chat_data["streak"] = context.chat_data.get("streak", 0) + 1
        badge = streak_badge(context.chat_data["streak"])
        await update.message.reply_text(f"✅ To'g'ri!{badge}", parse_mode=ParseMode.HTML)
    else:
        context.chat_data["wrong"] = context.chat_data.get("wrong", 0) + 1
        context.chat_data["streak"] = 0
        await update.message.reply_text(
            f"❌ Noto'g'ri! To'g'ri javob: <b>{context.chat_data['current_translation'].capitalize()}</b>",
            parse_mode=ParseMode.HTML,
        )

    context.chat_data["pos_in_block"] = context.chat_data.get("pos_in_block", 0) + 1
    await send_next_word(chat_id, context)


async def score_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/score - joriy natijani ko'rsatadi"""
    score = context.chat_data.get("score", 0)
    wrong = context.chat_data.get("wrong", 0)
    block_words = context.chat_data.get("block_words", [])
    pos = context.chat_data.get("pos_in_block", 0)
    block_start = context.chat_data.get("block_start", 0)
    attempt = context.chat_data.get("attempt_number", 1)

    text = f"✅ To'g'ri: <b>{score}</b>   ❌ Noto'g'ri: <b>{wrong}</b>"
    if block_words:
        text += f"\n📦 Blok: {block_start + 1}-{block_start + len(block_words)}-so'zlar ({attempt}-urinish)"
        text += f"\n<code>{progress_bar(pos, len(block_words))}</code>"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


def main():
    # Holatni diskka saqlaydigan persistence — bot qayta ishga tushsa ham
    # foydalanuvchilarning taraqqiyoti yo'qolmaydi
    persistence = PicklePersistence(filepath=PERSISTENCE_FILE)

    app = (
        Application.builder()
        .token(TOKEN)
        .persistence(persistence)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("score", score_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("top", leaderboard_command))
    app.add_handler(CommandHandler("invite", invite_command))
    app.add_handler(CallbackQueryHandler(restart_callback, pattern="^restart_game$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_answer))

    print("Bot ishga tushdi...")
    app.run_polling()


if __name__ == "__main__":
    main()
