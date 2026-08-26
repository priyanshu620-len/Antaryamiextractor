import os
import re
import aiohttp
from pyrogram import Client, filters
from pyrogram.types import Message

# -----------------------------------------------------------------------------
# Base Configuration & Headers
# -----------------------------------------------------------------------------
BASE_URL = "https://course.rasonly.com"
HEADERS = {
    "os": "android",
    "version": "33",
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": "okhttp/5.1.0",
}
COMMON_PAYLOAD = {"token": "123456789", "user_id": "5679", "dlb_grp_id": "1"}

thumb_path = "Extractor/thumbs/txt-5.jpg"


def sanitize_filename(name: str) -> str:
    """Removes illegal filesystem characters."""
    return re.sub(r'[\\/*?:"<>|]', "", name).strip().replace(" ", "_")


def extract_pdf(item: dict) -> str | None:
    """Finds PDF attachment URLs inside payload objects."""
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
# Command & Interactive Handler
# -----------------------------------------------------------------------------
@Client.on_message(filters.command(["rasonly"]) & ~filters.forwarded)
async def rasonly_handler(client: Client, message: Message):
    status_msg = await message.reply_text("🔎 **Fetching available courses list... Please wait.**")

    async with aiohttp.ClientSession() as session:
        # 1. Fetch available packages from API
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

        # 2. Build the text-based course menu list
        menu_text = "📚 **AVAILABLE RASONLY COURSES**\n"
        menu_text += "═══════════════════════════════════════\n\n"

        valid_map = {}
        for idx, p in enumerate(pkgs, 1):
            pid = str(p.get("dlb_pkg_id"))
            title = p.get("dlb_pkg_title", f"Course_{pid}").strip()
            
            # Pricing evaluation
            price = p.get("dlb_pkg_price") or p.get("pkg_price") or "0"
            mrp = p.get("MRP", "0")
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

            valid_map[str(idx)] = (pid, title)
            valid_map[pid] = (pid, title)

            menu_text += f"`{idx:02d}.` **{title}**\n"
            menu_text += f"     └ **ID:** `{pid}` | **Price:** `{display_price}`\n\n"

        menu_text += "═══════════════════════════════════════\n"
        menu_text += "👉 **Reply with the Course Number or Course ID to extract:**"

        if len(menu_text) > 4000:
            menu_text = menu_text[:4000] + "\n\n...[list truncated]"

        await status_msg.edit_text(menu_text)

        # 3. Wait for user input
        try:
            user_response: Message = await client.listen(chat_id=message.chat.id, timeout=120)
        except Exception:
            await message.reply_text("⏰ **Session timed out. Please run `/rasonly` again.**")
            return

        choice = user_response.text.strip()
        if choice not in valid_map:
            await message.reply_text(f"❌ **Invalid selection `{choice}`. Please run `/rasonly` again.**")
            return

        target_pid, course_title = valid_map[choice]
        progress_msg = await message.reply_text(
            f"⏳ **Extracting:** `{course_title}` (ID: `{target_pid}`)\n"
            f"__Fetching subject modules and organizing topics...__"
        )

        # 4. Fetch Subjects
        sub_payload = {**COMMON_PAYLOAD, "dlb_pkg_id": target_pid}
        sub_res = await post_api(session, "/app_version_2/course-subject", sub_payload)
        subjects = sub_res.get("List", [])

        if not subjects:
            await progress_msg.edit_text(f"❌ **No subjects found under Course ID `{target_pid}`.**")
            return

        # 5. Build structured Topic/Subject-wise .txt content
        file_lines = []
        file_lines.append("=" * 75)
        file_lines.append(f"COURSE: {course_title}")
        file_lines.append(f"COURSE ID: {target_pid}")
        file_lines.append("=" * 75)
        file_lines.append("")

        total_videos = 0
        total_pdfs = 0

        for sub in subjects:
            sub_id = str(sub.get("id"))
            sub_name = sub.get("name", f"Subject_{sub_id}").strip()

            vid_payload = {**COMMON_PAYLOAD, "dlb_pkg_id": target_pid, "catid": sub_id}
            vid_res = await post_api(session, "/app_version_2/class-videos-list-new", vid_payload)
            videos_data = vid_res.get("homedata", [])

            if not videos_data:
                continue

            sub_video_lines = []
            sub_pdf_lines = []

            for v in videos_data:
                v_title = v.get("title", "Untitled").strip()
                hls = v.get("aws_hsl_path") or v.get("hls_url")
                pdf = extract_pdf(v)

                if hls:
                    sub_video_lines.append(f"{v_title} : {hls}")
                    total_videos += 1

                if pdf:
                    sub_pdf_lines.append(f"{v_title} : {pdf}")
                    total_pdfs += 1

            # Only append the topic block if links exist
            if sub_video_lines or sub_pdf_lines:
                file_lines.append(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                file_lines.append(f"📁 TOPIC / SUBJECT: {sub_name.upper()} (ID: {sub_id})")
                file_lines.append(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                file_lines.append("")

                if sub_video_lines:
                    file_lines.append("[ VIDEOS / LECTURES ]")
                    file_lines.extend(sub_video_lines)
                    file_lines.append("")

                if sub_pdf_lines:
                    file_lines.append("[ STUDY MATERIAL / PDF NOTES ]")
                    file_lines.extend(sub_pdf_lines)
                    file_lines.append("")

        total_links = total_videos + total_pdfs
        if total_links == 0:
            await progress_msg.edit_text(f"⚠️ **No media or document links found for ID `{target_pid}`.**")
            return

        # 6. Save and Upload Document
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
            thumb=thumb_path if os.path.exists(thumb_path) else None
        )
        await progress_msg.delete()

        # Clean up disk
        if os.path.exists(filename):
            os.remove(filename)
