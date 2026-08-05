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
        f"✅ <b>Project Context Bundled Successfully!</b> ({fmt_title})\n\n"
        f"📁 <b>Files Bundled:</b> <code>{result['file_count']:,}</code>\n"
        f"📝 <b>Total Lines:</b> <code>{result['total_lines']:,}</code>\n"
        f"🧮 <b>Estimated Tokens:</b> <code>~{result['token_count']:,}</code> (cl100k-base)\n"
        f"📦 <b>Context Size:</b> <code>{format_bytes(result['total_bytes'])}</code>\n"
        f"🔒 <b>Redacted Secrets:</b> <code>{result['redacted_count']}</code>\n\n"
        "👇 <b>Tap below to Download context file or switch format:</b>"
    )

def build_keyboard(bundle_id, active_format="xml"):
    markup = InlineKeyboardMarkup(row_width=2)
    ext = ".xml" if active_format == "xml" else ".txt"
    btn_download = InlineKeyboardButton(f"📥 Download {ext}", callback_data=f"dl_{bundle_id}")
    
    toggle_label = "🏷️ Format: XML (Switch to MD)" if active_format == "xml" else "🏷️ Format: MD (Switch to XML)"
    btn_toggle = InlineKeyboardButton(toggle_label, callback_data=f"toggle_{bundle_id}")
    btn_clean = InlineKeyboardButton("🗑️ Clean Up Chat", callback_data=f"clean_{bundle_id}")

    markup.add(btn_download, btn_toggle)
    markup.add(btn_clean)
    return markup

def is_github_url_message(message):
    if not message or not message.text:
        return False
    text = message.text.strip()
    # Reject long texts or code blocks to avoid false positives when users paste/forward code
    if len(text) > 300 or text.count('\n') > 3:
        return False
    return bool(GITHUB_URL_REGEX.search(text))

def create_bot():
    if not TOKEN:
        print("TELEGRAM_BOT_TOKEN environment variable not set. Bot disabled.")
        return None

    bot = telebot.TeleBot(TOKEN)

    @bot.message_handler(commands=['start', 'help'])
    def send_welcome(message):
        welcome_text = (
            "👋 <b>Welcome to the Project Context Bundler Bot!</b>\n\n"
            "Convert any GitHub repository into a clean, single <code>project_context.xml</code> file ready for AI models!\n\n"
            "⚡ <b>How to use:</b>\n"
            "1️⃣ <b>Upload a <code>.zip</code> archive file</b>, OR\n"
            "2️⃣ <b>Paste a GitHub repo link</b> (e.g., <code>https://github.com/owner/repo</code>)\n\n"
            "🌟 <b>Features:</b>\n"
            "- 🌲 ASCII Directory Tree & 🏷️ <b>Default XML Output Format</b>\n"
            "- 🧮 <code>tiktoken</code> Token Count & 🔒 Automatic Secret Redaction\n"
            "- 📥 <b>Direct Download</b> of XML/Markdown context files inside Telegram\n"
            "- 🗑️ <b>1-Tap Chat Clean Up</b> to delete all generated files/messages when done!"
        )
        bot.reply_to(message, welcome_text, parse_mode="HTML")

    @bot.message_handler(func=is_github_url_message)
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
            bot.reply_to(message, "⚠️ Please upload a valid <b>.zip</b> archive file.", parse_mode="HTML")
            return

        if doc.file_size and doc.file_size > MAX_TELEGRAM_FILE_BYTES:
            bot.reply_to(
                message,
                "⚠️ File exceeds Telegram's <b>20 MB</b> bot limit. Please upload a smaller <code>.zip</code> archive.",
                parse_mode="HTML"
            )
            return

        status_msg = bot.reply_to(message, "⏳ Downloading and processing your project <code>.zip</code> file...", parse_mode="HTML")

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
            sent_doc = bot.send_document(
                message.chat.id,
                doc_file,
                caption=summary,
                parse_mode="HTML",
                reply_to_message_id=message.message_id,
                reply_markup=markup
            )
            add_sent_message(bundle_id, sent_doc.message_id)

        if os.path.exists(output_tmp):
            os.remove(output_tmp)

        bot.delete_message(message.chat.id, status_msg.message_id)

    @bot.callback_query_handler(func=lambda call: True)
    def handle_callbacks(call):
        try:
            bot.answer_callback_query(call.id)
        except Exception:
            pass

        if call.data.startswith("clean_"):
            bundle_id = call.data.replace("clean_", "")
            bundle = get_bundle(bundle_id)

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
                try:
                    bot.answer_callback_query(call.id, "⚠️ Context expired. Please re-upload or re-paste link.", show_alert=True)
                except Exception:
                    pass
                return

            new_fmt = bundle['active_format']
            summary = build_summary_text(bundle, active_format=new_fmt)
            markup = build_keyboard(bundle_id, active_format=new_fmt)

            try:
                bot.edit_message_caption(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    caption=summary,
                    parse_mode="HTML",
                    reply_markup=markup
                )
            except Exception:
                pass

        elif call.data.startswith("copy_"):
            try:
                bot.answer_callback_query(call.id, "📥 Please use the Download button below to get your context file!", show_alert=True)
            except Exception:
                pass

        elif call.data.startswith("dl_"):
            bundle_id = call.data.replace("dl_", "")
            bundle = get_bundle(bundle_id)

            if not bundle:
                try:
                    bot.answer_callback_query(call.id, "⚠️ Context expired. Please re-upload or re-paste link.", show_alert=True)
                except Exception:
                    pass
                return

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
                    caption=f"📥 <b>Here is your <code>project_context{ext}</code> file:</b>",
                    parse_mode="HTML",
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
