import os
import re
import json
import random
import asyncio
import logging
import base64
import requests
import aiohttp
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup

from pyrogram import filters, Client
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from pyrogram.enums import ParseMode

from Extractor import app
from config import OWNER_ID, CHANNEL_ID
import config

from Extractor.core import script
from Extractor.core.func import subscribe, chk_user
from Extractor.core.mongo import plans_db
from Extractor.core.utils import forward_to_log
from Extractor.html_converter.bot import handle_txt2html, show_txt2html_help

# Module Imports
from Extractor.modules.sway import cmd_selectionway
from Extractor.modules.appex_v4 import appex_v5_txt
from Extractor.modules.classplus import classplus_txt
from Extractor.modules.pw import pw_login
from Extractor.modules.exampur import exampur_txt
from Extractor.modules.careerwill import career_will
from Extractor.modules.utk import handle_utk_logic
from Extractor.modules.ak import ak_start
from Extractor.modules.mypathshala import my_pathshala_login
from Extractor.modules.khan import khan_login
from Extractor.modules.kdlive import kdlive
from Extractor.modules.iq import handle_iq_logic
from Extractor.modules.getappxotp import send_otpp
from Extractor.modules.findapi import findapis_extract
from Extractor.modules.rg_vikramjeet import rgvikramjeet
from Extractor.modules.adda import adda_command_handler
from Extractor.modules.vision import scrape_vision_ias
from Extractor.modules.enc import *

from Extractor.modules.freecp import *
from Extractor.modules.freeappx import *
from Extractor.modules.freepw import *

thumb_path = "Extractor/thumbs/txt-5.jpg"
THREADPOOL = ThreadPoolExecutor(max_workers=2000)
TIMEOUT = 300  # 5 minutes timeout

# -----------------------------------------------------------------------------
# RASONLY CONSTANTS & HELPERS
# -----------------------------------------------------------------------------
RASONLY_BASE = "https://course.rasonly.com"
RASONLY_HEADERS = {
    "os": "android",
    "version": "33",
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": "okhttp/5.1.0",
}
RASONLY_COMMON = {"token": "123456789", "user_id": "5679", "dlb_grp_id": "1"}

def rasonly_sanitize_filename(name: str) -> str:
    """Removes invalid OS characters from course titles."""
    return re.sub(r'[\\/*?:"<>|]', "", name).strip().replace(" ", "_")

def rasonly_extract_pdf(item: dict) -> str | None:
    """Finds PDF attachment URLs inside payload objects."""
    item_str = str(item)
    match = re.search(r'https?://[^\s\'"<>]+?\.pdf[^\s\'"<>]*', item_str, re.IGNORECASE)
    if match:
        return match.group(0).strip().rstrip('.,;)')
    return None

async def rasonly_post_api(session: aiohttp.ClientSession, path: str, payload: dict) -> dict:
    """Asynchronous HTTP POST request handler for RASonly."""
    try:
        async with session.post(f"{RASONLY_BASE}{path}", headers=RASONLY_HEADERS, data=payload, timeout=15) as resp:
            if resp.status == 200:
                return await resp.json(content_type=None)
    except Exception:
        pass
    return {}

# -----------------------------------------------------------------------------
# KEYBOARDS & MENUS
# -----------------------------------------------------------------------------
buttons = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("Lᴏɢɪɴ/Wɪᴛʜᴏᴜᴛ Lᴏɢɪɴ", callback_data="modes_")
    ],
    [
        InlineKeyboardButton("🔍 Fɪɴᴅ Aᴘɪ", callback_data="findapi_"),
        InlineKeyboardButton("📓 Aᴘᴘx Aᴘᴘs", callback_data="appxlist")
    ],
    [
        InlineKeyboardButton("📝 Tᴇxᴛ ⟷ HTML", callback_data="converter_")
    ]
])

modes_button = [
    [
        InlineKeyboardButton("🔏 Wɪᴛʜᴏᴜᴛ Lᴏɢɪɴ", callback_data="custom_")
    ],
    [
        InlineKeyboardButton("🔑 Lᴏɢɪɴ", callback_data="manual_"),
    ],
    [
        InlineKeyboardButton("𝐁 𝐀 𝐂 𝐊", callback_data="home_")
    ]
]

custom_button = [
    [
        InlineKeyboardButton("⚡ Pᴡ ⚡", callback_data="pwwp"),
        InlineKeyboardButton("🔮 Aᴘᴘx 🔮", callback_data="appxwp"),
    ],
    [
        InlineKeyboardButton("🎯 CʟᴀssPʟᴜs 🎯", callback_data="cpwp"),
        InlineKeyboardButton("🎓 CDS JᴏᴜʀɴᴇY 🎓", callback_data="cds_journey_free"),
    ],
    [
        InlineKeyboardButton("📚 Sᴇʟᴇᴄᴛɪᴏɴ Wᴀʏ 📚", callback_data="sway_free"),
        InlineKeyboardButton("🎯 RASᴏɴʟʏ 🎯", callback_data="rasonly_free"),
    ],
    [
        InlineKeyboardButton("𝐁 𝐀 𝐂 𝐊", callback_data="modes_"),
    ]
]

