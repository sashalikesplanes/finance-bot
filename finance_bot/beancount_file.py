from asyncio.log import logger
import json
import os
from beancount import loader
from git import Repo


REPO_DIR = "/tmp/beancount-repo"
secrets = json.loads(os.environ["SECRETS"])
auth_repo_url = (
    f"https://{secrets['github_token']}@github.com/sashalikesplanes/beancount-file.git"
)


def clone_or_pull():
    if os.path.exists(REPO_DIR):
        logger.info(f"Updating existing repository at {REPO_DIR}")
        repo = Repo(REPO_DIR)
        repo.remotes.origin.pull()
    else:
        logger.info(f"Cloning repository to {REPO_DIR}")
        Repo.clone_from(auth_repo_url, REPO_DIR, depth=1)


def write_to_file(str):
    clone_or_pull()

    filename = os.path.join(REPO_DIR, "main.beancount")

    with open(filename, "r+") as f:
        content = f.read()
        future_marker = ";;; FUTURE ;;;"
        if future_marker in content:
            # Find the position of the future marker
            insert_position = content.index(future_marker)
            # Check if the character before the marker is a newline
            if insert_position > 0 and content[insert_position - 1] == "\n":
                insert_position -= 1
            if insert_position > 0 and content[insert_position - 1] == "\n":
                insert_position -= 1
            # Move the file pointer to the insert position
            f.seek(insert_position)
            # Read the rest of the file
            rest_of_file = f.read()
            # Move back to the insert position
            f.seek(insert_position)
            # Write the new content followed by a newline
            f.write(f"\n{str}\n")
            # Write the rest of the file
            f.write(rest_of_file)
        else:
            # If the future marker is not found, append to the end
            f.seek(0, 2)  # Move to the end of the file
            f.write(f"\n{str}\n")

    _, errors, _ = loader.load_file(filename, log_errors=logger.error)

    if errors:
        repo = Repo(REPO_DIR)
        repo.head.reset(index=True, working_tree=True)
        raise Exception(f"Error loading Beancount file: {errors}")

    repo = Repo(REPO_DIR)
    repo.index.add([filename])
    repo.index.commit(f"Telegram bot update")
    repo.remotes.origin.push()


def get_entries():
    clone_or_pull()

    # Load the Beancount file
    filename = os.path.join(REPO_DIR, "main.beancount")
    entries, errors, options = loader.load_file(filename, log_errors=logger.error)

    if errors:
        raise Exception(f"Error loading Beancount file: {errors}")

    return entries, options
