"""Container entrypoint: initialise the MySQL schema, then exec the real command.

The application only starts if configuration is valid and RDS is reachable.
If not, the container exits non-zero and Docker's restart policy retries, so
the app comes up on its own once the database is available.
"""
import os
import sys

import init_db


def main() -> None:
    code = init_db.initialize()
    if code != init_db.EXIT_OK:
        sys.exit(code)
    if len(sys.argv) < 2:
        sys.exit("entrypoint.py: no command given")
    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == "__main__":
    main()
