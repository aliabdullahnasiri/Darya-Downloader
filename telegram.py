import asyncio
import os
import pathlib
import secrets
from dataclasses import dataclass, field
from typing import Optional, Self

from FastTelethonhelper import fast_upload
from telethon import TelegramClient, functions, utils
from telethon.hints import FileLike
from telethon.sessions import StringSession
from telethon.tl.types import DocumentAttributeVideo, InputFile, InputFileBig

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
            file_size = os.path.getsize(file_path)
            # Determine chunk size (must be a multiple of 1KB)
            chunk_size = 512 * 1024  # 512KB
            total_chunks = (file_size + chunk_size - 1) // chunk_size

            # Use a unique ID for the file
            file_id = secrets.randbits(63)

            with open(file_path, "rb") as f:
                uploaded_bytes = 0

                async def upload_chunk(i):
                    nonlocal uploaded_bytes
                    f.seek(i * chunk_size)
                    chunk = f.read(chunk_size)

                    # This is the raw Telethon internal method for speed
                    await self._client(
                        functions.upload.SaveBigFilePartRequest(
                            file_id=file_id,
                            file_part=i,
                            file_total_parts=total_chunks,
                            bytes=chunk,
                        )
                    )

                    uploaded_bytes += len(chunk)
                    self._progress(uploaded_bytes, file_size)

                # Semaphore limits parallel tasks to prevent FloodWait
                semaphore = asyncio.Semaphore(32)

                async def sem_task(i):
                    async with semaphore:
                        return await upload_chunk(i)

                tasks = [sem_task(i) for i in range(total_chunks)]
                await asyncio.gather(*tasks)

            file = InputFileBig(
                id=file_id, parts=total_chunks, name=os.path.basename(file_path)
            )

            await self._client.send_file(
                self.channel_username,
                file,
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
