import datetime
import json
import asyncio
import os
import logging
import subprocess
from git import Repo

from telegram import ForceReply, InlineKeyboardButton, InlineKeyboardMarkup
from telegram._update import Update
from telegram.constants import ChatAction
from telegram._replykeyboardremove import ReplyKeyboardRemove
from telegram._replykeyboardmarkup import ReplyKeyboardMarkup
from beancount import loader
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
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


async def budget_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global secrets

    logger.info(f"Got update")
    if update.effective_chat is None:
        logger.warn(f"Update has no chat")
        return

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )

    REPO_DIR = "/tmp/beancount-repo"

    # Use the GitHub token from secrets
    github_token = secrets["github_token"]
    auth_repo_url = (
        f"https://{github_token}@github.com/sashalikesplanes/beancount-file.git"
    )

    try:

        if os.path.exists(REPO_DIR):
            logger.info(f"Updating existing repository at {REPO_DIR}")
            repo = Repo(REPO_DIR)
            repo.remotes.origin.pull()
        else:
            logger.info(f"Cloning repository to {REPO_DIR}")
            Repo.clone_from(auth_repo_url, REPO_DIR, depth=1)

        # Load the Beancount file
        filename = os.path.join(REPO_DIR, "main.beancount")
        entries, errors, options = loader.load_file(filename, log_errors=logger.error)

        if errors:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"Error loading Beancount file:\n{str(errors)}",
                parse_mode="HTML",
            )
            return

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
            parse_mode="HTML",
        )

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"An error occurred while fetching the latest data:\n{str(e)}",
            parse_mode="HTML",
        )


# Stages
ENTER_PAYEE, SELECT_DATE, SELECT_EXPENSE, SELECT_ACCOUNT, SUMMARY = range(5)


async def enter_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None or update.message.from_user is None:
        logger.warn(f"Update has no message")
        return ConversationHandler.END

    user = update.message.from_user
    logger.info("User %s started the conversation.", user.first_name)
    await update.message.reply_text(
        "Enter the amount in EUR",
        reply_markup=ForceReply(input_field_placeholder="420.69"),
    )
    return ENTER_PAYEE


