"""Application-wide settings for the desktop broadcaster."""

import aiortc.codecs.h264 as h264

VIDEO_FPS = 60
VIDEO_CLOCK_RATE = 90_000
CURSOR_BUFFER_SIZE = 128
CURSOR_PAD = 16
STUN_SERVERS = (
    "stun:stun.l.google.com:19302",
    "stun:stun1.l.google.com:19302",
)


def configure_video_encoder() -> None:
    """Apply the H.264 quality limits used by aiortc."""
    h264.DEFAULT_BITRATE = 10_000_000
    h264.MAX_BITRATE = 12_000_000
    h264.MIN_BITRATE = 1_000_000