button1 = [
    [
        InlineKeyboardButton("👑 Aᴘɴɪ Kᴀᴋsʜᴀ", callback_data="ak_"),
        InlineKeyboardButton("👑 Aᴅᴅᴀ 𝟸𝟺𝟽", callback_data="adda_")
    ],
    [
        InlineKeyboardButton("👑 CʟᴀssPʟᴜs", callback_data="classplus_"),
        InlineKeyboardButton("👑 Kʜᴀɴ Gs", callback_data="khan_")
    ],
    [
        InlineKeyboardButton("👑 Pʜʏsɪᴄs Wᴀʟʟᴀʜ", callback_data="pw_"),
        InlineKeyboardButton("👑 Sᴛᴜᴅʏ IQ", callback_data="iq_")
    ],
    [
        InlineKeyboardButton("👑 Kᴅ Cᴀᴍᴘᴜs", callback_data="kdlive_"),
        InlineKeyboardButton("👑 Uᴛᴋᴀʀsʜ", callback_data="utkarsh_"),
        InlineKeyboardButton("👑 CDS JᴏᴜʀɴᴇY", callback_data="cds_journey")
    ],
    [
        InlineKeyboardButton("👑 Mʏ Pᴀᴛʜsʜᴀʟᴀ", callback_data="my_pathshala_"),
        InlineKeyboardButton("👑 ExᴀᴍPᴜʀ", callback_data="exampur_txt")
    ],
    [
        InlineKeyboardButton("👑 Vɪsɪᴏɴ Iᴀs", callback_data="vision_ias_"),
        InlineKeyboardButton("👑 Rᴀɴᴋᴇʀs Gᴜʀᴜᴋᴜʟ", callback_data="maintainer_")
    ],
    [
        InlineKeyboardButton("﹤", callback_data="modes_"),
        InlineKeyboardButton("ʙ ᴀ ᴄ ᴋ", callback_data="modes_"),
        InlineKeyboardButton("﹥", callback_data="next_1")
    ]
]

button2 = [
    [
        InlineKeyboardButton("Soon", callback_data="maintainer_"),
        InlineKeyboardButton("Soon", callback_data="maintainer_")
    ],
    [
        InlineKeyboardButton("Soon", callback_data="maintainer_"),
        InlineKeyboardButton("Soon", callback_data="maintainer_")
    ],
    [
        InlineKeyboardButton("Soon", callback_data="maintainer_"),
        InlineKeyboardButton("Soon", callback_data="maintainer_"),
    ],
    [
        InlineKeyboardButton("Soon", callback_data="maintainer_"),
        InlineKeyboardButton("Soon", callback_data="maintainer_"),
    ],
    [
        InlineKeyboardButton("Soon", callback_data="maintainer_"),
        InlineKeyboardButton("Soon", callback_data="maintainer_"),
    ],
    [
        InlineKeyboardButton("Soon", callback_data="maintainer_"),
        InlineKeyboardButton("Soon", callback_data="maintainer_"),
    ],
    [
        InlineKeyboardButton("﹤", callback_data="manual_"),
        InlineKeyboardButton("ʙ ᴀ ᴄ ᴋ", callback_data="modes_"),
        InlineKeyboardButton("﹥", callback_data="next_2")
    ]
]

button3 = [
    [
        InlineKeyboardButton("Soon", callback_data="maintainer_"),
        InlineKeyboardButton("Soon", callback_data="maintainer_")
    ],
    [
        InlineKeyboardButton("Soon", callback_data="maintainer_"),
        InlineKeyboardButton("Soon", callback_data="maintainer_")
    ],
    [
        InlineKeyboardButton("Soon", callback_data="maintainer_"),
        InlineKeyboardButton("Soon", callback_data="maintainer_")
    ],
    [
        InlineKeyboardButton("Soon", callback_data="maintainer_"),
        InlineKeyboardButton("Soon", callback_data="maintainer_")
    ],
    [
        InlineKeyboardButton("Soon", callback_data="maintainer_"),
        InlineKeyboardButton("Soon", callback_data="maintainer_")
    ],
    [
        InlineKeyboardButton("Soon", callback_data="maintainer_"),
        InlineKeyboardButton("Soon", callback_data="maintainer_")
    ],
    [
        InlineKeyboardButton("﹤", callback_data="next_1"),
        InlineKeyboardButton("ʙ ᴀ ᴄ ᴋ", callback_data="modes_"),
        InlineKeyboardButton("﹥", callback_data="next_3")
    ]
]

button4 = [
    [
        InlineKeyboardButton("Soon", callback_data="maintainer_"),
        InlineKeyboardButton("Soon", callback_data="maintainer_")
    ],
    [
        InlineKeyboardButton("Soon", callback_data="maintainer_"),
        InlineKeyboardButton("Soon", callback_data="maintainer_")
    ],
    [
        InlineKeyboardButton("Soon", callback_data="maintainer_"),
        InlineKeyboardButton("Soon", callback_data="maintainer_")
    ],
    [
        InlineKeyboardButton("Soon", callback_data="maintainer_"),
        InlineKeyboardButton("Soon", callback_data="maintainer_"),
    ],
    [
        InlineKeyboardButton("Soon", callback_data="maintainer_"),
        InlineKeyboardButton("Soon", callback_data="maintainer_")
    ],
    [
        InlineKeyboardButton("Soon", callback_data="maintainer_"),
        InlineKeyboardButton("Soon", callback_data="maintainer_")
    ],
    [
        InlineKeyboardButton("﹤", callback_data="next_2"),
        InlineKeyboardButton("ʙ ᴀ ᴄ ᴋ", callback_data="modes_"),
        InlineKeyboardButton("﹥", callback_data="next_4")
    ]
]

