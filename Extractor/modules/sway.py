import io
import re
import time
import aiohttp
import asyncio
from pyrogram import filters, Client
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from Extractor import app

API_BASE = "https://gdgoenkaratia.com/api"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.selectionway.com/",
    "Origin": "https://www.selectionway.com",
}

BATCH_CACHE = {}
USER_SESSIONS = {}
PAGE_SIZE = 8


def clean_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = re.sub(r'\s+', '_', name)
    return name.strip('_. ') or "SelectionWay_Batch"


def build_batch_keyboard(chat_id: int, page: int = 0) -> InlineKeyboardMarkup:
    batches = BATCH_CACHE.get(chat_id, [])
    start_idx = page * PAGE_SIZE
    end_idx = start_idx + PAGE_SIZE
    page_batches = batches[start_idx:end_idx]

    buttons = []
    for idx, b in enumerate(page_batches, start=start_idx):
        title = b.get("title", "Unknown")
        btn_title = (title[:30] + "..") if len(title) > 32 else title
        buttons.append([InlineKeyboardButton(f"📚 {btn_title}", callback_data=f"sw_pick_{idx}")])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"sw_page_{page - 1}"))
    if end_idx < len(batches):
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"sw_page_{page + 1}"))

    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="sw_close")])
    return InlineKeyboardMarkup(buttons)


async def fetch_batches(session: aiohttp.ClientSession):
    url = f"{API_BASE}/courses/active?userId="
    try:
        async with session.get(url, headers=HEADERS, timeout=25) as resp:
            if resp.status == 200:
                data = await resp.json(content_type=None)
                if data.get("state") == 200:
                    return data.get("data", [])
    except Exception:
        pass
    return []


async def fetch_topics(session: aiohttp.ClientSession, course_id):
    url = f"{API_BASE}/topic-and-section?courseId={course_id}&userId="
    try:
        async with session.get(url, headers=HEADERS, timeout=25) as resp:
            if resp.status == 200:
                data = await resp.json(content_type=None)
                if data.get("state") == 200:
                    return data.get("data", {}).get("topics", [])
    except Exception:
        pass
    return []


async def fetch_classes(session: aiohttp.ClientSession, topic_id, course_id):
    url = f"{API_BASE}/topics/{topic_id}/classes?courseId={course_id}&userId="
    try:
        async with session.get(url, headers=HEADERS, timeout=30) as resp:
            if resp.status == 200:
                data = await resp.json(content_type=None)
                if data.get("state") == 200:
                    return data.get("data", {}).get("classes", [])
    except Exception:
        pass
    return []


async def cmd_selectionway(client: Client, message: Message):
    status_msg = await message.reply_text("⚡ **Fetching SelectionWay batches...**")

    async with aiohttp.ClientSession() as session:
        batches = await fetch_batches(session)

    if not batches:
        await status_msg.edit_text("❌ **Failed to fetch batches or no active batches found.**")
        return

    chat_id = message.chat.id
    BATCH_CACHE[chat_id] = batches
    kb = build_batch_keyboard(chat_id, page=0)

    await status_msg.edit_text(
        f"🎯 **SelectionWay Batches Found:** `{len(batches)}`\n\nSelect a batch below to extract:",
        reply_markup=kb
    )


@app.on_message(filters.command(["sway", "selectionway"]) & filters.private)
async def sway_msg_handler(client: Client, message: Message):
    await cmd_selectionway(client, message)


@app.on_message(filters.command("sq") & filters.private)
async def cmd_sq_handler(client: Client, message: Message):
    user_id = message.from_user.id
    status_msg = await message.reply_text("⚡ **Fetching course list & pricing...**")

    async with aiohttp.ClientSession() as session:
        batches = await fetch_batches(session)

    if not batches:
        await status_msg.edit_text("❌ **Failed to fetch courses or no active courses found.**")
        return

    USER_SESSIONS[user_id] = batches

    list_buffer = io.StringIO()
    list_buffer.write("=========================================\n")
    list_buffer.write("         SELECTIONWAY COURSES LIST       \n")
    list_buffer.write("=========================================\n\n")

    for idx, b in enumerate(batches, 1):
        title = b.get("title", "Untitled Course").strip()
        price = b.get("fee", b.get("price", "Free"))
        faculty = b.get("facultyDetails", {}).get("name", "N/A")

        list_buffer.write(f"[{idx}] {title}\n")
        list_buffer.write(f"    ├ Price: ₹{price}\n")
        list_buffer.write(f"    └ Faculty: {faculty}\n\n")

    list_bytes = io.BytesIO(list_buffer.getvalue().encode("utf-8"))
    list_bytes.name = "SelectionWay_Courses_List.txt"

    caption = (
        f"🎯 **Found `{len(batches)}` Active Courses!**\n\n"
        f"📄 Check the attached file for all course numbers and prices.\n\n"
        f"👉 **Reply with the course number** (e.g. `1` or `5`) to extract links."
    )

    await message.reply_document(
        document=list_bytes,
        file_name="SelectionWay_Courses_List.txt",
        caption=caption
    )
    await status_msg.delete()


@app.on_callback_query(filters.regex(r"^sw_page_(\d+)"))
async def cb_pagination(client: Client, callback: CallbackQuery):
    page = int(callback.data.split("_")[2])
    kb = build_batch_keyboard(callback.message.chat.id, page=page)
    await callback.edit_message_reply_markup(reply_markup=kb)
    await callback.answer()


