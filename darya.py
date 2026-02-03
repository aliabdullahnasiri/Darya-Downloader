import asyncio
import copy
import json
import os
import pathlib
import random
import re
import subprocess
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from io import FileIO
from os.path import basename
from typing import Dict, List, Literal, Self, Union
from urllib.parse import urlparse

import pyfiglet
import requests
from rich.traceback import install
from werkzeug.utils import secure_filename

from console import console
from env import Env
from functions import audio_bitrate2representation as ab2r
from functions import download_file, get_video_info
from functions import resolution2representation as r2r
from logger import logger
from telegram import Telegram

install()


@dataclass
class Darya:
    item_identity: str
    resolution: Literal["1920x1080", "1280x720", "854x480", "426x240"] = "1920x1080"
    audio: Literal["128k", "256k", "320k"] = "128k"
    threads: int = 10
    verbose: bool = False
    output: Union[pathlib.Path, None] = None

    def __post_init__(self: Self) -> None:
        self.DOWNLOAD_DIR: str = "downloads"
        self.ITEM_DIRECTORY: str = f"{self.DOWNLOAD_DIR}/{self.item_identity}"
        self.ITEM_OUTPUT_DIR: str = f"{self.ITEM_DIRECTORY}/output/{self.resolution}"
        self.MPDS_OUTPUT_DIR: str = f"{self.ITEM_DIRECTORY}/mpds"
        self.LICENSE_OUTPUT_DIR: str = f"{self.ITEM_DIRECTORY}/license"
        self.VIDEO_OUTPUT_DIR: str = f"{self.ITEM_DIRECTORY}/video/{self.resolution}"
        self.AUDIO_OUTPUT_DIR: str = f"{self.ITEM_DIRECTORY}/audio/{self.audio}"
        self.THUMBNAIL_OUTPUT_DIR: str = f"{self.ITEM_DIRECTORY}/thumbnail"
        self.BG_OUTPUT_DIR: str = f"{self.ITEM_DIRECTORY}/background"

        self.thumbnail: Union[None, pathlib.Path] = None
        self.background: Union[None, pathlib.Path] = None

        os.makedirs(self.DOWNLOAD_DIR, exist_ok=True)

        if self.item:
            os.makedirs(self.ITEM_DIRECTORY, exist_ok=True)
            os.makedirs(self.ITEM_OUTPUT_DIR, exist_ok=True)
            os.makedirs(self.ITEM_OUTPUT_DIR, exist_ok=True)
            os.makedirs(self.MPDS_OUTPUT_DIR, exist_ok=True)
            os.makedirs(self.LICENSE_OUTPUT_DIR, exist_ok=True)
            os.makedirs(self.VIDEO_OUTPUT_DIR, exist_ok=True)
            os.makedirs(self.AUDIO_OUTPUT_DIR, exist_ok=True)
            os.makedirs(self.THUMBNAIL_OUTPUT_DIR, exist_ok=True)
            os.makedirs(self.BG_OUTPUT_DIR, exist_ok=True)

        self.downloaded: Dict[int, pathlib.Path] = {}

    @property
    def item(self: Self) -> Union[Dict, List[Dict[str, str]], None]:
        if hasattr(self, "_item"):
            return self._item

        response: requests.Response = requests.get(
            f"https://ffprod2s3.b-cdn.net/c/278/catalog/4FM71hGHCuwLjg-sGYSA4Q/item/{self.item_identity}.json"
        )

        if response.status_code == 200:
            data = response.json()

            item = self._item = (
                data
                if "children" not in data
                else [child for child in data["children"]]
            )

            return item

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
            pssh = adaptation_set.find("ContentProtection//cenc:pssh", namespaces)

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

                if pssh is not None:
                    representation_dct["pssh"] = pssh.text

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

    def download_mpds(self: Self, mid: str, mpds: List[str]) -> List[pathlib.Path]:
        paths: List[pathlib.Path] = []

        for mpd in mpds:
            path = pathlib.Path(f"downloads/{mid}/mpds/{os.path.basename(mpd)}")

            if not os.path.exists(path):
                download_file(mpd, path)

            paths.append(pathlib.Path(path))

        return paths

    def download_segment(self: Self, idx: int, segment, path):
        output = pathlib.Path(path) / basename(segment)

        if download_file(segment, output):
            return idx, output

        return idx, None

    def combine(self: Self, f) -> None:
        for value in {
            key: self.downloaded.get(key) for key in sorted(self.downloaded)
        }.values():
            if value:
                with open(value, "rb") as ff:
                    f.write(ff.read())

    def download(self: Self) -> Union[pathlib.Path, None]:
        item = self.item

        if type(item) is dict:
            id = item["id"]
            mid = item["mediaID"]
            mpds = self.download_mpds(id, item["media"]["mpds"])
            title = item["title"]["en"]

            self.thumbnail = self.download_thumbnail(item["thumbnail"])
            self.background = self.download_background(item["background"])

            for mpd in mpds:
                if re.search(re.compile(rf"{self.resolution}"), f"{mpd}"):
                    for repr in self.get_representations(
                        f"{mpd}", f"https://ffprod2.b-cdn.net/c/278/m/{mid}.ism/"
                    ):
                        init = repr["init"]
                        mime = repr["mime-type"]
                        rid = repr["representation-id"]
                        segments = repr["segments"]
                        pssh = repr["pssh"]

                        if r2r(self.resolution) == rid or ab2r(self.audio) == rid:
                            key = self.decrypt(pssh, self.license_url())

                            t = (None, None)

                            match mime:
                                case "video/mp4":
                                    t = ("video.mp4", f"{self.VIDEO_OUTPUT_DIR}")

                                case "audio/mp4":
                                    t = ("audio.mp3", f"{self.AUDIO_OUTPUT_DIR}")

                            filename, path = t

                            if filename and path:
                                with open(ff := f"{path}/.{filename}", "wb") as f:
                                    if i := download_file(
                                        init,
                                        pathlib.Path(f"{path}/{basename(init)}"),
                                        self.verbose,
                                    ):
                                        f.write(open(i, "rb").read())

                                    with ThreadPoolExecutor(
                                        max_workers=self.threads
                                    ) as executor:
                                        futures = [
                                            executor.submit(
                                                self.download_segment,
                                                idx,
                                                segment,
                                                path,
                                            )
                                            for idx, segment in enumerate(segments[:])
                                        ]

                                        for future in as_completed(futures):
                                            idx, file_path = future.result()
                                            if file_path:
                                                self.downloaded[idx] = file_path

                                    self.combine(f)

                                self.decrypt_video(key, ff, f"{path}/{filename}")

                    # Define your paths
                    video = pathlib.Path(f"{self.VIDEO_OUTPUT_DIR}/video.mp4")
                    audio = pathlib.Path(f"{self.AUDIO_OUTPUT_DIR}/audio.mp3")
                    output = pathlib.Path(
                        f"{self.ITEM_OUTPUT_DIR}/{secure_filename(title)}.mp4"
                    )

                    if video.exists() and audio.exists():
                        # Construct the FFmpeg command
                        command = [
                            "ffmpeg",
                            "-y",  # Overwrite output file if it exists
                            "-i",
                            audio,  # Second input (audio)
                            "-i",
                            video,  # First input (video)
                            "-c",
                            "copy",  # Copy video stream (no re-encoding)
                            str(output),
                        ]

                        try:
                            # Run the command
                            # check=True will raise an exception if the command fails
                            subprocess.run(
                                command, check=True, capture_output=True, text=True
                            )

                            if output.exists():
                                logger.success(f"Successfully merged into '{output}'.")
                                self.send_video(output)

                                return output
                            else:
                                logger.error(
                                    f"Merge failed: Output file '{output}' was not created."
                                )

                        except subprocess.CalledProcessError as e:
                            logger.error(
                                f"FFmpeg process failed with error:\n{e.stderr}"
                            )

                    break

        elif type(item) is list:
            downloaded: Dict[int, pathlib.Path] = {}

            for idx, item in enumerate(copy.deepcopy(item)):
                id = item["id"]
                logger.info(f"Downloading <b>{id!r} ({idx+1})</b>...")
                darya: Darya = Darya(id, self.resolution, self.audio, self.threads)
                if download := darya.download():
                    downloaded[idx] = download

                break

            for file in downloaded.values():
                print(file)
                self.send_video(file)

            console.print(downloaded)
        else:
            logger.error(f"Failed to find item with ID: {self.item_identity!r}.")

    def send_video(self: Self, file_path: pathlib.Path) -> None:
        if not (
            Env.API_ID and Env.API_HASH and Env.SESSION_STRING and Env.CHANNEL_USERNAME
        ):
            return

        try:
            tg = Telegram(
                api_id=Env.API_ID,
                api_hash=Env.API_HASH,
                session_str=Env.SESSION_STRING,
                channel_username=Env.CHANNEL_USERNAME,
            )

            if file_path.exists() and type(self.item) is dict:
                if info := get_video_info(file_path):
                    asyncio.run(
                        tg.upload_video(
                            file_path,
                            self.item["title"]["en"],
                            info["duration"],
                            info["width"],
                            info["height"],
                            True,
                            FileIO(self.thumbnail, "rb") if self.thumbnail else None,
                        )
                    )

        except Exception as err:
            print(f"ERROR: {err}")

    def decrypt_video(self: Self, key, input_file, output_file):
        command = ["mp4decrypt", "--key", f"{key}", input_file, output_file]

        try:
            subprocess.run(command, check=True)
            logger.success(f"Successfully decrypted {output_file}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Error during decryption: {e}")

    def license_url(
        self: Self,
        item_id: Union[str, None] = None,
        device_id: Union[str, None] = None,
    ):
        return f"https://www.darya.net/api/1.0/license??itemID={item_id}&deviceId={device_id}"

    def download_license(
        self: Self,
        item_id: Union[str, None] = None,
        device_id: Union[str, None] = None,
    ) -> Union[pathlib.Path, None]:
        return download_file(
            url := self.license_url(item_id, device_id),
            pathlib.Path(f"{self.LICENSE_OUTPUT_DIR}/{basename(urlparse(url).path)}"),
        )

    def download_thumbnail(self: Self, tid: str) -> Union[pathlib.Path, None]:
        path = pathlib.Path(f"{self.THUMBNAIL_OUTPUT_DIR}/thumbnail.jpg")

        if not path.exists():
            response: requests.Response = requests.get(
                f"https://ffprod2s3.b-cdn.net/c/278/images/{tid}.jpg"
            )

            with open(path, "wb") as f:
                f.write(response.content)

            if path.exists():
                logger.success(f"Thumbnail Successfully saved in <b>{path}</b>!")

    def download_background(self: Self, bid) -> Union[pathlib.Path, None]:
        path = pathlib.Path(f"{self.BG_OUTPUT_DIR}/{bid}.jpg")

        if not path.exists():
            response: requests.Response = requests.get(
                f"https://ffprod2s3.b-cdn.net/c/278/images/{bid}.jpg"
            )

            with open(path, "wb") as f:
                f.write(response.content)

            if path.exists():
                logger.success(f"Background Successfully saved in <b>{path}</b>!")

    def decrypt(
        self: Self,
        pssh: str,
        licurl: str,
        proxy=None,
        headers=None,
        cookies=None,
        data=None,
        device="default",
    ):
        response: requests.Response = requests.post(
            "https://cdrm-project.com/api/decrypt",
            data=json.dumps(
                {
                    "pssh": pssh,
                    "licurl": licurl,
                    "proxy": proxy,
                    "headers": headers,
                    "cookies": cookies,
                    "data": data,
                    "device": device,
                }
            ),
            headers={"Content-Type": "application/json"},
        )

        dct = response.json()

        return dct["message"]

    @staticmethod
    def banner() -> None:
        fonts = pyfiglet.FigletFont.getFonts()
        font = random.choice(fonts)
        colors = ["red", "cyan", "green", "white", "yellow"]

        console.print(
            pyfiglet.figlet_format("Darya", font=font, width=300),
            style=f"{random.choice(colors)} bold",
        )
