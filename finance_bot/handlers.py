import datetime
import json
import os
import logging
from telegram import ForceReply, InlineKeyboardButton, InlineKeyboardMarkup
from telegram._update import Update
from telegram.constants import ChatAction
from beancount_file import write_to_file, get_entries
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
)

from constants import get_accounts, get_counterparties
from reports import generate_account_report, generate_monthly_budget_report

logger = logging.getLogger(__name__)
secrets = json.loads(os.environ["SECRETS"])


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
        n_months_ahead = 0

    if context.args and len(context.args) > 1:
        filtered = context.args[1].lower() != "full"
    else:
        filtered = True

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

    options["filtered"] = filtered
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
    ENTER_NARRATION,
    ENTER_PAYEE,
    SELECT_DATE,
    SELECT_TYPE,
    SELECT_INCOME,
    SELECT_COUNTERPARTY,
    SELECT_ACCOUNT,
    SUMMARY,
    CONFIRM_ENTRY,
) = range(9)


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
    return SELECT_TYPE


async def select_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Get user that sent /start and log his name
    if (
        update.message is None
        or context.user_data is None
        or update.effective_chat is None
    ):
        logger.warn(f"Update has no message")
        return ConversationHandler.END

    context.user_data["amount"] = update.message.text

    all_counterparties = get_counterparties()
    all_types = list(all_counterparties.keys())
    all_types.sort()
    keyboard = [
        [InlineKeyboardButton(type, callback_data=f"{type}")] for type in all_types
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    # Send message with text and appended InlineKeyboard
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Select type",
        reply_markup=reply_markup,
    )
    # Tell ConversationHandler that we're in state `FIRST` now
    return ENTER_NARRATION


async def enter_narration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if (
        update.callback_query is None
        or context.user_data is None
        or update.effective_chat is None
    ):
        logger.warn(f"Update has no message")
        return ConversationHandler.END

    query = update.callback_query
    await query.answer()

    context.user_data["type"] = query.data

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Enter the narration",
        reply_markup=ForceReply(input_field_placeholder="Buying Condoms"),
    )

    return ENTER_PAYEE


async def enter_payee(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if (
        update.message is None
        or context.user_data is None
        or update.effective_chat is None
    ):
        logger.warn(f"Update has no message")
        return ConversationHandler.END

    context.user_data["narration"] = update.message.text

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Enter the payee",
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
    return SELECT_COUNTERPARTY


async def select_counterparty(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Send message on `/start`."""
    # Get user that sent /start and log his name
    if update.callback_query is None or context.user_data is None:
        logger.warn(f"Update has no message")
        return ConversationHandler.END

    query = update.callback_query
    await query.answer()

    context.user_data["date"] = query.data

    all_counterparties = get_counterparties()

    if context.user_data["type"] not in all_counterparties:
        await query.edit_message_text("Invalid type")
        return ConversationHandler.END

    options = all_counterparties[context.user_data["type"]]

    keyboard = [
        [InlineKeyboardButton(category, callback_data=f"{category}")]
        for category in options
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    # Send message with text and appended InlineKeyboard
    await query.edit_message_text("Select a counterparty", reply_markup=reply_markup)
    # Tell ConversationHandler that we're in state `FIRST` now
    return SELECT_ACCOUNT


async def select_account_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
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

    context.user_data["counterparty"] = query.data
    keyboard = [
        [InlineKeyboardButton(account, callback_data=f"{account}")]
        for account in get_accounts()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text="Select an account", reply_markup=reply_markup)
    return SUMMARY


def user_data_to_entry(user_data: dict) -> str:

    current_year = datetime.datetime.now().year
    formatted_date = f"{current_year}-{user_data['date']}"

    entry_amount = user_data["amount"]
    if user_data["type"] == "Income":
        entry_amount = f"-{entry_amount}"

    entry_counterparty = f"{user_data['type']}:{user_data['counterparty']}"
    if user_data["type"] == "Transfer":
        entry_counterparty = f"{user_data['counterparty']}"

    narration = user_data["narration"]
    if narration == ".":
        narration = ""

    payee = user_data["payee"]
    if payee == ".":
        payee = ""

    new_entry = f'{formatted_date} * "{payee}" "{narration}"\n'
    new_entry += f"    {entry_counterparty} {entry_amount} EUR\n"
    new_entry += f"    {user_data['account']}"

    return new_entry


async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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

    new_entry = user_data_to_entry(context.user_data)

    await query.edit_message_text(
        text=f"Is the entry correct?\n<pre>{new_entry}</pre>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Yes", callback_data="yes"),
                    InlineKeyboardButton("No", callback_data="no"),
                ]
            ]
        ),
    )

    return CONFIRM_ENTRY


async def confirm_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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

    if query.data == "no":
        await query.edit_message_text(text="Entry cancelled")
        return ConversationHandler.END

    await query.edit_message_text(text="Adding entry...")
    new_entry = user_data_to_entry(context.user_data)

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

    await account_report(update, context)
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


def add_handlers(app: Application):

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
            CommandHandler("add", enter_amount, filters.User(user_id=allowed_user_ids))
        ],
        states={
            SELECT_TYPE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, select_type),
            ],
            ENTER_NARRATION: [
                CallbackQueryHandler(enter_narration),
            ],
            ENTER_PAYEE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_payee),
            ],
            SELECT_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, select_date),
            ],
            SELECT_COUNTERPARTY: [
                CallbackQueryHandler(select_counterparty),
            ],
            SELECT_ACCOUNT: [CallbackQueryHandler(select_account_handler)],
            SUMMARY: [
                CallbackQueryHandler(summary),
            ],
            CONFIRM_ENTRY: [
                CallbackQueryHandler(confirm_entry),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Add ConversationHandler to application that will be used for handling updates
    app.add_handlers([budget_handler, account_handler, add_handler])

    return app
