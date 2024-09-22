import subprocess


def run_deploy():
    subprocess.run(
        "poetry export -f requirements.txt --output finance_bot/requirements.txt --without-hashes",
        shell=True,
        check=True,
    )
    subprocess.run("sam build", shell=True, check=True)
    subprocess.run("sam deploy", shell=True, check=True)


if __name__ == "__main__":
    run_deploy()
