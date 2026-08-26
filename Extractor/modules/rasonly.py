import os
import re
import aiohttp
from pyrogram import Client, filters
from pyrogram.types import Message

# -----------------------------------------------------------------------------
# Configuration & Headers
# -----------------------------------------------------------------------------
BASE_URL = "https://course.rasonly.com"
HEADERS = {
    "os": "android",
    "version": "33",
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": "okhttp/5.1.0",
}
COMMON_PAYLOAD = {"token": "123456789", "user_id": "5679", "dlb_grp_id": "1"}
THUMB_PATH = "Extractor/thumbs/txt-5.jpg"


def sanitize_filename(name: str) -> str:
    """Removes invalid filesystem characters for saving files."""
    return re.sub(r'[\\/*?:"<>|]', "", name).strip().replace(" ", "_")


def extract_pdf(item: dict) -> str | None:
    """Finds PDF attachment URLs inside payload dictionaries."""
    item_str = str(item)
    match = re.search(r'https?://[^\s\'"<>]+?\.pdf[^\s\'"<>]*', item_str, re.IGNORECASE)
    if match:
        return match.group(0).strip().rstrip('.,;)')
    return None


async def post_api(session: aiohttp.ClientSession, path: str, payload: dict) -> dict:
    """Asynchronous HTTP POST request handler."""
    try:
        async with session.post(f"{BASE_URL}{path}", headers=HEADERS, data=payload, timeout=15) as resp:
            if resp.status == 200:
                return await resp.json(content_type=None)
    except Exception:
        pass
    return {}


# -----------------------------------------------------------------------------
# Extraction Command Handler
# -----------------------------------------------------------------------------
@Client.on_message(filters.command(["rasonly"]) & ~filters.forwarded)
async def rasonly_handler(client: Client, message: Message):
    status_msg = await message.reply_text("⏳ **Fetching available courses list... Please wait.**")

    async with aiohttp.ClientSession() as session:
        # 1. Fetch available packages
        pkg_payload = {"token": "123456789", "dlb_u_id": "5677", "groupId": "1"}
        pkg_res = await post_api(session, "/app_version_2/exam/package-series-new", pkg_payload)

        pkgs = []
        for v in (pkg_res if isinstance(pkg_res, list) else pkg_res.values()):
            if isinstance(v, list) and v and "dlb_pkg_id" in v[0]:
                pkgs = v
                break

        if not pkgs:
            await status_msg.edit_text("❌ **Failed to retrieve courses from server.**")
            return

        # 2. Build text-based courses list
        menu_text = "📚 **AVAILABLE RASONLY COURSES**\n"
        menu_text += "═══════════════════════════════════════\n\n"

        valid_map = {}
        for idx, p in enumerate(pkgs, 1):
            pid = str(p.get("dlb_pkg_id"))
            title = p.get("dlb_pkg_title", f"Course_{pid}").strip()
            thumb = p.get("dlb_pkg_thumbnail") or p.get("image") or p.get("thumbnail") or ""

            price = p.get("dlb_pkg_price") or p.get("pkg_price") or "0"
            notes_price = p.get("dlb_notes_price", "")
            test_price = p.get("dlb_test_price", "")

            if price in ("0", ""):
                if notes_price and notes_price != "0":
                    display_price = f"₹{notes_price} (eNotes)"
                elif test_price and test_price != "0":
                    display_price = f"₹{test_price} (Test Series)"
                else:
                    display_price = "FREE"
            else:
                display_price = f"₹{price}"

            valid_map[str(idx)] = (pid, title, thumb)
            valid_map[pid] = (pid, title, thumb)

            menu_text += f"`{idx:02d}.` **{title}**\n"
            menu_text += f"     └ **ID:** `{pid}` | **Price:** `{display_price}`\n\n"

        menu_text += "═══════════════════════════════════════\n"
        menu_text += "👉 **Reply with the Course Number or Course ID to extract:**"

        if len(menu_text) > 4000:
            menu_text = menu_text[:4000] + "\n\n...[list truncated]"

        await status_msg.edit_text(menu_text)

        # 3. Wait for user selection
        try:
            user_response: Message = await client.listen(chat_id=message.chat.id, timeout=120)
        except Exception:
            await message.reply_text("⏰ **Session timed out. Please run `/rasonly` again.**")
            return

        choice = user_response.text.strip()
        if choice not in valid_map:
            await message.reply_text(f"❌ **Invalid selection `{choice}`. Please run `/rasonly` again.**")
            return

        target_pid, course_title, course_thumb = valid_map[choice]
        progress_msg = await message.reply_text(
            f"⏳ **Extracting:** `{course_title}` (ID: `{target_pid}`)\n"
            f"__Fetching topics, lectures, and documents...__"
        )

        # 4. Fetch Subjects
        sub_payload = {**COMMON_PAYLOAD, "dlb_pkg_id": target_pid}
        sub_res = await post_api(session, "/app_version_2/course-subject", sub_payload)
        subjects = sub_res.get("List", [])

        if not subjects:
            await progress_msg.edit_text(f"❌ **No subjects found under Course ID `{target_pid}`.**")
            return

        file_lines = []

        # 5. Course Thumbnail
        if course_thumb and str(course_thumb).startswith("http"):
            file_lines.append(f"(Course Thumbnail) Course Thumbnail : {course_thumb.strip()}")

        total_videos = 0
        total_pdfs = 0

        # 6. Fetch Lectures & PDFs Topic-wise
        for sub in subjects:
            sub_id = str(sub.get("id"))
            sub_name = sub.get("name", f"Subject_{sub_id}").strip()

            vid_payload = {**COMMON_PAYLOAD, "dlb_pkg_id": target_pid, "catid": sub_id}
            vid_res = await post_api(session, "/app_version_2/class-videos-list-new", vid_payload)
            videos_data = vid_res.get("homedata", [])

            if not videos_data:
                continue

            for v in videos_data:
                v_title = v.get("title", "Untitled").strip()
                hls = v.get("aws_hsl_path") or v.get("hls_url") or v.get("url")
                pdf = extract_pdf(v)

                # Format: (Topic) Title : URL
                if hls:
                    file_lines.append(f"({sub_name}) {v_title} : {hls.strip()}")
                    total_videos += 1

                # Format: (Topic) Title [PDF] : URL
                if pdf:
                    file_lines.append(f"({sub_name}) {v_title} [PDF] : {pdf.strip()}")
                    total_pdfs += 1

        total_links = total_videos + total_pdfs
        if total_links == 0:
            await progress_msg.edit_text(f"⚠️ **No media or document links found for ID `{target_pid}`.**")
            return

        # 7. Write to file & Upload
        filename = f"{target_pid}_{sanitize_filename(course_title)}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write("\n".join(file_lines).strip() + "\n")

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

        await message.reply_document(
            document=filename,
            caption=caption,
            thumb=THUMB_PATH if os.path.exists(THUMB_PATH) else None
        )
        await progress_msg.delete()

        if os.path.exists(filename):
            os.remove(filename)
