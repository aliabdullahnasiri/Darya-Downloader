import io
import os
import pathlib
from pathlib import Path
from typing import Literal, Union

import ffmpeg
import requests
from rich.prompt import Prompt

from console import console
from logger import logger


def get_video_info(file_path: pathlib.Path):
    try:
        # Probe the file
        probe = ffmpeg.probe(file_path)

        # Look for the video stream
        video_stream = next(
            (stream for stream in probe["streams"] if stream["codec_type"] == "video"),
            None,
        )

        if not video_stream:
            return None

        out, _ = (
            ffmpeg.input(file_path, ss=1)  # Seek to 1 second
            .filter("scale", 320, -1)  # Resize to 320px width
            .output("pipe:", vframes=1, format="image2", vcodec="mjpeg")
            .run(capture_stdout=True, quiet=True)
        )

        thumb = io.BytesIO(out)
        thumb.name = "thumb.jpg"

        # Extract details
        return {
            "width": int(video_stream.get("width")),
            "height": int(video_stream.get("height")),
            "duration": float(video_stream.get("duration", 0)),
            "size_bytes": pathlib.Path(file_path).stat().st_size,
            "codec": video_stream.get("codec_name"),
            "bitrate": int(video_stream.get("bit_rate", 0)),
            "fps": eval(video_stream.get("avg_frame_rate")),  # Converts "30/1" to 30.0
            "thumb": thumb,
        }
    except ffmpeg.Error as e:
        print(f"Error: {e.stderr.decode()}")
        return None


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


def download_file(
    url: str, output: pathlib.Path, verbose: bool = False, retries: int = 5
) -> Union[pathlib.Path, None]:
    """Download a file from the given URL and save it to the output path."""
    try:
        if output.exists():
            return output

        response = requests.get(url, stream=True)

        if size := response.headers.get("content-length"):
            size = float(size)

        if response.status_code == 200:
            with open(output, "wb") as file:
                for chunk in response.iter_content(chunk_size=1024):
                    file.write(chunk)

            if verbose:
                if size:
                    logger.info(
                        f"Downloaded: <b>{output}</b> (<c>{format_size(size)}</c>)"
                    )
                else:
                    logger.info(f"Downloaded: <b>{output}</b>")

            return pathlib.Path(output)
        else:
            logger.error(f"Failed to download: {url} (Status: {response.status_code})")
    except requests.exceptions.ChunkedEncodingError:
        logger.warning("⚠ Connection interrupted. Run again to resume automatically.")

        if retries > 0:
            if output.exists():
                os.remove(output)
            return download_file(url, output, verbose, retries - 1)

    except Exception as e:
        logger.error("Error:", e)


def resolution2representation(
    resolution: Literal["1920x1080", "1280x720", "854x480", "426x240"]
) -> Union[str, None]:
    """
    Maps a video resolution to its corresponding representation ID for use in media processing.

    This function accepts a specific resolution as a string (e.g., "1920x1080") and returns the associated
    representation ID, which can be used to identify media streams in systems like MPEG-DASH.

    Parameters:
    ----------
    resolution : Literal["1920x1080", "1280x720", "854x480", "426x240"]
        The video resolution for which the corresponding representation ID is required.
        Accepted values are:
        - "1920x1080" (Full HD)
        - "1280x720" (HD)
        - "854x480" (SD)
        - "426x240" (Low resolution)

    Returns:
    -------
    Union[str, None]
        The corresponding representation ID as a string (e.g., "2880000" for "1920x1080").
        Returns `None` if the provided resolution is not in the predefined resolution map.

    Examples:
    --------
    >>> resolution2representation("1920x1080")
    '2880000'
    >>> resolution2representation("1280x720")
    '1280000'
    >>> resolution2representation("1024x768")  # Invalid resolution
    None

    Notes:
    -----
    - This function uses a predefined mapping (`resolution_map`) for resolution-to-representation conversion.
    - The function only supports the resolutions listed in the `resolution_map`.
      Any unsupported resolutions will return `None`.
    """
    resolution_map = {
        "1920x1080": "2880000",
        "1280x720": "1280000",
        "854x480": "568000",
        "426x240": "142000",
    }

    representation = resolution_map.get(resolution)

    return representation


def audio_bitrate2representation(
    bitrate: Literal["128k", "256k", "320k"]
) -> Union[str, None]:
    """
    Maps an audio bitrate to its corresponding representation ID for use in media processing.

    This function accepts a specific audio bitrate as a string (e.g., "128k") and returns the associated
    representation ID, which can be used to identify audio streams in systems like MPEG-DASH.

    Parameters:
    ----------
    bitrate : Literal["128k", "256k", "320k"]
        The audio bitrate for which the corresponding representation ID is required.
        Accepted values are:
        - "128k" (128 kbps)
        - "256k" (256 kbps)
        - "320k" (320 kbps)

    Returns:
    -------
    Union[str, None]
        The corresponding representation ID as a string (e.g., "128000" for "128k").
        Returns `None` if the provided bitrate is not in the predefined bitrate map.

    Examples:
    --------
    >>> audio_bitrate2representation("128k")
    '128000'
    >>> audio_bitrate2representation("256k")
    '256000'
    >>> audio_bitrate2representation("64k")  # Invalid bitrate
    None

    Notes:
    -----
    - This function uses a predefined mapping (`BITRATE_MAP`) for bitrate-to-representation conversion.
    - The function only supports the bitrates listed in the `BITRATE_MAP`.
      Any unsupported bitrates will return `None`.
    """
    # Bitrate dictionary map with representation IDs
    BITRATE_MAP = {
        "128k": "128000",
        "256k": "256000",
        "320k": "320000",
    }

    representation = BITRATE_MAP.get(bitrate)

    return representation


def format_size(size: float) -> str:
    """
    Convert a size in bytes to a human-readable format (KB, MB, GB, etc.).

    Args:
        size (int): The size in bytes.

    Returns:
        str: The size formatted as a string with appropriate units.
    """
    if size == 0:
        return "0 B"

    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    index = 0

    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1

    return f"{size:.2f} {units[index]}"