@app.on_callback_query(filters.regex(r"^sw_close$"))
async def cb_close(client: Client, callback: CallbackQuery):
    BATCH_CACHE.pop(callback.message.chat.id, None)
    await callback.message.delete()
    await callback.answer("Closed")


@app.on_callback_query(filters.regex(r"^sw_pick_(\d+)"))
async def cb_extract(client: Client, callback: CallbackQuery):
    idx = int(callback.data.split("_")[2])
    user_batches = BATCH_CACHE.get(callback.message.chat.id, [])

    if not user_batches or idx >= len(user_batches):
        await callback.answer("Session expired. Send /sway again.", show_alert=True)
        return

    batch = user_batches[idx]
    await execute_extraction(client, callback.message, batch, is_callback=True)


@app.on_message(filters.text & filters.private & ~filters.command(["sq", "sway", "selectionway", "start"]))
async def process_course_selection(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in USER_SESSIONS:
        return

    text = message.text.strip()
    if not text.isdigit():
        return

    selected_idx = int(text) - 1
    batches = USER_SESSIONS[user_id]

    if selected_idx < 0 or selected_idx >= len(batches):
        await message.reply_text(f"⚠️ **Invalid number!** Please enter a number between `1` and `{len(batches)}`.")
        return

    batch = batches[selected_idx]
    await execute_extraction(client, message, batch, is_callback=False)


async def execute_extraction(client: Client, message: Message, batch: dict, is_callback: bool = False):
    course_id = batch.get("id")
    batch_title = batch.get("title", "Batch")
    faculty = batch.get("facultyDetails", {}).get("name", "N/A")

    if is_callback:
        status_msg = await message.edit_text(
            f"⏳ **Extracting:** `{batch_title}`\n\n_Fetching topics & class links..._"
        )
    else:
        status_msg = await message.reply_text(
            f"⏳ **Extracting:** `{batch_title}`\n\n_Fetching topics & class links..._"
        )

    async with aiohttp.ClientSession() as session:
        topics = await fetch_topics(session, course_id)
        if not topics:
            await status_msg.edit_text("❌ **No topics found for this course.**")
            return

        output = io.StringIO()
        total_videos = 0
        total_pdfs = 0
        last_edit_time = 0

        tasks = [fetch_classes(session, t.get("topicId"), course_id) for t in topics]
        all_topic_classes = await asyncio.gather(*tasks)

        for t_idx, (topic, classes) in enumerate(zip(topics, all_topic_classes), 1):
            topic_name = topic.get("topicName", f"Topic {t_idx}")

            now = time.time()
            if (now - last_edit_time > 3) or (t_idx == len(topics)):
                try:
                    await status_msg.edit_text(
                        f"⏳ **Extracting:** `{batch_title}`\n"
                        f"📁 **Topic** `{t_idx}/{len(topics)}`: _{topic_name}_\n"
                        f"🎥 Videos: `{total_videos}` | 📑 PDFs: `{total_pdfs}`"
                    )
                    last_edit_time = now
                except Exception:
                    pass

            if not classes:
                continue

            for cls in classes:
                title = cls.get("title", "Untitled").strip()
                mp4s = cls.get("mp4Recordings", [])
                selected_video_url = ""

                if mp4s:
                    for mp4 in mp4s:
                        q = str(mp4.get("quality", "")).lower()
                        if "720" in q:
                            selected_video_url = mp4.get("url", "").strip()
                            break

                    if not selected_video_url and len(mp4s) > 0:
                        selected_video_url = mp4s[-1].get("url", "").strip()

                if not selected_video_url:
                    selected_video_url = cls.get("class_link", "").strip()

                if selected_video_url:
                    output.write(f"{title}:{selected_video_url}\n")
                    total_videos += 1

                for pdf in cls.get("classPdf", []):
                    pdf_url = pdf.get("url", "").strip()
                    pdf_name = pdf.get("name", "PDF").strip()
                    if pdf_url:
                        output.write(f"{title} - {pdf_name}:{pdf_url}\n")
                        total_pdfs += 1

    total_links = total_videos + total_pdfs
    if total_links == 0:
        await status_msg.edit_text("⚠️ **No downloadable links found in this batch.**")
        return

    file_bytes = io.BytesIO(output.getvalue().encode("utf-8"))
    safe_name = f"{clean_filename(batch_title)}.txt"
    file_bytes.name = safe_name

    caption = (
        f"> ⚡ **S E L E C T I O N W A Y**\n"
        f"> *Course content successfully extracted*\n\n"
        f"📖 **Course:** `{batch_title}`\n"
        f"👤 **Faculty:** `{faculty}`\n\n"
        f"> 📊 **Overview**\n"
        f"> ├ 🎬 **Videos:** `{total_videos}`\n"
        f"> ├ 📄 **PDFs:** `{total_pdfs}`\n"
        f"> └ 🔗 **Total Items:** `{total_links}`\n\n"
        f"✨ *Downloaded & packaged cleanly.*"
    )

    chat_id = message.chat.id
    await client.send_document(
        chat_id=chat_id,
        document=file_bytes,
        file_name=safe_name,
        caption=caption
    )
    await status_msg.delete()
