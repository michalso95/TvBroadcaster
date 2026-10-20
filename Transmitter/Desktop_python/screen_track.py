"""aiortc video track that captures the primary Windows display."""

import asyncio
import time
from fractions import Fraction

import mss
import numpy as np
from aiortc import VideoStreamTrack
from av import VideoFrame

from settings import VIDEO_CLOCK_RATE, VIDEO_FPS
from windows_cursor import WindowsCursor


class ScreenTrack(VideoStreamTrack):
    """Capture the desktop and emit BGRA frames at a fixed frame rate."""

    def __init__(self) -> None:
        super().__init__()
        self.frame_interval = 1.0 / VIDEO_FPS
        self.frame_time = 0.0
        self.start_time = time.perf_counter()
        self.sct = mss.mss()
        self.monitor = self.sct.monitors[1]
        self.cursor = WindowsCursor()
        print(f"Capturing screen: {self.monitor['width']}x{self.monitor['height']}")

    async def recv(self) -> VideoFrame:
        now = time.perf_counter()
        if self.frame_time == 0:
            self.frame_time = now
        else:
            self.frame_time += self.frame_interval

        delay = self.frame_time - now
        if delay > 0:
            await asyncio.sleep(delay)
        else:
            self.frame_time = now

        shot = self.sct.grab(self.monitor)
        image = self.cursor.draw(np.asarray(shot), self.monitor)
        frame = VideoFrame.from_ndarray(image, format="bgra")
        frame.pts = int((self.frame_time - self.start_time) * VIDEO_CLOCK_RATE)
        frame.time_base = Fraction(1, VIDEO_CLOCK_RATE)
        return frame

    def stop(self) -> None:
        super().stop()
        if self.cursor is not None:
            self.cursor.close()
            self.cursor = None
        if self.sct is not None:
            self.sct.close()
            self.sct = None