button5 = [
    [
        InlineKeyboardButton("Soon", callback_data="maintainer_"),
        InlineKeyboardButton("Soon", callback_data="maintainer_")
    ],
    [
        InlineKeyboardButton("Soon", callback_data="maintainer_"),
        InlineKeyboardButton("Soon", callback_data="maintainer_")
    ],
    [
        InlineKeyboardButton("Soon", callback_data="maintainer_"),
        InlineKeyboardButton("Soon", callback_data="maintainer_")
    ],
    [
        InlineKeyboardButton("Soon", callback_data="maintainer_"),
        InlineKeyboardButton("Soon", callback_data="maintainer_")
    ],
    [
        InlineKeyboardButton("Soon", callback_data="maintainer_"),
        InlineKeyboardButton("Soon", callback_data="maintainer_")
    ],
    [
        InlineKeyboardButton("Soon", callback_data="maintainer_"),
        InlineKeyboardButton("Soon", callback_data="maintainer_")
    ],
    [
        InlineKeyboardButton("﹤", callback_data="next_3"),
        InlineKeyboardButton("ʙ ᴀ ᴄ ᴋ", callback_data="modes_"),
        InlineKeyboardButton("﹥", callback_data="manual_")
    ]
]

back_button = [
    [
        InlineKeyboardButton("ʙᴀᴄᴋ", callback_data="modes_"),
    ]
]

def photo():
    return config.THUMB_URL

# -----------------------------------------------------------------------------
# START COMMAND
# -----------------------------------------------------------------------------
@app.on_message(filters.command("start"))
async def start(_, message):
    join = await subscribe(_, message)
    if join == 1:
        return
    try:
        await message.reply_photo(
            photo=photo(),
            caption=script.START_TXT.format(message.from_user.mention),
            reply_markup=buttons
        )
    except Exception as e:
        print(f"Error in start command: {e}")
        await message.reply_text(
            script.START_TXT.format(message.from_user.mention),
            reply_markup=buttons
        )

# -----------------------------------------------------------------------------
# RASONLY WITHOUT LOGIN EXTRACTION FLOW
# -----------------------------------------------------------------------------
@app.on_callback_query(filters.regex("^rasonly_free$"))
async def rasonly_free_callback(client: Client, query: CallbackQuery):
    await query.message.edit_text("⏳ **Fetching available batches... Please wait.**")
    async with aiohttp.ClientSession() as session:
        pkg_payload = {"token": "123456789", "dlb_u_id": "5677", "groupId": "1"}
        pkg_res = await rasonly_post_api(session, "/app_version_2/exam/package-series-new", pkg_payload)

        pkgs = []
        for v in (pkg_res if isinstance(pkg_res, list) else pkg_res.values()):
            if isinstance(v, list) and v and "dlb_pkg_id" in v[0]:
                pkgs = v
                break

        if not pkgs:
            await query.message.edit_text(
                "❌ **Failed to retrieve courses.**",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="custom_")]])
            )
            return

        buttons_list = []
        for p in pkgs:
            pid = str(p.get("dlb_pkg_id"))
            title = p.get("dlb_pkg_title", f"Course {pid}")
            price = p.get("dlb_pkg_price") or p.get("pkg_price") or "Free"
            btn_title = (title[:25] + "..") if len(title) > 25 else title
            buttons_list.append([InlineKeyboardButton(f"📚 {btn_title} (₹{price})", callback_data=f"rasext_{pid}")])

        buttons_list.append([InlineKeyboardButton("🔙 Back", callback_data="custom_")])

        await query.message.edit_text(
            "🎯 **Select a Course to Extract Links:**",
            reply_markup=InlineKeyboardMarkup(buttons_list)
        )
        await query.answer()

