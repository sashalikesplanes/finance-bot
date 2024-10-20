import base64
import json
import os
import requests
from beancount import loader
from asyncio.log import logger

REPO_OWNER = "sashalikesplanes"
REPO_NAME = "beancount-file"
FILE_PATH = "main.beancount"
secrets = json.loads(os.environ["SECRETS"])
GITHUB_TOKEN = secrets["github_token"]


def _get_file_content():
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


def write_to_file(str):
    file_data = _get_file_content()
    content = file_data["content"]
    decoded_content = base64.b64decode(content).decode("utf-8")

    future_marker = ";;; FUTURE ;;;"
    if future_marker in decoded_content:
        # Find the position of the future marker
        insert_position = decoded_content.index(future_marker)
        # Check if the character before the marker is a newline
        if insert_position > 0 and decoded_content[insert_position - 1] == "\n":
            insert_position -= 1
        if insert_position > 0 and decoded_content[insert_position - 1] == "\n":
            insert_position -= 1
        # Insert the new content
        updated_content = (
            decoded_content[:insert_position]
            + f"\n{str}\n"
            + decoded_content[insert_position:]
        )
    else:
        # If the future marker is not found, append to the end
        updated_content = decoded_content + f"\n{str}\n"

    # Validate the updated content
    _, errors, _ = loader.load_string(updated_content, log_errors=logger.error)

    if errors:
        raise Exception(f"Error loading Beancount file: {errors}")

    # Update the file on GitHub
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    data = {
        "message": "Telegram bot update",
        "content": base64.b64encode(updated_content.encode()).decode(),
        "sha": file_data["sha"],
    }
    response = requests.put(url, headers=headers, json=data)
    response.raise_for_status()


def get_entries():
    file_data = _get_file_content()
    content = file_data["content"]
    decoded_content = base64.b64decode(content).decode("utf-8")

    # Load the Beancount file
    entries, errors, options = loader.load_string(
        decoded_content, log_errors=logger.error
    )

    if errors:
        raise Exception(f"Error loading Beancount file: {errors}")

    return entries, options
