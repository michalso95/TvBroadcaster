# TvBroadcaster

TvBroadcaster is a personal, in-progress project for sending a screen or other media source to a television over the local network. The goal is to make it easy to start a stream from whichever device is convenient and play it on a TV without relying on a dedicated casting dongle or a cloud streaming service.

## Project vision

The intended system has three kinds of apps:

- **Desktop transmitter** — share a computer screen. The first Windows/Python implementation is in this repository.
- **TV receiver** — an Android app that runs on an Android TV or TV-connected device and displays incoming streams.
- **Phone transmitter** — an iPhone source scaffold is now started in `Transmitter/Phone_apple/`; it supports receiver IP entry, scanning the TV's QR code, and a ReplayKit/WebRTC broadcast extension. Android phone support remains planned.

The longer-term idea is for the receiver to be the playback endpoint and for desktop and mobile transmitters to connect to it using a shared, documented streaming/signaling protocol. The repository contains an Android TV receiver and desktop transmitter; the iPhone transmitter is an initial, unbuilt source scaffold.

## What is implemented

The current desktop sender provides:

- A small Windows GUI to discover a receiver, enter its address, start/stop sharing, and view connection logs.
- A command-line entry point for running the sender from Python with a receiver address.
- Primary-monitor capture at a configured 60 FPS, including the Windows mouse cursor.
- WebRTC video streaming using `aiortc` and H.264.
- Local-network receiver discovery by checking the active IPv4 `/24` subnet for HTTP endpoints on port `8080`.

The iPhone sender is an initial Swift source scaffold. It has not yet been built or tested in Xcode; see `Transmitter/Phone_apple/README.md` for macOS target setup and current limitations.

Discovery is a convenience, not a prerequisite: the receiver's IP address or host name can be entered manually. Discovery currently checks only the active IPv4 `/24` subnet, so it may not find devices on a different subnet or a network with client isolation enabled.

### Expected receiver endpoint

The sender currently expects a compatible receiver at `http://<receiver-address>:8080/`. The endpoint is queried with `GET /`; the sender then `POST`s a WebRTC offer as JSON (`type` and `sdp`) and expects a JSON answer with `type: "answer"` and an `sdp` value. ICE candidates are sent as additional JSON `POST` requests. A receiver implementing a different signaling contract will not work without changes to the sender or receiver.

WebRTC media is negotiated peer-to-peer where possible. The sender is configured with public STUN servers to help peers find network routes; this is not a guarantee that connections will work across every router, firewall, or network. The signaling requests currently use HTTP.

## Repository layout

```text
Transmitter/
├── Desktop_python/
│   ├── sender.py                 # GUI and CLI entry points
│   ├── discovery.py              # Local subnet receiver discovery
│   ├── webrtc_sender.py          # WebRTC offer, signaling, and lifecycle
│   ├── screen_track.py           # Desktop capture and video frames
│   ├── windows_cursor.py         # Windows cursor capture/compositing
│   ├── settings.py               # Video and STUN configuration
│   ├── log_writer.py             # GUI log forwarding
│   ├── TVDesktopSender.spec      # PyInstaller single-file build
│   └── TVDesktopSenderGUI.spec   # PyInstaller GUI folder build
└── Phone_apple/
	├── TVBroadcaster/              # SwiftUI app: manual entry and QR scanning
	└── BroadcastUploadExtension/   # ReplayKit capture and WebRTC signaling
```

## Requirements

- Windows for the desktop transmitter; macOS with Xcode is required to build and sign the iPhone app.
- Python. The existing build artifacts were produced with Python 3.13; the project does not yet pin or certify a supported Python version.
- A compatible TV receiver running on the same reachable network, listening on port `8080`.
- Network access between the computer and receiver. Internet access may be needed for the configured public STUN servers.

## Run from source

Open PowerShell in the repository and set up the desktop transmitter environment:

```powershell
cd Transmitter\Desktop_python
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install aiortc aiohttp mss numpy
```

`aiortc` installs its media dependencies, including PyAV. Tkinter is included with most standard Windows Python installations. If the Python launcher does not have 3.13 installed, use an installed Python version compatible with the dependencies and substitute it for `-3.13`.

Launch the GUI:

```powershell
python sender.py
```

Or start a stream directly by providing the receiver IP address or host name:

```powershell
python sender.py 192.168.1.50
```

Stop the stream from the GUI, or press `Ctrl+C` when running from a console.

## Build Windows executables

From `Transmitter\Desktop_python`, install PyInstaller in the same virtual environment and build either or both packaged variants:

```powershell
python -m pip install pyinstaller
pyinstaller --clean --noconfirm TVDesktopSenderGUI.spec
pyinstaller --clean --noconfirm TVDesktopSender.spec
```

Build output is written to `dist`:

- `dist\TVDesktopSenderGUI\TVDesktopSenderGUI.exe` — GUI application distributed with its supporting files in the folder.
- `dist\TVDesktopSender.exe` — single-file, windowed application.

The GUI build is the recommended one to try first. Build on Windows, since the capture code uses Win32 APIs. If a packaged build fails to start or is missing a runtime dependency, run the source version first to separate packaging issues from connection or receiver issues.

## Current limitations and roadmap

- The iPhone scaffold has not yet been compiled, signed, or tested on a physical device.
- The TV receiver's HTTP signaling server is a prototype and may need hardening for production.
- Only the primary Windows display is captured. There are no display-selection, audio, or quality controls in the current GUI.
- Receiver discovery is an IPv4 subnet scan, not a general device-discovery protocol.
- There is no installer, automatic update mechanism, or pinned dependency lockfile yet.

Planned work is to validate the iPhone sender on macOS and a physical iPhone, then improve protocol reliability and add an Android phone transmitter.
