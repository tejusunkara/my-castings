"""Create the API's two secrets as SSM SecureString parameters, before the first deploy:

    uv run python scripts/aws/create_app_secrets.py            # create missing ones
    uv run python scripts/aws/create_app_secrets.py --replace  # also replace existing ones

- /my-castings/auth-password-hash: you type the login password (hidden); only its scrypt
  hash is stored.
- /my-castings/jwt-secret: a random session-signing key. Replacing it logs everyone out.

Values go straight to SSM through the API, never on a command line. After replacing
either one, restart the API service so tasks pick up the new value.
"""

import argparse
import getpass
import os
import secrets
import sys
from pathlib import Path

from _stack import client

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps/api"))
from app.services.auth import hash_password  # noqa: E402

PASSWORD_HASH = "/my-castings/auth-password-hash"
JWT_SECRET = "/my-castings/jwt-secret"


def exists(ssm, name: str) -> bool:
    try:
        ssm.get_parameter(Name=name)
        return True
    except ssm.exceptions.ParameterNotFound:
        return False


def put(ssm, name: str, value: str, description: str) -> None:
    ssm.put_parameter(
        Name=name, Value=value, Type="SecureString", Overwrite=True, Description=description
    )
    print(f"stored {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--replace", action="store_true", help="replace existing values")
    replace = parser.parse_args().replace
    ssm = client("ssm")

    if replace or not exists(ssm, PASSWORD_HASH):
        password = getpass.getpass("Login password for the deployed app: ")
        if len(password) < 12:
            sys.exit("Use at least 12 characters: this login is on the public internet.")
        if getpass.getpass("Again: ") != password:
            sys.exit("The passwords don't match.")
        put(ssm, PASSWORD_HASH, hash_password(password), "scrypt hash of the login password")
    else:
        print(f"{PASSWORD_HASH} exists; kept (use --replace to change it)")

    if replace or not exists(ssm, JWT_SECRET):
        put(ssm, JWT_SECRET, secrets.token_urlsafe(48), "session-cookie signing key")
    else:
        print(f"{JWT_SECRET} exists; kept")


if __name__ == "__main__":
    os.chdir(Path(__file__).resolve().parents[2])
    main()
