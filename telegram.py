import pathlib
from dataclasses import dataclass, field
from typing import Optional

from FastTelethonhelper import fast_upload
from telethon import TelegramClient
from telethon.hints import FileLike
from telethon.sessions import StringSession
from telethon.tl.types import DocumentAttributeVideo

from env import Env
from logger import logger


@dataclass
class Telegram:
    api_id: int
    api_hash: str
    session_str: str
    channel_username: str
    _client: TelegramClient = field(init=False)

    def __post_init__(self) -> None:
        self._client = TelegramClient(
            StringSession(self.session_str),
            self.api_id,
            self.api_hash,
        )

    async def upload_video(
        self,
        file_path: pathlib.Path,
        caption: str,
        duration: int,
        width: int,
        height: int,
        supports_streaming: bool = True,
        thumb: Optional[FileLike] = None,
    ) -> None:

        async with self._client:
            await self._client.send_file(
                self.channel_username,
                await fast_upload(
                    self._client, f"{file_path}", progress_bar_function=self._progress
                ),
                caption=caption,
                force_document=False,
                supports_streaming=supports_streaming,
                attributes=[
                    DocumentAttributeVideo(
                        duration=duration,
                        w=width,
                        h=height,
                        supports_streaming=supports_streaming,
                    )
                ],
                thumb=thumb,
                progress_callback=self._progress,
            )
            logger.success("Upload complete!")

    @staticmethod
    def _progress(current, total):
        print(f"Uploaded: {current / total * 100:.2f}%", end="\r")
