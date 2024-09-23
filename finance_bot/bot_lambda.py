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


async def budget_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        budget_handler = MessageHandler(
            filters.TEXT & (~filters.COMMAND), budget_report
        )

        app = ApplicationBuilder().token(secrets["telegram_token"]).build()
        logger.info(f"built app")
        app.add_handler(budget_handler)
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
