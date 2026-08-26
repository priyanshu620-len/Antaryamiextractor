import os
import re
import aiohttp
from pyrogram import Client, filters
from pyrogram.types import Message

# Base Configuration
BASE_URL = "https://course.rasonly.com"
HEADERS = {
    "os": "android",
    "version": "33",
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": "okhttp/5.1.0",
}
COMMON_PAYLOAD = {"token": "123456789", "user_id": "5679", "dlb_grp_id": "1"}

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

@Client.on_message(filters.command(["rasonly"]) & ~filters.forwarded)
async def rasonly_handler(client: Client, message: Message):
    args = message.text.split(maxsplit=1)
    status_msg = await message.reply_text("🔎 **Fetching batch data...**")

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
            await status_msg.edit_text("❌ **Failed to retrieve courses from API.**")
            return

        # Menu Display: If no batch ID is passed
        if len(args) == 1:
            menu = "📚 **RASonly Available Batches:**\n\n"
            for p in pkgs:
                pid = str(p.get("dlb_pkg_id"))
                title = p.get("dlb_pkg_title", "Course")
                price = p.get("dlb_pkg_price") or p.get("pkg_price") or "Free"
                menu += f"• `{pid}` — **{title}** (₹{price})\n"

            menu += "\n👉 **Send `/rasonly <Course_ID>` to extract.**"

            if len(menu) > 4000:
                menu = menu[:4000] + "\n\n...[list truncated]"
            await status_msg.edit_text(menu)
            return

        # Extraction Flow: ID provided
        target_pid = args[1].strip()
        selected_pkg = next((p for p in pkgs if str(p.get("dlb_pkg_id")) == target_pid), None)
        course_title = selected_pkg.get("dlb_pkg_title", f"Course_{target_pid}") if selected_pkg else f"Course_{target_pid}"

        await status_msg.edit_text(f"⏳ **Extracting:** `{course_title}`\n_Processing subjects & lectures..._")

        # 2. Fetch Subjects
        sub_payload = {**COMMON_PAYLOAD, "dlb_pkg_id": target_pid}
        sub_res = await post_api(session, "/app_version_2/course-subject", sub_payload)
        subjects = sub_res.get("List", [])

        if not subjects:
            await status_msg.edit_text(f"❌ **No subjects found for Course ID `{target_pid}`.**")
            return

        extracted_lines = [
            f"Course: {course_title} (ID: {target_pid})",
            "=" * 70,
            ""
        ]
        
        total_videos = 0
        total_pdfs = 0

        # 3. Fetch Classes & Separate Videos from PDFs
        for sub in subjects:
            sub_id = str(sub.get("id"))
            sub_name = sub.get("name", f"Subject_{sub_id}")

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

            if sub_video_lines or sub_pdf_lines:
                extracted_lines.append(f"\n{'=' * 20} {sub_name.upper()} (ID: {sub_id}) {'=' * 20}\n")
                
                # Videos Section
                if sub_video_lines:
                    extracted_lines.append("--- [VIDEOS] ---")
                    extracted_lines.extend(sub_video_lines)
                    extracted_lines.append("")
                
                # PDFs Section
                if sub_pdf_lines:
                    extracted_lines.append("--- [PDF NOTES] ---")
                    extracted_lines.extend(sub_pdf_lines)
                    extracted_lines.append("")

        total_links = total_videos + total_pdfs
        if total_links == 0:
            await status_msg.edit_text(f"⚠️ **No media or notes found for ID `{target_pid}`.**")
            return

        # 4. Generate, Send & Cleanup Document
        filename = f"{target_pid}_{sanitize_filename(course_title)}.txt"
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

        await message.reply_document(document=filename, caption=caption)
        await status_msg.delete()

        if os.path.exists(filename):
            os.remove(filename)