@app.on_callback_query(filters.regex(r"^rasext_(\d+)$"))
async def rasonly_extract_batch_callback(client: Client, query: CallbackQuery):
    target_pid = query.data.split("_")[1]
    await query.message.edit_text(
        f"⏳ **Extracting Course ID `{target_pid}`...**\n"
        f"__Fetching lectures, PDFs, and HLS streams...__"
    )

    async with aiohttp.ClientSession() as session:
        pkg_payload = {"token": "123456789", "dlb_u_id": "5677", "groupId": "1"}
        pkg_res = await rasonly_post_api(session, "/app_version_2/exam/package-series-new", pkg_payload)
        
        course_title = f"Course_{target_pid}"
        for v in (pkg_res if isinstance(pkg_res, list) else pkg_res.values()):
            if isinstance(v, list) and v and "dlb_pkg_id" in v[0]:
                match_pkg = next((p for p in v if str(p.get("dlb_pkg_id")) == target_pid), None)
                if match_pkg:
                    course_title = match_pkg.get("dlb_pkg_title", course_title)
                break

        # Fetch Subjects
        sub_payload = {**RASONLY_COMMON, "dlb_pkg_id": target_pid}
        sub_res = await rasonly_post_api(session, "/app_version_2/course-subject", sub_payload)
        subjects = sub_res.get("List", [])

        if not subjects:
            await query.message.edit_text(f"❌ **No subjects found for Course ID `{target_pid}`.**")
            return

        extracted_lines = [
            f"Course: {course_title} (ID: {target_pid})",
            "=" * 70,
            ""
        ]

        total_videos = 0
        total_pdfs = 0

        for sub in subjects:
            sub_id = str(sub.get("id"))
            sub_name = sub.get("name", f"Subject_{sub_id}")

            vid_payload = {**RASONLY_COMMON, "dlb_pkg_id": target_pid, "catid": sub_id}
            vid_res = await rasonly_post_api(session, "/app_version_2/class-videos-list-new", vid_payload)
            videos_data = vid_res.get("homedata", [])

            if not videos_data:
                continue

            sub_video_lines = []
            sub_pdf_lines = []

            for v in videos_data:
                v_title = v.get("title", "Untitled").strip()
                hls = v.get("aws_hsl_path") or v.get("hls_url")
                pdf = rasonly_extract_pdf(v)

                if hls:
                    sub_video_lines.append(f"{v_title} : {hls}")
                    total_videos += 1

                if pdf:
                    sub_pdf_lines.append(f"{v_title} : {pdf}")
                    total_pdfs += 1

            if sub_video_lines or sub_pdf_lines:
                extracted_lines.append(f"\n{'=' * 20} {sub_name.upper()} (ID: {sub_id}) {'=' * 20}\n")
                if sub_video_lines:
                    extracted_lines.append("--- [VIDEOS] ---")
                    extracted_lines.extend(sub_video_lines)
                    extracted_lines.append("")
                if sub_pdf_lines:
                    extracted_lines.append("--- [PDF NOTES] ---")
                    extracted_lines.extend(sub_pdf_lines)
                    extracted_lines.append("")

        total_links = total_videos + total_pdfs
        if total_links == 0:
            await query.message.edit_text(f"⚠️ **No media or notes found for ID `{target_pid}`.**")
            return

        filename = f"{target_pid}_{rasonly_sanitize_filename(course_title)}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write("\n".join(extracted_lines).strip() + "\n")

        caption = (
            f"**🎯 ᴇxᴛʀᴀᴄᴛɪᴏɴ sᴜᴄᴄᴇssғᴜʟ**\n\n"
            f"> 📚 **Batch Name:** `{course_title}`\n"
            f"> 🆔 **Course ID:** `{target_pid}`\n"
            f"> 🎬 **Total Videos:** `{total_videos}`\n"
            f"> 📄 **Total PDFs:** `{total_pdfs}`\n"
            f"> 🔗 **Total Links:** `{total_links}`\n"
            f"> ⚡ **Platform:** `RASonly`\n\n"
            f"__Extracted by ONeX Extractor Bot__"
        )

        await query.message.reply_document(
            document=filename,
            caption=caption,
            thumb=thumb_path if os.path.exists(thumb_path) else None
        )
        await query.message.delete()

        if os.path.exists(filename):
            os.remove(filename)

# -----------------------------------------------------------------------------
# APPX & UTILITIES
# -----------------------------------------------------------------------------
def get_alphabet_keyboard():
    """Create a keyboard with A-Z buttons in a modern style"""
    alphabet = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    keyboard = []
    row = []

    for letter in alphabet:
        row.append(InlineKeyboardButton(f"{letter}", callback_data=f"alpha_{letter}"))
        if len(row) == 7:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("𝐁 𝐀 𝐂 𝐊", callback_data="home_")])
    return InlineKeyboardMarkup(keyboard)

def get_apps_by_letter(letter):
    """Get apps starting with the given letter from appxapis.json"""
    try:
        with open('appxapis.json', 'r', encoding='utf-8') as f:
            apps = json.load(f)

        filtered_apps = [app for app in apps if app['name'].upper().startswith(letter)]
        filtered_apps.sort(key=lambda x: x['name'])
        return filtered_apps
    except Exception as e:
        print(f"Error reading appxapis.json: {e}")
        return []

def to_small_caps(text):
    normal = "abcdefghijklmnopqrstuvwxyz"
    small_caps = "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ"
    table = str.maketrans(''.join(normal), ''.join(small_caps))
    return text.lower().translate(table)

