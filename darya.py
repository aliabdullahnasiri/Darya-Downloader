import os
import pathlib
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Dict, List, Literal, Self, Tuple, Union
from urllib.parse import urlparse

import ffmpeg
import requests
from rich.prompt import Prompt

from functions import audio_bitrate2representation as ab2r
from functions import download_file
from functions import resolution2representation as r2r
from logger import logger


@dataclass
class Darya:
    item_identity: str

    def __post_init__(self: Self) -> None:
        self.DOWNLOAD_DIR: str = "downloads"
        self.ITEM_DIRECTORY: str = f"{self.DOWNLOAD_DIR}/{self.item_identity}"
        self.ITEM_OUTPUT_DIR: str = f"{self.ITEM_DIRECTORY}/output"
        self.MPDS_OUTPUT_DIR: str = f"{self.ITEM_DIRECTORY}/mpds"
        self.LICENSE_OUTPUT_DIR: str = f"{self.ITEM_DIRECTORY}/license"
        self.VIDEO_OUTPUT_DIR: str = f"{self.ITEM_DIRECTORY}/video"
        self.AUDIO_OUTPUT_DIR: str = f"{self.ITEM_DIRECTORY}/audio"
        self.THUMBNAIL_OUTPUT_DIR: str = f"{self.ITEM_DIRECTORY}/thumbnail"
        self.BG_OUTPUT_DIR: str = f"{self.ITEM_DIRECTORY}/background"

        os.makedirs(self.DOWNLOAD_DIR, exist_ok=True)
        os.makedirs(self.ITEM_DIRECTORY, exist_ok=True)
        os.makedirs(self.ITEM_OUTPUT_DIR, exist_ok=True)
        os.makedirs(self.ITEM_OUTPUT_DIR, exist_ok=True)
        os.makedirs(self.MPDS_OUTPUT_DIR, exist_ok=True)
        os.makedirs(self.LICENSE_OUTPUT_DIR, exist_ok=True)
        os.makedirs(self.VIDEO_OUTPUT_DIR, exist_ok=True)
        os.makedirs(self.AUDIO_OUTPUT_DIR, exist_ok=True)
        os.makedirs(self.THUMBNAIL_OUTPUT_DIR, exist_ok=True)
        os.makedirs(self.BG_OUTPUT_DIR, exist_ok=True)

    def get_item(self: Self) -> Union[Dict, None]:
        response: requests.Response = requests.get(
            f"https://ffprod2s3.b-cdn.net/c/278/catalog/d_35ePcIfifmsHJgZ7G_Yw/item/{self.item_identity}.json"
        )

        if response.status_code == 200:
            return response.json()

    def get_representations(
        self: Self,
        mpd_file: str,
        base_url: str,
    ) -> List[Dict]:

        tree = ET.parse(mpd_file)
        root = tree.getroot()

        # Namespaces used in the MPD file
        namespaces = {
            "": "urn:mpeg:dash:schema:mpd:2011",
            "xlink": "http://www.w3.org/1999/xlink",
            "cenc": "urn:mpeg:cenc:2013",
        }

        representations: List = []

        # Iterate through adaptation sets
        for adaptation_set in root.findall(".//AdaptationSet", namespaces):
            content_type = adaptation_set.get("contentType", "unknown")
            segment_template = adaptation_set.find("SegmentTemplate", namespaces)

            if segment_template is None:
                logger.warning(f"No SegmentTemplate found for {content_type!r}")

                continue

            # Extract the initialization and media template
            initialization = segment_template.get("initialization")
            media_template = segment_template.get("media")
            int(segment_template.get("startNumber", 1))

            # Download the initialization file for each representation
            for representation in adaptation_set.findall("Representation", namespaces):
                representation_dct = {}

                representation_id = representation_dct["representation-id"] = (
                    representation.get("id")
                )

                representation_dct["mime-type"] = representation.get("mimeType")

                if initialization and representation_id:
                    init_url = base_url + initialization.replace(
                        "$RepresentationID$", representation_id
                    )
                    representation_dct["init"] = init_url

                segments = representation_dct["segments"] = []

                # Download media segments using the SegmentTimeline
                segment_timeline = segment_template.find("SegmentTimeline", namespaces)
                if segment_timeline is not None:
                    time = 0

                    for segment in segment_timeline.findall("S", namespaces):
                        t = segment.get("t")
                        d = int(segment.get("d", 0))
                        r = int(segment.get("r", 0))

                        if t:
                            time = int(t)

                        for _ in range(r + 1):
                            if media_template and representation_id:
                                media_url = base_url + media_template.replace(
                                    "$RepresentationID$", representation_id
                                ).replace("$Time$", str(time))

                                segments.append(media_url)

                            time += d

                else:
                    logger.warning(
                        f"No SegmentTimeline found for Representation {representation_id!r}"
                    )

                representations.append(representation_dct)

        return representations

    def download_mpds(self: Self, mpds: List[str]) -> List[pathlib.Path]:
        paths: List[pathlib.Path] = []

        for mpd in mpds:
            path = f"downloads/mpds/{os.path.basename(mpd)}"

            if not os.path.exists(path):
                download_file(mpd, path)

            paths.append(pathlib.Path(path))

        return paths

    def download_thumbnail(self: Self) -> Union[pathlib.Path, None]:
        pass

    def download_background(self: Self) -> Union[pathlib.Path, None]:
        pass

    def download_license(self: Self) -> Union[pathlib.Path, None]:
        pass

    def download_media(
        self: Self,
        mpd: pathlib.Path,
        base: str,
        resolution: Literal[
            "1920x1080", "1280x720", "854x480", "426x240"
        ] = "1920x1080",
        audio: Literal["128k", "256k", "320k"] = "128k",
    ) -> Union[Tuple[bytes, bytes], None]:
        representations = self.get_representations(str(mpd), base)
        vrepr_id = r2r(resolution)
        arepr_id = ab2r(audio)
        representations = list(
            filter(
                lambda representation: representation["mime-type"] == "video/mp4"
                and representation["representation-id"] == vrepr_id
                or representation["mime-type"] == "audio/mp4"
                and representation["representation-id"] == arepr_id,
                representations,
            )
        )

        if len(representations) == 2:
            video_links: List[str] = []
            audio_links: List[str] = []

            for representation in representations:
                init_file = representation["init"]
                mime_type = representation["mime-type"]
                segments = representation["segments"]

                if mime_type == "video/mp4":
                    video_links.append(init_file)
                    video_links.extend(segments)
                elif mime_type == "audio/mp4":
                    audio_links.append(init_file)
                    audio_links.extend(segments)

            video_bytes: bytes = b""
            audio_bytes: bytes = b""

            for video_link in video_links:
                filename = os.path.basename(urlparse(video_link).path)
                path = f"{self.VIDEO_OUTPUT_DIR}/{filename}"

                if not os.path.exists(path):
                    download_file(video_link, path)
                else:
                    logger.info(f"The file '{path}' already exists.")

                if os.path.exists(path):
                    with open(path, "rb") as f:
                        video_bytes += f.read()

            for audio_link in audio_links:
                filename = os.path.basename(urlparse(audio_link).path)
                path = f"{self.AUDIO_OUTPUT_DIR}/{filename}"

                if not os.path.exists(path):
                    download_file(audio_link, path)
                else:
                    logger.info(f"The file '{path}' already exists.")

                if os.path.exists(path):
                    with open(path, "rb") as f:
                        audio_bytes += f.read()

            return video_bytes, audio_bytes

        else:
            logger.warning(
                "No matching video or audio representation ID was found. Please check the provided resolution or bitrate."
            )

    def merge_media(
        self: Self, video: bytes, audio: bytes, output: pathlib.Path
    ) -> Union[pathlib.Path, None]:
        if output.exists():
            choice = Prompt.ask(
                f"The output file '{output}' has been created. Do you want to keep it?",
                choices=["yes", "no"],
                show_default=True,
                default="yes",
            )

            if choice == "no":
                os.remove(output)

                logger.info(
                    "Output file '{output}' has been deleted at the user's request."
                )

            else:
                logger.info(f"Output file '{output}' has been kept.")

        if not output.exists():
            try:
                logger.info(f"Starting merge of video and audio into '{output}'.")

                video_path: pathlib.Path = pathlib.Path(
                    f"/tmp/{self.item_identity}-{uuid.uuid4()}.mp4"
                )
                audio_path: pathlib.Path = pathlib.Path(
                    f"/tmp/{self.item_identity}-{uuid.uuid4()}.mp3"
                )

                with open(video_path, "wb") as f:
                    f.write(video)

                with open(audio_path, "wb") as f:
                    f.write(audio)

                # Using ffmpeg-python to merge audio and video
                ffmpeg.output(
                    ffmpeg.input(video_path),
                    ffmpeg.input(audio_path),
                    str(output),
                    vcodec="copy",  # Copy the video stream without re-encoding
                    acodec="aac",  # Encode the audio in AAC format
                ).run()

                if output.exists():
                    logger.success(f"Successfully merged into '{output}'.")

                    return output
                else:
                    logger.error(
                        f"Merge failed: Output file '{output}' was not created."
                    )

            except ffmpeg.Error as e:
                logger.error(f"An error occurred while merging: {e.stderr.decode()}")
            except Exception as ex:
                logger.exception(f"An unexpected error occurred: {ex}")

    def download(
        self: Self,
        resolution: Literal[
            "1920x1080", "1280x720", "854x480", "426x240"
        ] = "1920x1080",
        audio: Literal["128k", "256k", "320k"] = "128k",
        output: Union[pathlib.Path, None] = None,
    ) -> None:
        item = self.get_item()

        if item and (item_media := item.get("trailer")):
            if not output:
                output = pathlib.Path(
                    f"{self.ITEM_OUTPUT_DIR}/{self.item_identity}.mp4"
                )

            media_identity = item.get("trailerID")
            mpds = item_media["mpds"]
            mpd = download_file(
                link := mpds.pop(0),
                f"{self.MPDS_OUTPUT_DIR}/{os.path.basename(urlparse(link).path)}",
            )

            if media_identity and mpd:
                media = self.download_media(
                    mpd,
                    f"https://ffprod2.b-cdn.net/c/278/m/{media_identity}.ism/",
                    resolution,
                    audio,
                )

                if media:
                    video_bytes, audio_bytes = media
                    self.merge_media(video_bytes, audio_bytes, output)
        else:
            logger.error(f"Failed to find item with ID: {self.item_identity!r}.")
