import json
import asyncio
import os
import logging
import subprocess

from telegram._update import Update
from telegram._replykeyboardremove import ReplyKeyboardRemove
from telegram._replykeyboardmarkup import ReplyKeyboardMarkup
from beancount import loader
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
)

from monthly_budget import generate_monthly_budget_report

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

GENDER, PHOTO, LOCATION, BIO = range(4)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the conversation and asks the user about their gender."""
    reply_keyboard = [["Boy", "Girl", "Other"]]

    if update.message is None:
        return ConversationHandler.END

    await update.message.reply_text(
        "Hi! My name is Professor Bot. I will hold a conversation with you. "
        "Send /cancel to stop talking to me.\n\n"
        "Are you a boy or a girl?",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard,
            one_time_keyboard=True,
            input_field_placeholder="Boy or Girl?",
        ),
    )

    return GENDER


async def gender(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the selected gender and asks for a photo."""
    if update.message is None or update.message.from_user is None:
        return ConversationHandler.END

    user = update.message.from_user
    logger.info("Gender of %s: %s", user.first_name, update.message.text)
    await update.message.reply_text(
        "I see! Please send me a photo of yourself, "
        "so I know what you look like, or send /skip if you don't want to.",
        reply_markup=ReplyKeyboardRemove(),
    )

    return PHOTO


async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the photo and asks for a location."""
    if update.message is None or update.message.from_user is None:
        return ConversationHandler.END

    user = update.message.from_user
    photo_file = await update.message.photo[-1].get_file()
    await photo_file.download_to_drive("user_photo.jpg")
    logger.info("Photo of %s: %s", user.first_name, "user_photo.jpg")
    await update.message.reply_text(
        "Gorgeous! Now, send me your location please, or send /skip if you don't want to."
    )

    return LOCATION


async def skip_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Skips the photo and asks for a location."""
    if update.message is None or update.message.from_user is None:
        return ConversationHandler.END

    user = update.message.from_user
    logger.info("User %s did not send a photo.", user.first_name)
    await update.message.reply_text(
        "I bet you look great! Now, send me your location please, or send /skip."
    )

    return LOCATION


async def location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the location and asks for some info about the user."""
    if (
        update.message is None
        or update.message.from_user is None
        or update.message.location is None
    ):
        return ConversationHandler.END

    user = update.message.from_user
    user_location = update.message.location
    logger.info(
        "Location of %s: %f / %f",
        user.first_name,
        user_location.latitude,
        user_location.longitude,
    )
    await update.message.reply_text(
        "Maybe I can visit you sometime! At last, tell me something about yourself."
    )

    return BIO


async def skip_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Skips the location and asks for info about the user."""
    if update.message is None or update.message.from_user is None:
        return ConversationHandler.END

    user = update.message.from_user
    logger.info("User %s did not send a location.", user.first_name)
    await update.message.reply_text(
        "You seem a bit paranoid! At last, tell me something about yourself."
    )

    return BIO


async def bio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the info about the user and ends the conversation."""
    if update.message is None or update.message.from_user is None:
        return ConversationHandler.END

    user = update.message.from_user
    logger.info("Bio of %s: %s", user.first_name, update.message.text)
    await update.message.reply_text("Thank you! I hope we can talk again some day.")

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the conversation."""
    if update.message is None or update.message.from_user is None:
        return ConversationHandler.END

    user = update.message.from_user
    logger.info("User %s canceled the conversation.", user.first_name)
    await update.message.reply_text(
        "Bye! I hope we can talk again some day.", reply_markup=ReplyKeyboardRemove()
    )

    return ConversationHandler.END


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global secrets

    logger.info(f"Got update")
    if update.effective_chat is None:
        return

    REPO_DIR = "/tmp/beancount-repo"

    # Use the GitHub token from secrets
    github_token = secrets["github_token"]
    auth_repo_url = (
        f"https://{github_token}@github.com/sashalikesplanes/beancount-file.git"
    )

    try:
        if os.path.exists(REPO_DIR):
            logger.info(f"Updating existing repository at {REPO_DIR}")
            subprocess.run(
                ["/opt/bin/git", "-C", REPO_DIR, "pull", "origin", "main"], check=True
            )
        else:
            logger.info(f"Cloning repository to {REPO_DIR}")
            subprocess.run(
                ["/opt/bin/git", "clone", "--depth", "1", auth_repo_url, REPO_DIR],
                check=True,
            )

        # Load the Beancount file
        filename = os.path.join(REPO_DIR, "main.beancount")
        entries, errors, options = loader.load_file(filename, log_errors=logger.error)

        options["filtered"] = True
        options["n_months_ahead"] = 0

        accounts, income_assigned, last_date = generate_monthly_budget_report(
            entries, options
        )

        # construct a table with accounts and assigned and available
        table = f"Budget Report for {last_date.strftime('%B %Y')}\n\n"
        table += "<pre>\n"
        table += "| Account           | Assigned  | Available |\n"
        table += "|-------------------|----------:|----------:|\n"
        for account in accounts:
            table += f"| {account['account_name']:<17} | {account['assigned_this_month']:9.2f} | {account['remaining']:9.2f} |\n"
        table += "</pre>"

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=table,
            # text="hello",
            parse_mode="HTML",
        )

    except subprocess.CalledProcessError as e:
        logger.error(f"Error in Git operations: {str(e)}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="An error occurred while fetching the latest data.",
            parse_mode="HTML",
        )
        return
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="An error occurred while fetching the latest data.",
            parse_mode="HTML",
        )
        return


# Global variable to store the initialized application
initialized_app = None
secrets = {}


async def get_secrets():
    global secrets
    secrets = json.loads(os.environ["SECRETS"])


async def main(event, context):
    global initialized_app
    global secrets

    if initialized_app is None:
        logger.info(f"Getting secrets")

        await get_secrets()
        logger.info(
            f"Got secrets: github_token: {secrets['github_token'][:5]}..., telegram_token: {secrets['telegram_token'][:5]}..."
        )

        # Initialize the application only if it hasn't been initialized yet
        echo_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), echo)

        # Add conversation handler with the states GENDER, PHOTO, LOCATION and BIO
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("start", start)],
            states={
                GENDER: [MessageHandler(filters.Regex("^(Boy|Girl|Other)$"), gender)],
                PHOTO: [
                    MessageHandler(filters.PHOTO, photo),
                    CommandHandler("skip", skip_photo),
                ],
                LOCATION: [
                    MessageHandler(filters.LOCATION, location),
                    CommandHandler("skip", skip_location),
                ],
                BIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, bio)],
            },
            fallbacks=[CommandHandler("cancel", cancel)],
        )

        app = ApplicationBuilder().token(secrets["telegram_token"]).build()
        logger.info(f"built app")
        app.add_handler(conv_handler)
        app.add_handler(echo_handler)
        logger.info(f"added handlers")

        # Initialize the application
        logger.info(f"initializing app")
        await app.initialize()
        logger.info(f"initialized app")
        initialized_app = app

    try:
        # Process the update using the initialized application
        await initialized_app.process_update(
            Update.de_json(json.loads(event["body"]), initialized_app.bot)
        )
        return {"statusCode": 200, "body": "Success"}

    except Exception as exc:
        logger.error(exc)
        return {"statusCode": 500, "body": "Failure"}


def lambda_handler(event, context):
    return asyncio.get_event_loop().run_until_complete(main(event, context))
