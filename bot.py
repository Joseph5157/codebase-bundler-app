import os
import tempfile
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from bundler import process_zip_file
from store import save_bundle, get_bundle

load_dotenv()

TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
WEB_APP_DOMAIN = os.environ.get('RAILWAY_PUBLIC_DOMAIN', 'codebase-bundler-app-production.up.railway.app')
WEB_APP_URL = os.environ.get('WEB_APP_URL', f"https://{WEB_APP_DOMAIN}")

def format_bytes(size):
    if size < 1024:
        return f"{size} Bytes"
    elif size < 1024 * 1024:
        return f"{size / 1024:.2f} KB"
    else:
        return f"{size / (1024 * 1024):.2f} MB"

def create_bot():
    if not TOKEN:
        print("TELEGRAM_BOT_TOKEN environment variable not set. Bot disabled.")
        return None

    bot = telebot.TeleBot(TOKEN)

    @bot.message_handler(commands=['start', 'help'])
    def send_welcome(message):
        welcome_text = (
            "👋 **Welcome to the Project Context Bundler Bot!**\n\n"
            "Upload any GitHub repository **.zip** file here, and I will instantly bundle "
            "it into a single `project_context.txt` file ready for AI models!\n\n"
            "⚡ **Features:**\n"
            "- Ignores `node_modules`, `.git`, `venv`, `__pycache__`, & binary files\n"
            "- Formats clean file headers for ChatGPT, Claude, & Gemini\n"
            "- 📋 **1-Click Copy** & 📥 **Download** buttons included right in chat!\n\n"
            "📤 **Send any .zip file to get started!**"
        )
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🌐 Open Web App", url=WEB_APP_URL))
        bot.reply_to(message, welcome_text, parse_mode="Markdown", reply_markup=markup)

    @bot.message_handler(content_types=['document'])
    def handle_document(message):
        doc = message.document
        if not doc.file_name.lower().endswith('.zip'):
            bot.reply_to(message, "⚠️ Please upload a valid **.zip** archive file.", parse_mode="Markdown")
            return

        status_msg = bot.reply_to(message, "⏳ Downloading and processing your project `.zip` file...")

        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_file:
            tmp_path = tmp_file.name

        try:
            file_info = bot.get_file(doc.file_id)
            downloaded_bytes = bot.download_file(file_info.file_path)

            with open(tmp_path, 'wb') as f:
                f.write(downloaded_bytes)

            result = process_zip_file(tmp_path)

            text_content = result['text']
            file_count = result['file_count']
            total_lines = result['total_lines']
            total_bytes = result['total_bytes']

            # Save bundle into store
            bundle_id = save_bundle(
                text=text_content,
                file_count=file_count,
                total_lines=total_lines,
                total_bytes=total_bytes,
                filename=doc.file_name
            )

            copy_url = f"{WEB_APP_URL}/copy/{bundle_id}"

            summary = (
                "✅ **Project Context Bundled Successfully!**\n\n"
                f"📁 **Files Bundled:** `{file_count:,}`\n"
                f"📝 **Total Lines:** `{total_lines:,}`\n"
                f"📦 **Context Size:** `{format_bytes(total_bytes)}`\n\n"
                "👇 **Tap below to Copy or Download your full context:**"
            )

            # Create Inline Keyboard with 1-Click Copy Web Page, Download & Telegram Preview
            markup = InlineKeyboardMarkup(row_width=2)
            btn_copy_full = InlineKeyboardButton("📋 Copy Full Context", url=copy_url)
            btn_download = InlineKeyboardButton("📥 Download .txt", callback_data=f"dl_{bundle_id}")
            btn_preview = InlineKeyboardButton("💬 Chat Preview", callback_data=f"preview_{bundle_id}")
            
            markup.add(btn_copy_full)
            markup.add(btn_download, btn_preview)

            # Send document file with Inline Keyboard buttons
            output_tmp = os.path.join(tempfile.gettempdir(), "project_context.txt")
            with open(output_tmp, "w", encoding="utf-8") as f:
                f.write(text_content)

            with open(output_tmp, "rb") as doc_file:
                bot.send_document(
                    message.chat.id,
                    doc_file,
                    caption=summary,
                    parse_mode="Markdown",
                    reply_to_message_id=message.message_id,
                    reply_markup=markup
                )

            # Clean up output file
            if os.path.exists(output_tmp):
                os.remove(output_tmp)

            # Delete status message
            bot.delete_message(message.chat.id, status_msg.message_id)

        except Exception as e:
            bot.edit_message_text(f"❌ Error processing zip file: {str(e)}", message.chat.id, status_msg.message_id)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    @bot.callback_query_handler(func=lambda call: True)
    def handle_callbacks(call):
        if call.data.startswith("preview_"):
            bundle_id = call.data.replace("preview_", "")
            bundle = get_bundle(bundle_id)

            if not bundle:
                bot.answer_callback_query(call.id, "⚠️ Context expired or not found. Please re-upload your zip file.", show_alert=True)
                return

            text_content = bundle['text']
            bot.answer_callback_query(call.id, "📋 Preparing chat preview...", show_alert=False)

            if len(text_content) <= 3800:
                copy_msg = (
                    "💬 **Tap the code block below to copy:**\n\n"
                    f"```text\n{text_content}\n```"
                )
            else:
                snippet = text_content[:3500]
                copy_msg = (
                    "💬 **Tap code block below to copy preview:**\n\n"
                    f"```text\n{snippet}\n```\n\n"
                    f"🔗 *To copy the ENTIRE context without truncation, tap the [📋 Copy Full Context] button!*"
                )

            bot.send_message(call.message.chat.id, copy_msg, parse_mode="Markdown", reply_to_message_id=call.message.message_id)

        elif call.data.startswith("dl_"):
            bundle_id = call.data.replace("dl_", "")
            bundle = get_bundle(bundle_id)

            if not bundle:
                bot.answer_callback_query(call.id, "⚠️ Context expired. Please re-upload your zip file.", show_alert=True)
                return

            bot.answer_callback_query(call.id, "📥 Preparing download file...", show_alert=False)

            text_content = bundle['text']
            output_tmp = os.path.join(tempfile.gettempdir(), "project_context.txt")
            with open(output_tmp, "w", encoding="utf-8") as f:
                f.write(text_content)

            with open(output_tmp, "rb") as doc_file:
                bot.send_document(
                    call.message.chat.id,
                    doc_file,
                    caption="📥 **Here is your `project_context.txt` file:**",
                    parse_mode="Markdown",
                    reply_to_message_id=call.message.message_id
                )

            if os.path.exists(output_tmp):
                os.remove(output_tmp)

    return bot

def run_bot():
    bot = create_bot()
    if bot:
        print("Starting Telegram Bot polling loop...")
        bot.infinity_polling()

if __name__ == '__main__':
    run_bot()
