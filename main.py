from typing import Literal

import click

from darya import Darya


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
@click.option("--threads", type=int, default=10)
@click.option("--verbose", is_flag=True, default=False)
def download(
    item_id: str,
    resolution: Literal[
        "1920x1080",
        "1280x720",
        "854x480",
        "426x240",
    ] = "1920x1080",
    audio: Literal["128k", "256k", "320k"] = "128k",
    threads: int = 10,
    verbose: bool = False,
) -> None:
    Darya.banner()

    darya: Darya = Darya(item_id, resolution, audio, threads, verbose)
    darya.download()


if __name__ == "__main__":
    main()
