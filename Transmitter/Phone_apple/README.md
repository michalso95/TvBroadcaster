# iPhone transmitter

The iPhone app streams the screen to the TvBroadcaster Android TV receiver using ReplayKit and WebRTC. It supports manual receiver address entry and scanning the QR code shown on the TV. The app accepts the receiver URL (`http://<receiver-ip>:8080`) or a plain host/IP.

The configured video output is **45 FPS**. It is intentionally capped at 45 FPS because streaming at 60 FPS has occasionally caused problems.

## What is included

- SwiftUI receiver-entry screen with QR scanning (iOS 16+).
- URL validation and storage in an App Group shared with the broadcast extension.
- ReplayKit Broadcast Upload Extension that captures and streams screen video to the receiver with WebRTC.
- HTTP signaling matching `Receiver/app/src/main/java/com/example/tvbroadcast/network/ReceiverSignalingClient.kt`:
  - `GET /` checks the receiver is ready.
  - `POST /` sends `{ "type": "offer", "sdp": ... }` and expects an answer.
  - `POST /` sends trickled ICE candidates.

## Build and run

On a Mac with Xcode, open `TvBroadcaster.xcworkspace` and build the `ScreenTransmitter` app and `TvBroadcasterBroadcast` extension. The Xcode project, targets, App Groups, and CocoaPods integration are included in this repository. Select your development team for code signing, then install and run on a physical iPhone; screen broadcasting uses Apple's system broadcast prompt.

## Use

Enter the receiver's IP/host or tap **Scan QR code** and scan the QR shown on the TV. Tap **Start broadcast** and confirm Apple's system broadcast prompt. iOS will show the red recording indicator while the extension streams. Stop from the system broadcast controls.

## Notes and constraints

- Screen capture requires the system Broadcast Upload Extension; this is not ordinary in-app screen recording.
- The receiver and iPhone must be able to reach each other on the network. STUN is configured as on desktop, but restrictive NAT/firewall setups may still prevent WebRTC.
- Signaling uses the receiver's local HTTP endpoint; it is not encrypted in transit.
