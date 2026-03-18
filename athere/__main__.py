from .agent import run
from .config import Config


def main() -> None:
    run(Config())


if __name__ == "__main__":
    main()
