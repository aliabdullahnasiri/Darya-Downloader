import re
from typing import Literal, Optional

import click

from console import console
from darya import Darya

SLICE_RE = re.compile(r"^(-?\d*)?:(-?\d*)?(?::(-?\d+))?$")


class SliceType(click.ParamType):
    name = "slice"

    def convert(self, value, param, ctx):
        if not SLICE_RE.match(value):
            self.fail(
                f"{value!r} is not a valid slice (start:stop[:step])",
                param,
                ctx,
            )

        start, stop, step = (value + "::").split(":")[:3]

        def to_int(x):
            return int(x) if x else None

        return slice(to_int(start), to_int(stop), to_int(step))


def send_to_telegram_callback(obj: Darya) -> None:
    console.print("Send to Telegram!!!", obj)
    console.print(obj.media)


def send_to_youtube_callback(obj: Darya) -> None:
    console.print("Send to Youtube!!!", obj)
    console.print(obj.media)


@click.group()
def main() -> None: ...


@main.command()
@click.option(
    "--item-id",
    required=True,
    help="The unique identifier of the media item to download. This ID is used to locate and retrieve the specific media file or representation.",
)
@click.option(
    "--resolution",
    type=click.Choice(
        ["1920x1080", "1280x720", "854x480", "426x240"], case_sensitive=False
    ),
    default="1920x1080",
    help="Specify the media representation resolution to download.",
)
@click.option(
    "--audio",
    type=click.Choice(["128k", "256k", "320k"], case_sensitive=False),
    default="128k",
    help="Specify the audio bitrate representation to download (e.g., 128k).",
)
@click.option(
    "--range",
    "range_",
    type=SliceType(),
    help="Python slice like 1:10:2",
)
@click.option("--threads", type=int, default=10)
@click.option("--verbose", is_flag=True, default=False)
@click.option("--send-to-telegram", is_flag=True, default=False)
@click.option("--send-to-youtube", is_flag=True, default=False)
def download(
    item_id: str,
    resolution: Literal[
        "1920x1080",
        "1280x720",
        "854x480",
        "426x240",
    ] = "1920x1080",
    audio: Literal["128k", "256k", "320k"] = "128k",
    range_: Optional[slice] = None,
    threads: int = 10,
    verbose: bool = False,
    send_to_telegram: bool = False,
    send_to_youtube: bool = False,
) -> None:
    install_bento4()

    Darya.banner()

    darya: Darya = Darya(item_id, resolution, audio, range_, threads, verbose)

    callback = None

    if send_to_telegram:
        callback = send_to_telegram_callback
    elif send_to_youtube:
        callback = send_to_youtube_callback

    darya.download(
        callback=lambda obj: (
            callback(obj)
            if callback is not None
            else console.print(obj) if verbose else None
        )
    )


if __name__ == "__main__":
    main()
