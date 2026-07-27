import os
import tempfile
import telebot
from dotenv import load_dotenv
from bundler import process_zip_file

load_dotenv()

TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')


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
            "- Returns a direct downloadable `project_context.txt` file!"
        )
        bot.reply_to(message, welcome_text, parse_mode="Markdown")

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

            summary = (
                "✅ **Project Context Bundled Successfully!**\n\n"
                f"📁 **Files Bundled:** {file_count:,}\n"
                f"📝 **Total Lines:** {total_lines:,}\n"
                f"📦 **Context Size:** {format_bytes(total_bytes)}\n\n"
                "Here is your `project_context.txt` file ready for AI prompt context:"
            )

            # Send as document file
            output_tmp = os.path.join(tempfile.gettempdir(), "project_context.txt")
            with open(output_tmp, "w", encoding="utf-8") as f:
                f.write(text_content)

            with open(output_tmp, "rb") as doc_file:
                bot.send_document(
                    message.chat.id,
                    doc_file,
                    caption=summary,
                    parse_mode="Markdown",
                    reply_to_message_id=message.message_id
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

    return bot

def run_bot():
    bot = create_bot()
    if bot:
        print("Starting Telegram Bot polling loop...")
        bot.infinity_polling()

if __name__ == '__main__':
    run_bot()
