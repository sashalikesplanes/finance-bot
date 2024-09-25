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

    with open(os.path.join(REPO_DIR, "main.beancount"), "a") as f:
        f.write(f"\n{str}")

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
