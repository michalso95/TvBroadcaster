"""WebRTC signaling and connection lifecycle for the TV receiver."""

import asyncio
import json

import aiohttp
from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription

from screen_track import ScreenTrack
from settings import STUN_SERVERS, configure_video_encoder


def _configuration() -> RTCConfiguration:
    return RTCConfiguration(iceServers=[RTCIceServer(urls=server) for server in STUN_SERVERS])


async def stream_desktop(tv_ip: str) -> None:
    """Offer the desktop track to the TV and keep the connection alive."""
    configure_video_encoder()
    url = f"http://{tv_ip}:8080/"
    pc = RTCPeerConnection(configuration=_configuration())
    track = ScreenTrack()
    pc.addTrack(track)

    @pc.on("icecandidate")
    async def on_ice_candidate(event) -> None:
        if not event.candidate:
            return
        payload = {
            "type": "candidate",
            "candidate": event.candidate.candidate,
            "sdpMid": event.candidate.sdpMid,
            "sdpMLineIndex": event.candidate.sdpMLineIndex,
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    await response.text()
            print("ICE candidate sent to the TV")
        except Exception as error:
            print("Error sending ICE candidate:", error)

    @pc.on("connectionstatechange")
    async def on_connection_state_change() -> None:
        print("WebRTC:", pc.connectionState)

    @pc.on("iceconnectionstatechange")
    async def on_ice_state_change() -> None:
        print("ICE:", pc.iceConnectionState)

    try:
        print("Video source: WINDOWS DESKTOP")
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        print("Sending offer to the TV...")

        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, timeout=5) as response:
                print("TV status:", await response.text())

            payload = {"type": pc.localDescription.type, "sdp": pc.localDescription.sdp}
            async with session.post(url, json=payload) as response:
                response_text = await response.text()
                print("HTTP:", response.status)
                print("TV response:", response_text)
                if response.status != 200:
                    raise RuntimeError(f"TV returned HTTP {response.status}: {response_text}")

        answer = json.loads(response_text)
        if answer.get("type") != "answer" or not answer.get("sdp"):
            raise RuntimeError(f"TV did not return a valid SDP answer: {answer}")
        await pc.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type=answer["type"]))

        print("Waiting for video on the TV.")
        print("Press Ctrl+C to stop streaming.")
        while True:
            await asyncio.sleep(1)
    finally:
        print("Closing WebRTC connection...")
        track.stop()
        try:
            # aiortc can occasionally wait indefinitely for a transport task
            # after the peer has already announced its closed state.
            await asyncio.wait_for(pc.close(), timeout=5)
        except asyncio.TimeoutError:
            print("WebRTC cleanup timed out; continuing shutdown.")
        print("WebRTC cleanup finished.")
