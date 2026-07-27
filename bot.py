import os
import tempfile
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from bundler import process_zip_file
from github_downloader import download_github_repo_zip, GITHUB_URL_REGEX
from store import save_bundle, get_bundle, toggle_bundle_format, add_sent_message

load_dotenv()

TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
MAX_TELEGRAM_FILE_BYTES = 20 * 1024 * 1024  # 20 MB Telegram Bot API limit

def format_bytes(size):
    if size < 1024:
        return f"{size} Bytes"
    elif size < 1024 * 1024:
        return f"{size / 1024:.2f} KB"
    else:
        return f"{size / (1024 * 1024):.2f} MB"

def build_summary_text(result, active_format="xml"):
    fmt_title = "XML" if active_format == "xml" else "Markdown"
    return (
        f"✅ **Project Context Bundled Successfully!** ({fmt_title})\n\n"
        f"📁 **Files Bundled:** `{result['file_count']:,}`\n"
        f"📝 **Total Lines:** `{result['total_lines']:,}`\n"
        f"🧮 **Estimated Tokens:** `~{result['token_count']:,}` (cl100k-base)\n"
        f"📦 **Context Size:** `{format_bytes(result['total_bytes'])}`\n"
        f"🔒 **Redacted Secrets:** `{result['redacted_count']}`\n\n"
        "👇 **Tap below to Copy, Download, or Clean Up chat:**"
    )

def build_keyboard(bundle_id, active_format="xml"):
    markup = InlineKeyboardMarkup(row_width=2)
    ext = ".xml" if active_format == "xml" else ".txt"
    btn_copy = InlineKeyboardButton("📋 Copy Context", callback_data=f"copy_{bundle_id}")
    btn_download = InlineKeyboardButton(f"📥 Download {ext}", callback_data=f"dl_{bundle_id}")
    
    toggle_label = "🏷️ Format: XML (Switch to MD)" if active_format == "xml" else "🏷️ Format: MD (Switch to XML)"
    btn_toggle = InlineKeyboardButton(toggle_label, callback_data=f"toggle_{bundle_id}")
    btn_clean = InlineKeyboardButton("🗑️ Clean Up Chat", callback_data=f"clean_{bundle_id}")

    markup.add(btn_copy, btn_download)
    markup.add(btn_toggle, btn_clean)
    return markup

