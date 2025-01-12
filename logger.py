import sys

from loguru import logger

format = (
    "<b>[<cyan>{time:YYYY-MM-DD HH:MM:SS A}</cyan>]</b> "
    "<b><level>[<b>{level: ^8}</b>]</level></b> "
    "[<green><b>{module}<w>:</w>{name}<w>:</w>{line:06}</b></green>] {message}"
)

logger.remove()
logger.add(".log", format=format, mode="w")
logger.add(sys.stdout, format=format)

logger = logger.opt(colors=True)
