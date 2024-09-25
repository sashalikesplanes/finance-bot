import datetime
import json
import asyncio
import os
import logging
from telegram import ForceReply, InlineKeyboardButton, InlineKeyboardMarkup
from telegram._update import Update
from telegram.constants import ChatAction
from beancount_file import write_to_file, get_entries
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
)

from reports import generate_account_report, generate_monthly_budget_report


# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def budget_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Got update")
    if update.effective_chat is None:
        logger.warn(f"Update has no chat")
        return

    # Get the first argument
    if context.args and len(context.args) > 0:
        try:
            n_months_ahead = int(context.args[0])
            if n_months_ahead < 0:
                raise ValueError("Number must be positive")
        except ValueError:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Error: Please provide a positive integer for the number of months ahead.",
                parse_mode="HTML",
            )
            return
    else:
        n_months_ahead = 0  # Default value if no argument is provided

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )

    try:
        entries, options = get_entries()
    except Exception as e:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Error loading Beancount file:\n{str(e)}",
            parse_mode="HTML",
        )
        return

    options["filtered"] = True
    options["n_months_ahead"] = n_months_ahead

    table = generate_monthly_budget_report(entries, options)

    # construct a table with accounts and assigned and available
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=table,
        parse_mode="HTML",
    )


async def account_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Got update")
    if update.effective_chat is None:
        logger.warn(f"Update has no chat")
        return

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )

    try:
        entries, options = get_entries()
    except Exception as e:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Error loading Beancount file:\n{str(e)}",
            parse_mode="HTML",
        )
        return

    table = generate_account_report(entries, options)

    # construct a table with accounts and assigned and available
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=table,
        parse_mode="HTML",
    )


# Stages
(
    ENTER_PAYEE,
    SELECT_DATE,
    SELECT_TYPE,
    SELECT_INCOME,
    SELECT_CATEGORY,
    SELECT_ACCOUNT,
    SUMMARY,
) = range(7)


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
    return SELECT_TYPE


async def select_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Get user that sent /start and log his name
    if update.callback_query is None or context.user_data is None:
        logger.warn(f"Update has no message")
        return ConversationHandler.END
    # get dates from today to 6 days ago
    dates = [datetime.datetime.now() - datetime.timedelta(days=i) for i in range(6)]
    date_strs = [date.strftime("%m-%d") for date in dates]
    date_strs.sort()

    query = update.callback_query
    await query.answer()
    context.user_data["date"] = query.data

    keyboard = [
        [
            InlineKeyboardButton("Income", callback_data="Income"),
            InlineKeyboardButton(
                "Expenses:Variable", callback_data="Expenses:Variable"
            ),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    # Send message with text and appended InlineKeyboard
    await update.callback_query.edit_message_text(
        "Select type", reply_markup=reply_markup
    )
    # Tell ConversationHandler that we're in state `FIRST` now
    return SELECT_CATEGORY


async def select_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Send message on `/start`."""
    # Get user that sent /start and log his name
    if update.callback_query is None or context.user_data is None:
        logger.warn(f"Update has no message")
        return ConversationHandler.END

    query = update.callback_query
    await query.answer()

    context.user_data["type"] = query.data

    all_categories = {
        "Expenses:Variable": [
            "HouseTax",
            "Transport",
            "LuxTrip24Oct",
            "TurkeyTrip24Oct",
            "PersonalCare",
            "BankFees",
            "MyLove",
            "EatOut",
            "Tobacco",
            "Clothes",
            "Family",
            "Education",
            "Party",
            "Forgotten",
            "Groceries",
        ],
        "Income": ["NL:Fung:Salary", "Interest"],
    }

    if context.user_data["type"] not in all_categories:
        await query.edit_message_text("Invalid type")
        return ConversationHandler.END

    categories = all_categories[context.user_data["type"]]

    keyboard = [
        [InlineKeyboardButton(category, callback_data=f"{category}")]
        for category in categories
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

    context.user_data["category"] = query.data
    accounts = [
        "Assets:NL:ING:Checking59",
        "Assets:NL:ING:Checking34",
        "Assets:BE:WISE:Checking",
        "Assets:BE:WISE:Savings",
        "Assets:BE:WISE:Investments",
        "Liabilities:NL:AMEX:Green",
        "Liabilities:NL:ING:CreditCard",
    ]

    keyboard = [
        [InlineKeyboardButton(account, callback_data=f"{account}")]
        for account in accounts
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
        or update.effective_chat is None
    ):
        logger.warn(f"Update has no callback query")
        return ConversationHandler.END

    query = update.callback_query
    await query.answer()

    context.user_data["account"] = update.callback_query.data

    current_year = datetime.datetime.now().year
    formatted_date = f"{current_year}-{context.user_data['date']}"

    entry_amount = context.user_data["amount"]
    if context.user_data["type"] == "Income":
        entry_amount = f"-{entry_amount}"

    new_entry = f"{formatted_date} * \"{context.user_data['payee']}\"\n"
    new_entry += f"    {context.user_data['type']}:{context.user_data['category']} {entry_amount} EUR\n"
    new_entry += f"    {context.user_data['account']}"

    await query.edit_message_text(
        text=f"Summary:\n<pre>{new_entry}</pre>", parse_mode="HTML"
    )
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )
    try:
        write_to_file(new_entry)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Entry added successfully",
        )
    except Exception as e:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Error writing to Beancount file:\n{str(e)}",
            parse_mode="HTML",
        )

    await budget_report(update, context)
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


async def main(event, context):
    global initialized_app

    secrets = json.loads(os.environ["SECRETS"])

    if initialized_app is None:
        app = ApplicationBuilder().token(secrets["telegram_token"]).build()

        allowed_user_ids = [int(secrets["sasha_user_id"])]

        budget_handler = CommandHandler(
            "budget", budget_report, filters.User(user_id=allowed_user_ids)
        )
        account_handler = CommandHandler(
            "accounts",
            account_report,
            filters.User(user_id=allowed_user_ids),
        )
        add_handler = ConversationHandler(
            entry_points=[
                CommandHandler(
                    "add", enter_amount, filters.User(user_id=allowed_user_ids)
                )
            ],
            states={
                ENTER_PAYEE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, enter_payee),
                ],
                SELECT_DATE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, select_date),
                ],
                SELECT_TYPE: [
                    CallbackQueryHandler(select_type),
                ],
                SELECT_CATEGORY: [
                    CallbackQueryHandler(select_category),
                ],
                SELECT_ACCOUNT: [CallbackQueryHandler(select_account)],
                SUMMARY: [
                    CallbackQueryHandler(end),
                ],
            },
            fallbacks=[CommandHandler("cancel", cancel)],
        )

        # Add ConversationHandler to application that will be used for handling updates
        app.add_handlers([budget_handler, account_handler, add_handler])

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
