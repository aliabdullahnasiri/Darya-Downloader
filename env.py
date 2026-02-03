import os

from dotenv import load_dotenv

load_dotenv()


class Meta(type):
    def __getattr__(cls, name):
        return os.getenv(name, None)

    def __getattribute__(cls, name):
        return super().__getattribute__(name)


class Env(metaclass=Meta): ...


def main() -> None:
    pass


if __name__ == "__main__":
    main()