def create_app_keyboard(apps, page=0, letter=None):
    """Create a keyboard with app buttons, 40 apps per page"""
    keyboard = []
    row = []

    items_per_page = 40
    total_pages = (len(apps) + items_per_page - 1) // items_per_page
    start_idx = page * items_per_page
    end_idx = min(start_idx + items_per_page, len(apps))
    current_apps = apps[start_idx:end_idx]

    for idx, app_item in enumerate(current_apps):
        name = app_item['name']
        styled_name = name.replace("api", "").replace("Api", "")
        styled_name = ' '.join(word.capitalize() for word in styled_name.split())

        button_text = f"👑 {styled_name}"
        button = InlineKeyboardButton(button_text, callback_data=f"app_{name}")
        row.append(button)

        if len(row) == 2:
            keyboard.append(row)
            row = []

    if row:
        if len(row) == 1:
            row.append(InlineKeyboardButton(" ", callback_data="ignore"))
        keyboard.append(row)

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("« Prev", callback_data=f"page_{letter}_{page-1}"))
    nav_row.append(InlineKeyboardButton("« 𝐁𝐚𝐜𝐤 »", callback_data="appxlist"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next »", callback_data=f"page_{letter}_{page+1}"))
    keyboard.append(nav_row)

    return keyboard, total_pages

async def process_with_timeout(func, client, message, user_id, timeout=60):
    try:
        return await asyncio.wait_for(func(client, message, user_id), timeout=timeout)
    except asyncio.TimeoutError:
        return "timeout"
    except Exception as e:
        print(f"Error in process_with_timeout: {e}")
        return f"error:{str(e)}"

# -----------------------------------------------------------------------------
# TOP-LEVEL CALLBACK HANDLERS
# -----------------------------------------------------------------------------
@app.on_callback_query(filters.regex("^appxlist$"))
async def show_alphabet(client, query):
    keyboard = get_alphabet_keyboard()
    await query.message.edit_text("𝐒𝐞𝐥𝐞𝐜𝐭 𝐀 𝐋𝐞𝐭𝐭𝐞𝐫 𝐓𝐨 𝐕𝐢𝐞𝐰 𝐀𝐩ᴘ𝐬 ✨", reply_markup=keyboard)

@app.on_callback_query(filters.regex("^alpha_"))
async def show_apps_for_letter(client, query):
    letter = query.data.split('_')[1]
    apps = get_apps_by_letter(letter)

    if not apps:
        await query.answer(f"No apps found starting with {letter}", show_alert=True)
        return

    keyboard, total_pages = create_app_keyboard(apps, page=0, letter=letter)
    text = f"📱 𝐀𝐩𝐩𝐬 𝐒𝐭𝐚𝐫ᴛ𝐢𝐧Gs 𝐖𝐢𝐭𝐡 '{letter}' ({len(apps)} apps)\n"
    text += f"𝐏𝐚𝐠𝐞: 1/{total_pages}\n"
    text += "═══════════════════"

    try:
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        print(f"Error showing apps: {e}")
        await query.answer("Error displaying apps. Please try again.", show_alert=True)

@app.on_callback_query(filters.regex(r"^sway_free$"))
async def handle_sway_callback(client: Client, callback: CallbackQuery):
    await callback.answer()
    await cmd_selectionway(client, callback.message)

@app.on_callback_query(filters.regex("^page_"))
async def handle_pagination(client, query):
    try:
        _, letter, page = query.data.split('_')
        page = int(page)

        apps = get_apps_by_letter(letter)
        if not apps:
            await query.answer("No apps found", show_alert=True)
            return

        keyboard, total_pages = create_app_keyboard(apps, page, letter)
        text = f"📱 𝐀𝐩𝐩𝐬 𝐒𝐭𝐚𝐫ᴛ𝐢𝐧𝐠 𝐖𝐢𝐭𝐡 '{letter}' ({len(apps)} apps)\n"
        text += f"𝐏𝐚𝐠𝐞: {page + 1}/{total_pages}\n"
        text += "═══════════════════"

        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        print(f"Pagination error: {e}")
        await query.answer("Error in pagination. Please try again.", show_alert=True)

@app.on_callback_query(filters.regex("^app_"))
async def handle_app_selection(client, query):
    try:
        app_name = query.data.split("_")[1]
        with open('appxapis.json', 'r', encoding='utf-8') as f:
            apps = json.load(f)

        selected_app = next((app for app in apps if app['name'] == app_name), None)

        if selected_app:
            api = selected_app['api']
            name = selected_app['name']
            api = api.replace("https://", "").replace("http://", "")
            await appex_v5_txt(app, query.message, api, name)
        else:
            await query.message.edit_text(
                "**Error: App not found**\n\n"
                "Please try selecting another app.",
                reply_markup=get_alphabet_keyboard()
            )
    except Exception as e:
        await query.message.edit_text(
            f"**Error processing app: {str(e)}**\n\n"
            "Please try again later.",
            reply_markup=get_alphabet_keyboard()
        )

@app.on_callback_query(filters.regex("^pwwp$"))
async def pwwp_callback(client, callback_query):
    try:
        processing_msg = await callback_query.message.reply_text(
            "⏳ Starting process... Please wait  - **DONT LOGIN WITH PHONE NUMBER, It Leads to ban your account of PW**"
        )
        user_id = callback_query.from_user.id
        try:
            await process_pwwp(client, callback_query.message, user_id)
        except Exception as e:
            await processing_msg.edit_text(
                f"❌ An error occurred: {str(e)}\n"
                "Please try again."
            )
    except Exception as e:
        print(f"Error in pwwp_callback: {e}")
        await callback_query.answer("An error occurred", show_alert=True)

@app.on_callback_query(filters.regex("^appxwp$"))
async def appxwp_callback(client, callback_query):
    try:
        processing_msg = await callback_query.message.reply_text(
            "⏳ Starting process... Please wait"
        )
        user_id = callback_query.from_user.id
        try:
            result = await process_with_timeout(process_appxwp, client, callback_query.message, user_id)
            if result == "timeout":
                await processing_msg.edit_text(
                    "⚠️ Process timed out. Please try again.\n"
                    "Tip: Make sure to respond within 60 seconds when prompted."
                )
            elif result and result.startswith("error:"):
                await processing_msg.edit_text(
                    f"❌ An error occurred: {result[6:]}\n"
                    "Please try again."
                )
            else:
                await processing_msg.delete()
        except Exception as e:
            await processing_msg.edit_text(
                "❌ Process failed. Please try again.\n"
                f"Error: {str(e)}"
            )
    except Exception as e:
        print(f"Error in appxwp_callback: {e}")
        await callback_query.answer("An error occurred", show_alert=True)

@app.on_callback_query(filters.regex("^cpwp$"))
async def cpwp_callback(client, callback_query):
    try:
        processing_msg = await callback_query.message.reply_text(
            "⏳ Starting process... Please wait"
        )
        user_id = callback_query.from_user.id
        try:
            await process_cpwp(client, callback_query.message, user_id)
        except Exception as e:
            await processing_msg.edit_text(
                f"❌ An error occurred: {str(e)}\n"
                "Please try again."
            )
    except Exception as e:
        print(f"Error in cpwp_callback: {e}")
        await callback_query.answer("An error occurred", show_alert=True)

@app.on_callback_query(filters.regex("^cw$"))
async def career_will_callback(app: Client, callback_query: CallbackQuery):
    try:
        await callback_query.answer()
        processing_msg = await callback_query.message.reply_text("Starting CareerWill extractor...")
        await career_will(app, callback_query.message)
        try:
            await processing_msg.delete()
        except Exception:
            pass
    except Exception as e:
        await callback_query.message.reply_text(f"Error: {str(e)}")

@app.on_callback_query(filters.regex("^ignore$"))
async def handle_ignore(client, query):
    await query.answer()

# -----------------------------------------------------------------------------
# MAIN CALLBACK DISPATCHER
# -----------------------------------------------------------------------------
@app.on_callback_query()
async def handle_callback(client, query):
    if query.data == "home_":
        await query.message.edit_text(
            script.START_TXT.format(query.from_user.mention),
            reply_markup=buttons
        )

    elif query.data == "modes_":
        reply_markup = InlineKeyboardMarkup(modes_button)
        await query.message.edit_text(
            script.MODES_TXT,
            reply_markup=reply_markup
        )

    elif query.data == "custom_":
        reply_markup = InlineKeyboardMarkup(custom_button)
        await query.message.edit_text(
            script.CUSTOM_TXT,
            reply_markup=reply_markup
        )

    elif query.data == "manual_":
        reply_markup = InlineKeyboardMarkup(button1)
        await query.message.edit_text(
            script.MANUAL_TXT,
            reply_markup=reply_markup
        )

    elif query.data == "next_1":
        reply_markup = InlineKeyboardMarkup(button2)
        await query.message.edit_text(
            script.MANUAL_TXT,
            reply_markup=reply_markup
        )

    elif query.data == "next_2":
        reply_markup = InlineKeyboardMarkup(button3)
        await query.message.edit_text(
            script.MANUAL_TXT,
            reply_markup=reply_markup
        )

    elif query.data == "next_3":
        reply_markup = InlineKeyboardMarkup(button4)
        await query.message.edit_text(
            script.MANUAL_TXT,
            reply_markup=reply_markup
        )

    elif query.data == "next_4":
        reply_markup = InlineKeyboardMarkup(button5)
        await query.message.edit_text(
            script.MANUAL_TXT,
            reply_markup=reply_markup
        )

    elif query.data == "perfect_acc":
        api = "perfectionacademyapi.appx.co.in"
        name = "Perfection Academy"
        await appex_v5_txt(app, query.message, api, name)

    elif query.data == "e1_coaching":
        api = "e1coachingcenterapi.classx.co.in"
        name = "e1 coaching"
        await appex_v5_txt(app, query.message, api, name)

    elif query.data == "samyak_ras":
        api = "samyakapi.classx.co.in"
        name = "Samyak"
        await appex_v5_txt(app, query.message, api, name)

    elif query.data == "vj_education":
        api = "vjeducationapi.appx.co.in"
        name = "VJ Education"
        await appex_v5_txt(app, query.message, api, name)

    elif query.data == "gyan_bindu":
        api = "gyanbinduapi.appx.co.in"
        name = "Gyan Bindu"
        await appex_v5_txt(app, query.message, api, name)

    elif query.data == "dhananjay_ias":
        api = "dhananjayiasacademyapi.classx.co.in"
        name = "Dhananjay IAS"
        await appex_v5_txt(app, query.message, api, name)

    elif query.data == "think_ssc":
        api = "thinksscapi.classx.co.in"
        name = "Think SSC"
        await appex_v5_txt(app, query.message, api, name)

    elif query.data == "note_book":
        api = "notebookapi.classx.co.in"
        name = "Note Book"
        await appex_v5_txt(app, query.message, api, name)

    elif query.data == "uc_live":
        api = "ucliveapi.classx.co.in"
        name = "UC LIVE"
        await appex_v5_txt(app, query.message, api, name)

    elif query.data == "space_ias":
        api = "spaceiasapi.classx.co.in"
        name = "Space IAS"
        await appex_v5_txt(app, query.message, api, name)

    elif query.data == "rg_vikramjeet":
        await rgvikramjeet(app, query.message)

    elif query.data == "vidya_bihar":
        api = "vidyabiharapi.teachx.in"
        name = "Vidya Vihar"
        await appex_v5_txt(app, query.message, api, name)

    elif query.data == "aman_sir":
        api = "amansirenglishapi.classx.co.in"
        name = "Aman Sir English"
        await appex_v5_txt(app, query.message, api, name)

    elif query.data == "nirman_ias":
        api = "nirmaniasapi.classx.co.in"
        name = "Nirman IAS"
        await appex_v5_txt(app, query.message, api, name)

    elif query.data == "permar_ssc":
        api = "parmaracademyapi.classx.co.in"
        name = "Parmar Academy"
        await appex_v5_txt(app, query.message, api, name)

    elif query.data == "neo_spark":
        api = "neosparkapi.classx.co.in"
        name = "Neo Spark"
        await appex_v5_txt(app, query.message, api, name)

    elif query.data == "md_classes":
        api = "mdclassesapi.classx.co.in"
        name = "MD Classes"
        await appex_v5_txt(app, query.message, api, name)

    elif query.data == "ng_learners":
        api = "nglearnersapi.classx.co.in"
        name = "NG Learners"
        await appex_v5_txt(app, query.message, api, name)

    elif query.data == "anilsir_iti":
        api = "anilsiritiapi.classx.co.in"
        name = "Anil Sir Iti"
        await appex_v5_txt(app, query.message, api, name)

    elif query.data == "education_adda":
        api = "educationaddaplusapi.classx.co.in"
        name = "Education Adda Plus"
        await appex_v5_txt(app, query.message, api, name)

    elif query.data == "achievers_acc":
        api = "achieversacademyapi.classx.co.in"
        name = "Achievers Academy"
        await appex_v5_txt(app, query.message, api, name)

    elif query.data == "commando_acc":
        api = "commandoacademyapi.appx.co.in"
        name = "Commando Academy"
        await appex_v5_txt(app, query.message, api, name)

    elif query.data == "neet_kakajee":
        api = "neetkakajeeapi.classx.co.in"
        name = "Neet Kaka JEE"
        await appex_v5_txt(app, query.message, api, name)

    elif query.data == "app_exampur":
        api = "exampurapi.classx.co.in"
        name = "App Exampur"
        await appex_v2_txt(app, query.message, api, name)

    elif query.data == "classplus_":
        await classplus_txt(app, query.message)

    elif query.data == 'ak_':
        await ak_start(client, query.message)

    elif query.data in ["pw_", "pw2_", "mobile_", "token_"]:
        await pw_login(app, query.message)

    elif query.data == "close_data":
        await query.message.delete()
        await query.message.reply_to_message.delete()

    elif query.data == "txt2html_":
        await show_txt2html_help(client, query.message)

    elif query.data == "converter_":
        await query.message.edit_text(
            "**🔄 File Conversion Tools**\n\n"
            "**<blockquote>Choose the conversion type you need:</blockquote>**\n\n"
            "• 📝 **Text to HTML**: Convert text files to beautiful HTML pages\n"
            "• 📄 **HTML to Text**: Extract links from HTML files back to text",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📝 Tᴇxᴛ ᴛᴏ HTML", callback_data="txt2html_"),
                    InlineKeyboardButton("📄 HTML ᴛᴏ Tᴇxᴛ", callback_data="html2txt_")
                ],
                [
                    InlineKeyboardButton("𝐁 𝐀 𝐂 𝐊", callback_data="home_")
                ]
            ])
        )

    elif query.data == "html2txt_":
        await query.message.edit_text(
            "**📄 HTML to Text Converter**\n\n"
            "**<blockquote>Convert HTML files back to text format with decoded URLs.</blockquote>**\n\n"
            "**How to use:**\n"
            "• Send an HTML file directly\n"
            "• Or use command `/html2txt` with HTML file\n"
            "• Get back a text file with all extracted links\n\n"
            "**Features:**\n"
            "• Extracts all video links\n"
            "• Extracts all PDF links\n"
            "• Decodes obfuscated URLs\n"
            "• Clean name:url format",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("𝐁 𝐀 𝐂 𝐊", callback_data="converter_")
                ]
            ])
        )

    elif query.data == "maintainer_":
        await query.message.edit_text("THIS FEATURE IS UNDER DEVELOPMENT")

    elif query.data == "utkarsh_":
        await handle_utk_logic(app, query.message)

    elif query.data == "vision_ias_":
        await scrape_vision_ias(app, query.message)

    elif query.data == "my_pathshala_":
        await my_pathshala_login(app, query.message)

    elif query.data == "khan_":
        await khan_login(app, query.message)

    elif query.data == "kdlive_":
        await kdlive(app, query.message)

    elif query.data == "iq_":
        await handle_iq_logic(app, query.message)

    elif query.data == "adda_":
        await adda_command_handler(app, query.message)

    elif query.data == "exampur_txt":
        await exampur_txt(app, query.message)

