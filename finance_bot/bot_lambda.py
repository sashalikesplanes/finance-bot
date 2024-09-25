import json
import asyncio
import os
import logging
from telegram._update import Update
from telegram.ext import ApplicationBuilder
from handlers import add_handlers


# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

secrets = json.loads(os.environ["SECRETS"])
logger = logging.getLogger(__name__)


# Global variable to store the initialized application
initialized_app = None


async def process_update_in_lambda(event, context):
    global initialized_app

    if initialized_app is None:
        app = ApplicationBuilder().token(secrets["telegram_token"]).build()
        app = add_handlers(app)
        await app.initialize()
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
    return asyncio.get_event_loop().run_until_complete(
        process_update_in_lambda(event, context)
    )
