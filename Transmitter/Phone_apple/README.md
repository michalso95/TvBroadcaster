# iPhone transmitter (starter)

This folder contains the first iOS transmitter implementation. It mirrors the desktop sender's WebRTC offer/signaling contract and adds manual receiver entry plus QR scanning. The Android TV currently displays a QR code containing `http://<receiver-ip>:8080`; the app accepts that URL or a plain host/IP.

## What is included

- SwiftUI receiver-entry screen with QR scanning (iOS 16+).
- URL validation and storage in an App Group shared with the broadcast extension.
- ReplayKit Broadcast Upload Extension that streams captured screen video to the receiver with WebRTC.
- HTTP signaling matching `Receiver/app/src/main/java/com/example/tvbroadcast/network/ReceiverSignalingClient.kt`:
  - `GET /` checks the receiver is ready.
  - `POST /` sends `{ "type": "offer", "sdp": ... }` and expects an answer.
  - `POST /` sends trickled ICE candidates.

## Xcode setup (on the Mac that builds the app)

1. Create an iOS App project named `TVBroadcaster` in Xcode, with SwiftUI and iOS 16.0 or later, using bundle ID `com.example.TvBroadcaster` (or update the extension ID below to match your chosen ID).
2. Add the Swift files from `TVBroadcaster/` to the app target. Add both `BroadcastUploadExtension/SampleHandler.swift` and `BroadcastUploadExtension/WebRTCStreamer.swift` to a new **Broadcast Upload Extension** target named `TVBroadcasterBroadcast`. Do not add either extension file to the app target.
3. Add the App Groups capability to both targets and create the same group, initially `group.com.example.TvBroadcaster`. Update `appGroupIdentifier` in `ContentView.swift` and `appGroupIdentifier` in `SampleHandler.swift` if your team uses another identifier.
4. Set the extension bundle identifier to `com.example.TvBroadcaster.BroadcastUpload` (or update `broadcastExtensionIdentifier` in `ContentView.swift` to match).
5. Use the supplied `Podfile` from this folder. From this directory run `pod install`, then open the generated `.xcworkspace` in Xcode. Ensure the `GoogleWebRTC` pod is linked to both app and extension targets.
6. Add these app Info.plist values: `NSCameraUsageDescription` = “Scan the TV receiver's connection QR code.”; `NSLocalNetworkUsageDescription` = “Connect to a TV receiver on your local network.”; `NSAppTransportSecurity` → `NSAllowsLocalNetworking` = `YES` (the receiver currently serves HTTP).
7. Add `NSLocalNetworkUsageDescription` and the `NSAppTransportSecurity` → `NSAllowsLocalNetworking` setting to the extension Info.plist too, so the broadcast extension can signal to the TV over HTTP.
8. In the extension Info.plist, verify `NSExtensionPointIdentifier` is `com.apple.broadcast-services-upload` and `NSExtensionPrincipalClass` is `$(PRODUCT_MODULE_NAME).SampleHandler`.
9. Build and run on a physical iPhone. The app can be built on macOS only; this Windows workspace is for preparing source code.

## Use

Enter the receiver's IP/host or tap **Scan QR code** and scan the QR shown on the TV. Tap **Start broadcast** and confirm Apple's system broadcast prompt. iOS will show the red recording indicator while the extension streams. Stop from the system broadcast controls.

## Current constraints

- Screen capture requires the system Broadcast Upload Extension; this is not ordinary in-app screen recording.
- The receiver and iPhone must be able to reach each other on the network. STUN is configured as on desktop, but restrictive NAT/firewall setups may still prevent WebRTC.
- The Android receiver currently has a simplistic HTTP server. Its request parser, response framing, and concurrent-client handling may need hardening if iOS URLSession signaling exposes interoperability issues.
- This is a source scaffold rather than a checked-in `.xcodeproj`; target creation, signing, App Groups, CocoaPods installation, and device testing are done on macOS.
