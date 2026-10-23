# TvBroadcaster

TvBroadcaster streams a screen from a Windows laptop or iPhone to an Android TV over the local network. The TV receiver, laptop transmitter, and iPhone transmitter are working. Video is sent peer-to-peer using WebRTC; signaling uses the receiver's local HTTP endpoint.

## Current apps

- **Android TV receiver** — displays the incoming stream and a QR code with the receiver address. The app is in `Receiver/`.
- **Windows laptop transmitter** — captures the primary display, including the mouse cursor, and sends video using WebRTC/H.264. The configured capture rate is **60 FPS**. It has a GUI and a command-line entry point in `Transmitter/Desktop_python/`.
- **iPhone transmitter** — shares the screen through an iOS Broadcast Upload Extension and WebRTC. Its configured output rate is **45 FPS**. It is intentionally set below 60 FPS because 60 FPS has occasionally caused problems. The Xcode project and workspace are in `Transmitter/Phone_apple/`.

An **Android phone transmitter** is planned as the next development step; it has not been implemented yet.

## Connecting to the TV

The transmitters connect to a compatible receiver at `http://<receiver-address>:8080/`. The TV app displays a QR code that the iPhone app can scan. On the laptop, discover a receiver on the local network or enter its IP address/host name manually. Discovery checks the active IPv4 `/24` subnet, so manual entry may be needed on other network layouts or when client isolation is enabled.

Signaling uses `GET /` to check that the receiver is ready, then `POST /` requests to exchange the WebRTC offer/answer and ICE candidates. The apps use public STUN servers to help establish a peer-to-peer connection, but restrictive routers, firewalls, or network isolation can still prevent streaming. Signaling currently uses HTTP.

## Repository layout

```text
Receiver/                         # Android TV receiver app
Transmitter/
├── Desktop_python/               # Windows GUI/CLI transmitter
│   ├── sender.py                 # GUI and CLI entry points
│   ├── discovery.py              # Local subnet receiver discovery
│   ├── webrtc_sender.py          # WebRTC signaling and lifecycle
│   ├── screen_track.py           # Desktop capture and video frames
│   ├── windows_cursor.py         # Windows cursor capture/compositing
│   └── settings.py               # Video and STUN configuration
└── Phone_apple/
	├── ScreenTransmitter/        # iOS app
	├── TvBroadcasterBroadcast/   # ReplayKit capture and WebRTC signaling
	└── TvBroadcaster.xcworkspace # Xcode workspace
```

## Requirements

- Windows for the laptop transmitter; Python and its dependencies are required to run from source. macOS with Xcode is required to build and sign the iPhone app.
- An Android TV or TV-connected device running the receiver app.
- The receiver and transmitting device must be able to reach each other over the network. Internet access may be needed for the configured public STUN servers.

## Run the laptop transmitter from source

Open PowerShell in the repository and set up the desktop transmitter environment:

```powershell
cd Transmitter\Desktop_python
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install aiortc aiohttp mss numpy
```

`aiortc` installs its media dependencies, including PyAV. Tkinter is included with most standard Windows Python installations. If the Python launcher does not have Python 3.13 installed, use an installed Python version compatible with the dependencies and substitute it for `-3.13`.

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

Build on Windows, since the capture code uses Win32 APIs. The GUI build is the recommended one to try first.

## Current limitations and roadmap

- The laptop transmitter captures only the primary display; audio, display selection, and quality controls are not available in the current GUI.
- Receiver discovery is limited to scanning the active IPv4 `/24` subnet.
- WebRTC connectivity depends on the local network, router, and firewall configuration.
- The signaling endpoint uses HTTP, and the receiver may need further hardening before production use.
- There is no installer, automatic update mechanism, or pinned dependency lockfile yet.