async def enter_payee(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if (
        update.message is None
        or update.message.from_user is None
        or context.user_data is None
    ):
        logger.warn(f"Update has no message")
        return ConversationHandler.END

    context.user_data["amount"] = update.message.text

    user = update.message.from_user
    logger.info("User %s started the conversation.", user.first_name)
    await update.message.reply_text(
        "Enter the payee",
        reply_markup=ForceReply(input_field_placeholder="ALBERT HEIJN"),
    )
    return SELECT_DATE


async def select_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Get user that sent /start and log his name
    if (
        update.message is None
        or update.message.from_user is None
        or context.user_data is None
    ):
        logger.warn(f"Update has no message")
        return ConversationHandler.END
    # get dates from today to 6 days ago
    dates = [datetime.datetime.now() - datetime.timedelta(days=i) for i in range(6)]
    date_strs = [date.strftime("%m-%d") for date in dates]
    date_strs.sort()

    context.user_data["payee"] = update.message.text

    keyboard = [
        [
            InlineKeyboardButton(f"{date_str}", callback_data=f"{date_str}")
            for date_str in date_strs
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    # Send message with text and appended InlineKeyboard
    await update.message.reply_text("Select a date", reply_markup=reply_markup)
    # Tell ConversationHandler that we're in state `FIRST` now
    return SELECT_EXPENSE


async def select_expense(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Send message on `/start`."""
    # Get user that sent /start and log his name
    if update.callback_query is None or context.user_data is None:
        logger.warn(f"Update has no message")
        return ConversationHandler.END

    query = update.callback_query
    await query.answer()

    context.user_data["date"] = query.data

    keyboard = [
        [InlineKeyboardButton("Expenses:Coffee", callback_data=f"Expenses:Coffee")],
        [InlineKeyboardButton("Expenses:Food", callback_data=f"Expenses:Food")],
        [
            InlineKeyboardButton(
                "Expenses:Transportation",
                callback_data=f"Expenses:Transportation",
            )
        ],
        [
            InlineKeyboardButton(
                "Expenses:Entertainment",
                callback_data=f"Expenses:Entertainment",
            )
        ],
        [InlineKeyboardButton("Expenses:Other", callback_data=f"Expenses:Other")],
        [InlineKeyboardButton("Expenses:Kids", callback_data=f"Expenses:Kids")],
        [InlineKeyboardButton("Expenses:Rent", callback_data=f"Expenses:Rent")],
        [
            InlineKeyboardButton(
                "Expenses:Utilities",
                callback_data=f"Expenses:Utilities",
            )
        ],
        [
            InlineKeyboardButton(
                "Expenses:Insurance",
                callback_data=f"Expenses:Insurance",
            )
        ],
        [
            InlineKeyboardButton(
                "Expenses:Healthcare",
                callback_data=f"Expenses:Healthcare",
            )
        ],
        [InlineKeyboardButton("Expenses:Clothing", callback_data=f"Expenses:Clothing")],
        [InlineKeyboardButton("Expenses:Gifts", callback_data=f"Expenses:Gifts")],
        [InlineKeyboardButton("Expenses:Fees", callback_data=f"Expenses:Fees")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    # Send message with text and appended InlineKeyboard
    await query.edit_message_text(
        "Select an expense category", reply_markup=reply_markup
    )
    # Tell ConversationHandler that we're in state `FIRST` now
    return SELECT_ACCOUNT


async def select_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show new choice of buttons"""
    if (
        update.callback_query is None
        or update.callback_query.data is None
        or context.user_data is None
    ):
        logger.warn(f"Update has no callback query")
        return ConversationHandler.END

    query = update.callback_query
    await query.answer()

    context.user_data["expense"] = query.data

    keyboard = [
        [
            InlineKeyboardButton("Assets:ING", callback_data=f"Assets:ING"),
        ],
        [
            InlineKeyboardButton("Assets:Cash", callback_data=f"Assets:Cash"),
        ],
        [
            InlineKeyboardButton("Assets:Wise", callback_data=f"Assets:Wise"),
        ],
        [
            InlineKeyboardButton("Liabilities:Amex", callback_data=f"Liabilities:Amex"),
        ],
        [
            InlineKeyboardButton("Liabilities:Visa", callback_data=f"Liabilities:Visa"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text="Select an account", reply_markup=reply_markup)
    return SUMMARY


async def end(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Returns `ConversationHandler.END`, which tells the
    ConversationHandler that the conversation is over.
    """
    if (
        update.callback_query is None
        or update.callback_query.data is None
        or context.user_data is None
    ):
        logger.warn(f"Update has no callback query")
        return ConversationHandler.END

    context.user_data["account"] = update.callback_query.data
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        text=f"You are done. You chose {str(context.user_data)}"
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Returns `ConversationHandler.END`, which tells the
    ConversationHandler that the conversation is over.
    """
    if update.message is None:
        logger.warn(f"Update has no message")
        return ConversationHandler.END

    logger.info(f"User cancelled the operation")
    await update.message.reply_text("Operation cancelled")
    return ConversationHandler.END


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
        budget_handler = CommandHandler("budget", budget_report)

        app = ApplicationBuilder().token(secrets["telegram_token"]).build()
        logger.info(f"built app")
        app.add_handler(budget_handler)
        logger.info(f"added handlers")

        # Setup conversation handler with the states FIRST and SECOND
        # Use the pattern parameter to pass CallbackQueries with specific
        # data pattern to the corresponding handlers.
        # ^ means "start of line/string"
        # $ means "end of line/string"
        # So ^ABC$ will only allow 'ABC'
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("add", enter_amount)],
            states={
                ENTER_PAYEE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, enter_payee),
                ],
                SELECT_DATE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, select_date),
                ],
                SELECT_EXPENSE: [
                    CallbackQueryHandler(select_expense),
                ],
                SELECT_ACCOUNT: [CallbackQueryHandler(select_account)],
                SUMMARY: [
                    CallbackQueryHandler(end),
                ],
            },
            fallbacks=[CommandHandler("cancel", cancel)],
        )

        # Add ConversationHandler to application that will be used for handling updates
        app.add_handler(conv_handler)

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
