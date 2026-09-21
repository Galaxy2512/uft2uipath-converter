# Entry point for `python -m uft2uipath`; delegates straight to the CLI's
# main() function defined in cli.py.
from .cli import main

if __name__ == "__main__":
    main()