# -----------------------------------------------------------------------------
# HTML CONVERTER HANDLERS
# -----------------------------------------------------------------------------
def deobfuscate_url(encoded_url):
    """Deobfuscate URL back to original form."""
    try:
        decoded = base64.b64decode(encoded_url.encode()).decode()
        decoded = base64.b64decode(decoded.encode()).decode()
        return decoded[8:]
    except Exception:
        return encoded_url

async def fetch_url(session, url):
    """Fetch URL from API asynchronously and extract actual URL."""
    try:
        if 'api.extractor.workers.dev' in url:
            url_param = re.search(r'url=([^&]+)', url)
            if url_param:
                return url_param.group(1)
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    if 'url' in data:
                        return data['url']
    except Exception:
        pass
    return url

@app.on_message(filters.command("txt2html"))
async def txt2html_command(client, message):
    await show_txt2html_help(client, message)

@app.on_message(filters.private & filters.document)
async def handle_document(client, message):
    """Handle document messages"""
    if message.document.file_name.endswith('.txt'):
        await handle_txt2html(client, message)
    elif message.document.file_name.endswith('.html'):
        await html_to_text_command(client, message)

@app.on_message(filters.command("html2txt"))
async def html_to_text_command(client: Client, message: Message):
    """Convert HTML file back to text format."""
    try:
        if message.reply_to_message and message.reply_to_message.document:
            doc = message.reply_to_message.document
            is_reply = True
        elif message.document:
            doc = message.document
            is_reply = False
        else:
            await message.reply_text("Please send an HTML file or reply to one.")
            return

        if not doc.file_name.endswith('.html'):
            await message.reply_text("Please send an HTML file only.")
            return

        progress_msg = await message.reply_text("Processing HTML file...")
        if is_reply:
            file_path = await message.reply_to_message.download()
        else:
            file_path = await message.download()

        with open(file_path, 'r', encoding='utf-8') as f:
            html_content = f.read()

        soup = BeautifulSoup(html_content, 'html.parser')

        async with aiohttp.ClientSession() as session:
            video_links = []
            tasks = []
            video_names = []

            for div in soup.find_all('div', class_='list-group-item'):
                onclick = div.get('onclick', '')
                if 'playVideo' in onclick:
                    encoded_url = re.search(r"playVideo\('([^']+)'\)", onclick)
                    if encoded_url:
                        url = deobfuscate_url(encoded_url.group(1))
                        name = div.find('span').text.strip()
                        if 'api.extractor.workers.dev' in url:
                            tasks.append(fetch_url(session, url))
                            video_names.append(name)
                        else:
                            url_param = re.search(r'url=([^&]+)', url)
                            if url_param:
                                url = url_param.group(1)
                            video_links.append((name, url))

            if tasks:
                results = await asyncio.gather(*tasks)
                for name, url in zip(video_names, results):
                    video_links.append((name, url))

            pdf_links = []
            for div in soup.find_all('div', class_='list-group-item'):
                view_btn = div.find('button', class_='view')
                if view_btn and 'viewPDF' in view_btn.get('onclick', ''):
                    encoded_url = re.search(r"viewPDF\('([^']+)'\)", view_btn['onclick'])
                    if encoded_url:
                        url = deobfuscate_url(encoded_url.group(1))
                        url_param = re.search(r'url=([^&]+)', url)
                        if url_param:
                            url = url_param.group(1)
                        name = div.find('span').text.strip()
                        pdf_links.append((name, url))

            other_links = []
            for div in soup.find_all('div', class_='list-group-item'):
                link = div.find('a', onclick=True)
                if link and 'deobfuscateUrl' in link.get('onclick', ''):
                    encoded_url = re.search(r"deobfuscateUrl\('([^']+)'\)", link['onclick'])
                    if encoded_url:
                        url = deobfuscate_url(encoded_url.group(1))
                        url_param = re.search(r'url=([^&]+)', url)
                        if url_param:
                            url = url_param.group(1)
                        name = div.find('span').text.strip()
                        other_links.append((name, url))

            text_content = "🎥 Videos:\n"
            for name, url in video_links:
                url = requests.utils.unquote(url)
                text_content += f"{name}:{url}\n"

            if pdf_links:
                text_content += "\n📄 PDFs:\n"
                for name, url in pdf_links:
                    url = requests.utils.unquote(url)
                    text_content += f"{name}:{url}\n"

            if other_links:
                text_content += "\n🔗 Other Links:\n"
                for name, url in other_links:
                    text_content += f"{name}:{url}\n"

            text_content += "\n@GodxBots"

            txt_path = file_path.rsplit('.', 1)[0] + '.txt'
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(text_content)

            await message.reply_document(
                txt_path,
                thumb=thumb_path if os.path.exists(thumb_path) else None,
                caption="<blockquote>✅ HTML converted to text format\n🔓 All URLs have been decoded\n\n🤖 @GodxBots</blockquote>"
            )

            os.remove(file_path)
            os.remove(txt_path)
            await progress_msg.delete()

    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")
