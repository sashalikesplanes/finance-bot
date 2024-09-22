import json
import asyncio
import sys

from telegram._update import Update
from beancount import loader
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)

from monthly_budget import generate_monthly_budget_report


# Test
application = (
    ApplicationBuilder().token("7594531489:AAFUxTUfSxkowaxpNTRSX2b7zY62S1YwTZs").build()
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat is None:
        return

    await context.bot.send_message(
        chat_id=update.effective_chat.id, text="I'm a bot, please talk to me!"
    )


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat is None:
        return

    filename = "main.beancount"
    entries, errors, options = loader.load_file(filename, log_errors=sys.stderr)

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


def lambda_handler(event, context):
    return asyncio.get_event_loop().run_until_complete(main(event, context))


async def main(event, context):
    start_handler = CommandHandler("start", start)
    application.add_handler(start_handler)

    echo_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), echo)
    application.add_handler(echo_handler)

    try:
        await application.initialize()
        await application.process_update(
            Update.de_json(json.loads(event["body"]), application.bot)
        )

        return {"statusCode": 200, "body": "Success"}

    except Exception as exc:
        return {"statusCode": 500, "body": "Failure"}