def create_bot():
    if not TOKEN:
        print("TELEGRAM_BOT_TOKEN environment variable not set. Bot disabled.")
        return None

    bot = telebot.TeleBot(TOKEN)

    @bot.message_handler(commands=['start', 'help'])
    def send_welcome(message):
        welcome_text = (
            "👋 **Welcome to the Project Context Bundler Bot!**\n\n"
            "Convert any GitHub repository into a clean, single `project_context.xml` file ready for AI models!\n\n"
            "⚡ **How to use:**\n"
            "1️⃣ **Upload a `.zip` archive file**, OR\n"
            "2️⃣ **Paste a GitHub repo link** (e.g., `https://github.com/owner/repo`)\n\n"
            "🌟 **Features:**\n"
            "- 🌲 ASCII Directory Tree & 🏷️ **Default XML Output Format**\n"
            "- 🧮 `tiktoken` Token Count & 🔒 Automatic Secret Redaction\n"
            "- 📋 **1-Tap Copy** & 📥 **Download** directly inside Telegram\n"
            "- 🗑️ **1-Tap Chat Clean Up** to delete all generated files/messages when done!"
        )
        bot.reply_to(message, welcome_text, parse_mode="Markdown")

    @bot.message_handler(func=lambda msg: GITHUB_URL_REGEX.search(msg.text or ""))
    def handle_github_url(message):
        url_text = message.text.strip()
        status_msg = bot.reply_to(message, "⏳ Downloading repository from GitHub...")

        try:
            tmp_zip, repo_filename = download_github_repo_zip(url_text)
            process_and_send_result(bot, message, status_msg, tmp_zip, repo_filename)
        except Exception as e:
            bot.edit_message_text(f"❌ Error fetching GitHub repository: {str(e)}", message.chat.id, status_msg.message_id)

    @bot.message_handler(content_types=['document'])
    def handle_document(message):
        doc = message.document
        if not doc.file_name.lower().endswith('.zip'):
            bot.reply_to(message, "⚠️ Please upload a valid **.zip** archive file.", parse_mode="Markdown")
            return

        if doc.file_size and doc.file_size > MAX_TELEGRAM_FILE_BYTES:
            bot.reply_to(
                message,
                "⚠️ File exceeds Telegram's **20 MB** bot limit. Please upload a smaller `.zip` archive.",
                parse_mode="Markdown"
            )
            return

        status_msg = bot.reply_to(message, "⏳ Downloading and processing your project `.zip` file...")

        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_file:
            tmp_path = tmp_file.name

        try:
            file_info = bot.get_file(doc.file_id)
            downloaded_bytes = bot.download_file(file_info.file_path)

            with open(tmp_path, 'wb') as f:
                f.write(downloaded_bytes)

            process_and_send_result(bot, message, status_msg, tmp_path, doc.file_name)
        except Exception as e:
            bot.edit_message_text(f"❌ Error processing zip file: {str(e)}", message.chat.id, status_msg.message_id)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def process_and_send_result(bot, message, status_msg, zip_path, original_filename):
        result = process_zip_file(zip_path)

        bundle_id = save_bundle(
            text=result['xml_text'],
            file_count=result['file_count'],
            total_lines=result['total_lines'],
            total_bytes=result['total_bytes'],
            token_count=result['token_count'],
            redacted_count=result['redacted_count'],
            xml_text=result['xml_text'],
            markdown_text=result['markdown_text'],
            filename=original_filename
        )

        summary = build_summary_text(result, active_format="xml")
        markup = build_keyboard(bundle_id, active_format="xml")

        output_filename = f"project_context_{message.chat.id}_{message.message_id}.xml"
        output_tmp = os.path.join(tempfile.gettempdir(), output_filename)
        
        with open(output_tmp, "w", encoding="utf-8") as f:
            f.write(result['xml_text'])

        with open(output_tmp, "rb") as doc_file:
            try:
                sent_doc = bot.send_document(
                    message.chat.id,
                    doc_file,
                    caption=summary,
                    parse_mode="Markdown",
                    reply_to_message_id=message.message_id,
                    reply_markup=markup
                )
            except Exception:
                doc_file.seek(0)
                sent_doc = bot.send_document(
                    message.chat.id,
                    doc_file,
                    caption=summary,
                    parse_mode=None,
                    reply_to_message_id=message.message_id,
                    reply_markup=markup
                )
            add_sent_message(bundle_id, sent_doc.message_id)

        if os.path.exists(output_tmp):
            os.remove(output_tmp)

        bot.delete_message(message.chat.id, status_msg.message_id)

    @bot.callback_query_handler(func=lambda call: True)
    def handle_callbacks(call):
        if call.data.startswith("clean_"):
            bundle_id = call.data.replace("clean_", "")
            bundle = get_bundle(bundle_id)

            bot.answer_callback_query(call.id, "🧹 Cleaning up generated files and messages...", show_alert=False)

            if bundle and 'sent_message_ids' in bundle:
                for msg_id in bundle['sent_message_ids']:
                    try:
                        bot.delete_message(call.message.chat.id, msg_id)
                    except Exception:
                        pass
                bundle['sent_message_ids'] = []
            else:
                try:
                    bot.delete_message(call.message.chat.id, call.message.message_id)
                except Exception:
                    pass

        elif call.data.startswith("toggle_"):
            bundle_id = call.data.replace("toggle_", "")
            bundle = toggle_bundle_format(bundle_id)

            if not bundle:
                bot.answer_callback_query(call.id, "⚠️ Context expired. Please re-upload or re-paste link.", show_alert=True)
                return

            new_fmt = bundle['active_format']
            bot.answer_callback_query(call.id, f"🔄 Switched output format to {new_fmt.upper()}!", show_alert=False)

            summary = build_summary_text(bundle, active_format=new_fmt)
            markup = build_keyboard(bundle_id, active_format=new_fmt)

            try:
                bot.edit_message_caption(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    caption=summary,
                    parse_mode="Markdown",
                    reply_markup=markup
                )
            except Exception:
                pass

        elif call.data.startswith("copy_"):
            bundle_id = call.data.replace("copy_", "")
            bundle = get_bundle(bundle_id)

            if not bundle:
                bot.answer_callback_query(call.id, "⚠️ Context expired. Please re-upload or re-paste link.", show_alert=True)
                return

            text_content = bundle['text']
            fmt_label = bundle.get('active_format', 'xml').upper()
            bot.answer_callback_query(call.id, f"📋 Preparing copyable {fmt_label} context...", show_alert=False)

            CHUNK_SIZE = 3800
            MAX_COPY_PARTS = 3
            total_len = len(text_content)

            if total_len <= CHUNK_SIZE:
                safe_text = text_content.replace("```", "'''")
                copy_msg = f"📋 **Tap code block below to copy ({fmt_label}):**\n\n```text\n{safe_text}\n```"
                try:
                    sent_msg = bot.send_message(call.message.chat.id, copy_msg, parse_mode="Markdown", reply_to_message_id=call.message.message_id)
                except Exception:
                    sent_msg = bot.send_message(call.message.chat.id, f"📋 Tap code block below to copy ({fmt_label}):\n\n{text_content}", reply_to_message_id=call.message.message_id)
                add_sent_message(bundle_id, sent_msg.message_id)
            else:
                chunks = []
                lines = text_content.split('\n')
                current_chunk = []
                current_len = 0

                for line in lines:
                    line_len = len(line) + 1
                    if current_len + line_len > CHUNK_SIZE and current_chunk:
                        chunks.append("\n".join(current_chunk))
                        current_chunk = [line]
                        current_len = line_len
                    else:
                        current_chunk.append(line)
                        current_len += line_len
                if current_chunk:
                    chunks.append("\n".join(current_chunk))

                total_parts = len(chunks)
                parts_to_send = min(total_parts, MAX_COPY_PARTS)

                for idx in range(parts_to_send):
                    chunk = chunks[idx]
                    safe_chunk = chunk.replace("```", "'''")
                    copy_msg = f"📋 **Part {idx+1}/{total_parts} ({fmt_label} - Tap code block to copy):**\n\n```text\n{safe_chunk}\n```"
                    try:
                        sent_msg = bot.send_message(call.message.chat.id, copy_msg, parse_mode="Markdown", reply_to_message_id=call.message.message_id)
                    except Exception:
                        sent_msg = bot.send_message(call.message.chat.id, f"📋 Part {idx+1}/{total_parts} ({fmt_label}):\n\n{chunk}", reply_to_message_id=call.message.message_id)
                    add_sent_message(bundle_id, sent_msg.message_id)

                if total_parts > MAX_COPY_PARTS:
                    server_url = os.environ.get('SERVER_URL', '').rstrip('/')
                    copy_web_text = f"\n\n🔗 **Web 1-Click Copy:** {server_url}/copy/{bundle_id}" if server_url else ""
                    limit_msg = (
                        f"⚠️ **Context is large ({total_parts} parts / {format_bytes(len(text_content))}) for Telegram messages.**\n"
                        f"Sent first {MAX_COPY_PARTS} parts above to prevent continuous message flooding.{copy_web_text}\n\n"
                        f"📥 **Please use the Download button or open the `.xml` / `.txt` file above for full context!**"
                    )
                    try:
                        sent_msg = bot.send_message(call.message.chat.id, limit_msg, parse_mode="Markdown", reply_to_message_id=call.message.message_id)
                    except Exception:
                        sent_msg = bot.send_message(call.message.chat.id, limit_msg.replace("**", "").replace("`", ""), reply_to_message_id=call.message.message_id)
                    add_sent_message(bundle_id, sent_msg.message_id)

        elif call.data.startswith("dl_"):
            bundle_id = call.data.replace("dl_", "")
            bundle = get_bundle(bundle_id)

            if not bundle:
                bot.answer_callback_query(call.id, "⚠️ Context expired. Please re-upload or re-paste link.", show_alert=True)
                return

            bot.answer_callback_query(call.id, "📥 Sending context file...", show_alert=False)

            text_content = bundle['text']
            ext = ".xml" if bundle.get('active_format') == 'xml' else ".txt"
            output_filename = f"project_context_{call.message.chat.id}_{call.message.message_id}{ext}"
            output_tmp = os.path.join(tempfile.gettempdir(), output_filename)

            with open(output_tmp, "w", encoding="utf-8") as f:
                f.write(text_content)

            with open(output_tmp, "rb") as doc_file:
                sent_doc = bot.send_document(
                    call.message.chat.id,
                    doc_file,
                    caption=f"📥 **Here is your `project_context{ext}` file:**",
                    parse_mode="Markdown",
                    reply_to_message_id=call.message.message_id
                )
                add_sent_message(bundle_id, sent_doc.message_id)

            if os.path.exists(output_tmp):
                os.remove(output_tmp)

    return bot

def run_bot():
    bot = create_bot()
    if bot:
        print("Starting Telegram Bot polling loop...")
        try:
            bot.infinity_polling(skip_pending=True, timeout=10, long_polling_timeout=5)
        except Exception as e:
            print(f"Telegram bot polling stopped due to error: {e}")

if __name__ == '__main__':
    run_bot()
