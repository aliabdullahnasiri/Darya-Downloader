from pathlib import Path
from typing import Union

import requests
from rich.prompt import Prompt

from console import console
from logger import logger


def choose_mpd_file(directory: str = "downloads/mpds") -> Union[Path, None]:
    """
    Prompt the user to select an MPD file from a list of files in the given directory.

    Args:
        directory (str): The directory to search for MPD files (default: current directory).

    Returns:
        Path: The path of the selected MPD file.
    """
    path = Path(directory)

    # Get all MPD files in the directory
    mpd_files = list(path.glob("*.mpd"))

    if not mpd_files:
        console.print("[red]No MPD files found in the directory.[/red]")

        return None

    # Display the files to the user
    console.print("[bold cyan]Available MPD files:[/bold cyan]")
    for index, file in enumerate(mpd_files, start=1):
        console.print(f"[green]{index}[/green]: {file.name}")

    # Prompt the user to select a file
    choice = Prompt.ask(
        "[bold yellow]Choose a file by entering the number[/bold yellow]",
        choices=[str(i) for i in range(1, len(mpd_files) + 1)],
    )

    # Return the selected file
    selected_file = mpd_files[int(choice) - 1]
    console.print(f"[bold green]You selected:[/bold green] {selected_file}")

    return selected_file


def download_file(url: str, output_path: str):
    """Download a file from the given URL and save it to the output path."""
    response = requests.get(url, stream=True)
    if response.status_code == 200:
        with open(output_path, "wb") as file:
            for chunk in response.iter_content(chunk_size=1024):
                file.write(chunk)
        logger.info(f"Downloaded: {output_path}")
    else:
        logger.error(f"Failed to download: {url} (Status: {response.status_code})")
