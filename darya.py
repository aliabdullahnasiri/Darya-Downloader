import os
import uuid
import pathlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Dict, List, Literal, Self, Union

import ffmpeg
import requests

from console import console
from functions import audio_bitrate2representation as ab2r
from functions import choose_mpd_file, download_file
from functions import resolution2representation as r2r
from logger import logger


@dataclass
class Darya:
    item_id: str

    def __post_init__(self: Self) -> None:
        if not os.path.exists("downloads"):
            os.mkdir("downloads")

        paths = ["audio", "video", "mpds", "output"]
        for path in paths:
            if not os.path.exists(f"downloads/{path}"):
                os.mkdir(f"downloads/{path}")

    def get_item(self: Self) -> Union[Dict, None]:
        response: requests.Response = requests.get(
            f"https://ffprod2s3.b-cdn.net/c/278/catalog/d_35ePcIfifmsHJgZ7G_Yw/item/{self.item_id}.json"
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

    def download(
        self: Self,
        resolution: Literal[
            "1920x1080", "1280x720", "854x480", "426x240"
        ] = "1920x1080",
        audio: Literal["128k", "256k", "320k"] = "128k",
        output: Union[pathlib.Path, None] = None,
    ) -> None:
        item = self.get_item()

        if item:
            item_id = item.get("mediaID") or item.get("trailerID")
            if item_media := item.get("media") or item.get("trailer"):
                mpds: List[pathlib.Path] = self.download_mpds(item_media["mpds"])

                en_title: str = item["title"]["en"]
                mpd: Union[pathlib.Path, None] = choose_mpd_file("downloads/mpds")

                if mpd:
                    representations = self.get_representations(
                        str(mpd),
                        f"https://ffprod2.b-cdn.net/c/278/m/{item_id}.ism/",
                    )
                    vrepr_id = r2r(resolution)
                    arepr_id = ab2r(audio)

                    representations = list(
                        filter(
                            lambda representation: representation["mime-type"]
                            == "video/mp4"
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

                        output_dir = "downloads"
                        video_output_dir = f"{output_dir}/video"
                        audio_output_dir = f"{output_dir}/audio"

                        if not os.path.exists(output_dir):
                            os.mkdir(output_dir)

                        if not os.path.exists(video_output_dir):
                            os.mkdir(video_output_dir)

                        if not os.path.exists(audio_output_dir):
                            os.mkdir(audio_output_dir)

                        video_files = []
                        for video_link in video_links:
                            video_filename = video_link.split("/").pop()
                            path = f"{video_output_dir}/{video_filename}"

                            if not os.path.exists(path):
                                download_file(video_link, path)
                            else:
                                console.print(f"File {path!r} already exists!")

                            video_files.append(path)

                        audio_files = []
                        for audio_link in audio_links:
                            audio_filename = audio_link.split("/").pop()
                            path = f"{audio_output_dir}/{audio_filename}"

                            if not os.path.exists(path):
                                download_file(audio_link, path)
                            else:
                                console.print(f"File [cyan]{path!r}[/] already exists!")

                            audio_files.append(path)

                        if output is None:
                            formatted_en_title = en_title.replace(" ", "-").lower()
                            media_output_dir = f"{output_dir}/output"

                            if not os.path.exists(media_output_dir):
                                os.mkdir(media_output_dir)

                            output = pathlib.Path(
                                f"{media_output_dir}/{formatted_en_title}-{resolution}-{item_id}.mp4"
                            )

                        video_bytes: bytes = b""
                        audio_bytes: bytes = b""

                        for video_file in video_files:
                            with open(video_file, "rb") as f:
                                video_bytes += f.read()

                        for audio_file in audio_files:
                            with open(audio_file, "rb") as f:
                                audio_bytes += f.read()

                        with open(video_path := f"/tmp/{uuid.uuid4()}.mp4", "wb") as f:
                            f.write(video_bytes)

                        with open(audio_path := f"/tmp/{uuid.uuid4()}.mp3", "wb") as f:
                            f.write(audio_bytes)

                        if not os.path.exists(output):
                            # Using ffmpeg-python to merge audio and video

                            ffmpeg.output(
                                ffmpeg.input(video_path),
                                ffmpeg.input(audio_path),
                                str(output),
                                vcodec="copy",  # Copy the video stream without re-encoding
                                acodec="aac",  # Encode the audio in AAC format
                            ).run()
                        else:
                            logger.warning(f"File already exists! {str(output)!r}")

                    else:
                        logger.warning(
                            "No matching video or audio representation ID was found. Please check the provided resolution or bitrate."
                        )
