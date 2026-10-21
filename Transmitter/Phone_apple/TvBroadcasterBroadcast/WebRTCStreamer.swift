import AVFoundation
import CoreVideo
import Foundation
import ImageIO
import ReplayKit
import WebRTC

enum StreamerError: LocalizedError {
    case receiverNotConfigured
    case invalidResponse
    case receiverRejected(Int, String)
    case webRTC(String)

    var errorDescription: String? {
        switch self {
        case .receiverNotConfigured:
            return "Choose a TV receiver in the app before starting a broadcast."
        case .invalidResponse:
            return "The TV returned an invalid WebRTC answer."
        case let .receiverRejected(status, message):
            return "The TV returned HTTP \(status): \(message)"
        case let .webRTC(message):
            return "WebRTC setup failed: \(message)"
        }
    }
}

final class WebRTCStreamer: NSObject, RTCPeerConnectionDelegate {
    private static let diagnosticsKey = "broadcastDiagnostics"
    private static let diagnosticsQueue = DispatchQueue(label: "private.ScreenTransmitter.TvBroadcasterBroadcast.diagnostics")
    private let receiverURL: URL
    private let onFatalError: (Error) -> Void
    private let queue = DispatchQueue(label: "private.ScreenTransmitter.TvBroadcasterBroadcast.streamer")
    private let factory: RTCPeerConnectionFactory
    private let videoSource: RTCVideoSource
    private let videoCapturer: RTCVideoCapturer
    private let peerConnection: RTCPeerConnection
    private var isStopped = false
    private var isPaused = false
    private var isOfferSent = false
    private var pendingCandidates: [RTCIceCandidate] = []
    private var lastTimestampNs: Int64 = 0
    private var didLogFirstFrame = false
    private var lastDiagnosticsWriteTime: TimeInterval = 0
    private var framesSinceDiagnosticsWrite = 0

    static func recordDiagnostic(_ message: String) {
        diagnosticsQueue.async {
            guard let defaults = UserDefaults(suiteName: "group.private.ScreenTransmitter") else { return }
            var entries = defaults.stringArray(forKey: diagnosticsKey) ?? []
            entries.append("\(ISO8601DateFormatter().string(from: Date()))  \(message)")
            defaults.set(Array(entries.suffix(30)), forKey: diagnosticsKey)
        }
    }

    init(receiverURL: URL, onFatalError: @escaping (Error) -> Void) {
        self.receiverURL = receiverURL
        self.onFatalError = onFatalError

        RTCInitializeSSL()
        let encoderFactory = RTCDefaultVideoEncoderFactory()
        let decoderFactory = RTCDefaultVideoDecoderFactory()
        factory = RTCPeerConnectionFactory(encoderFactory: encoderFactory, decoderFactory: decoderFactory)
        videoSource = factory.videoSource()
        videoCapturer = RTCVideoCapturer(delegate: videoSource)

        let configuration = RTCConfiguration()
        configuration.iceServers = [
            RTCIceServer(urlStrings: ["stun:stun.l.google.com:19302"]),
            RTCIceServer(urlStrings: ["stun:stun1.l.google.com:19302"])
        ]
        configuration.sdpSemantics = .unifiedPlan

        let constraints = RTCMediaConstraints(mandatoryConstraints: nil, optionalConstraints: nil)
        let connection = factory.peerConnection(with: configuration, constraints: constraints, delegate: nil)

        peerConnection = connection
        super.init()
        peerConnection.delegate = self

        let track = factory.videoTrack(with: videoSource, trackId: "iphone-screen")
        guard peerConnection.add(track, streamIds: ["tvbroadcaster"]) != nil else {
            fatalError("Failed to add screen video track")
        }
    }

    func start() {
        queue.async { [weak self] in
            guard let self, !self.isStopped else { return }
            self.checkReceiverAndCreateOffer()
        }
    }

    func setPaused(_ paused: Bool) {
        queue.async { [weak self] in self?.isPaused = paused }
    }

    func process(_ sampleBuffer: CMSampleBuffer) {
        guard !isPaused, !isStopped,
              let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }

        let orientation = videoRotation(for: sampleBuffer)
        framesSinceDiagnosticsWrite += 1
        if !didLogFirstFrame {
            didLogFirstFrame = true
            Self.recordDiagnostic(
                "First ReplayKit frame: \(CVPixelBufferGetWidth(pixelBuffer))x\(CVPixelBufferGetHeight(pixelBuffer)), rotation=\(orientation.rawValue)"
            )
        }

        let now = ProcessInfo.processInfo.systemUptime
        if now - lastDiagnosticsWriteTime >= 2 {
            Self.recordDiagnostic(
                "ReplayKit frames flowing: \(framesSinceDiagnosticsWrite) in interval, size=\(CVPixelBufferGetWidth(pixelBuffer))x\(CVPixelBufferGetHeight(pixelBuffer)), rotation=\(orientation.rawValue)"
            )
            lastDiagnosticsWriteTime = now
            framesSinceDiagnosticsWrite = 0
        }

        let time = CMSampleBufferGetPresentationTimeStamp(sampleBuffer)
        let convertedTime = CMTimeConvertScale(time, timescale: 1_000_000_000, method: .default)
        var timestampNs = time.isValid && time.isNumeric && convertedTime.isValid && convertedTime.isNumeric
            ? convertedTime.value
            : Int64(ProcessInfo.processInfo.systemUptime * 1_000_000_000)
        if timestampNs <= lastTimestampNs {
            timestampNs = lastTimestampNs + 1
        }
        lastTimestampNs = timestampNs
        let rtcBuffer = RTCCVPixelBuffer(pixelBuffer: pixelBuffer)
        let frame = RTCVideoFrame(buffer: rtcBuffer, rotation: orientation, timeStampNs: timestampNs)
        videoSource.capturer(videoCapturer, didCapture: frame)
    }

    private func videoRotation(for sampleBuffer: CMSampleBuffer) -> RTCVideoRotation {
        guard let value = CMGetAttachment(
            sampleBuffer,
            key: RPVideoSampleOrientationKey as CFString,
            attachmentModeOut: nil
        ) as? NSNumber,
        let orientation = CGImagePropertyOrientation(rawValue: value.uint32Value) else {
            return ._0
        }

        switch orientation {
        case .right, .rightMirrored:
            return ._270
        case .down, .downMirrored:
            return ._180
        case .left, .leftMirrored:
            return ._90
        default:
            return ._0
        }
    }

    func stop() {
        queue.async { [weak self] in
            guard let self, !self.isStopped else { return }
            self.isStopped = true
            self.peerConnection.close()
            RTCCleanupSSL()
        }
    }

    private func checkReceiverAndCreateOffer() {
        var request = URLRequest(url: receiverURL)
        request.httpMethod = "GET"
        request.timeoutInterval = 8
        URLSession.shared.dataTask(with: request) { [weak self] _, response, error in
            guard let self else { return }
            if let error {
                self.fail(error)
                return
            }
            guard let response = response as? HTTPURLResponse, (200..<400).contains(response.statusCode) else {
                self.fail(StreamerError.invalidResponse)
                return
            }
            let constraints = RTCMediaConstraints(mandatoryConstraints: nil, optionalConstraints: nil)
            self.peerConnection.offer(for: constraints) { [weak self] offer, error in
                guard let self else { return }
                if let error {
                    self.fail(error)
                    return
                }
                guard let offer else {
                    self.fail(StreamerError.webRTC("No offer was created."))
                    return
                }
                self.peerConnection.setLocalDescription(offer) { [weak self] error in
                    guard let self else { return }
                    if let error {
                        self.fail(error)
                        return
                    }
                    guard let local = self.peerConnection.localDescription else {
                        self.fail(StreamerError.webRTC("Local offer is missing."))
                        return
                    }
                    self.postOffer(type: "offer", sdp: local.sdp)
                }
            }
        }.resume()
    }

    private func postOffer(type: String, sdp: String) {
        postJSON(["type": type, "sdp": sdp]) { [weak self] data, response, error in
            guard let self else { return }
            if let error {
                self.fail(error)
                return
            }
            guard let response = response as? HTTPURLResponse,
                  (200..<300).contains(response.statusCode),
                  let data,
                  let answer = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  answer["type"] as? String == "answer",
                  let sdp = answer["sdp"] as? String else {
                self.fail(StreamerError.invalidResponse)
                return
            }

            let remoteDescription = RTCSessionDescription(type: .answer, sdp: sdp)
            self.peerConnection.setRemoteDescription(remoteDescription) { [weak self] error in
                guard let self else { return }
                if let error {
                    self.fail(error)
                    return
                }
                self.queue.async {
                    self.isOfferSent = true
                    let candidates = self.pendingCandidates
                    self.pendingCandidates.removeAll()
                    candidates.forEach(self.postCandidate)
                }
            }
        }
    }

    private func postCandidate(_ candidate: RTCIceCandidate) {
        let payload: [String: Any] = [
            "type": "candidate",
            "candidate": candidate.sdp,
            "sdpMid": candidate.sdpMid as Any? ?? NSNull(),
            "sdpMLineIndex": candidate.sdpMLineIndex
        ]
        postJSON(payload) { _, _, error in
            if let error { NSLog("TV Broadcaster: failed to send ICE candidate: %@", error.localizedDescription) }
        }
    }

    private func postJSON(_ object: [String: Any], completion: @escaping (Data?, URLResponse?, Error?) -> Void) {
        var request = URLRequest(url: receiverURL)
        request.httpMethod = "POST"
        request.timeoutInterval = 30
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        do {
            request.httpBody = try JSONSerialization.data(withJSONObject: object)
        } catch {
            completion(nil, nil, error)
            return
        }
        URLSession.shared.dataTask(with: request, completionHandler: completion).resume()
    }

    private func fail(_ error: Error) {
        queue.async { [weak self] in
            guard let self, !self.isStopped else { return }
            Self.recordDiagnostic("WebRTC fatal error: \(error.localizedDescription)")
            self.isStopped = true
            self.peerConnection.close()
            RTCCleanupSSL()
            self.onFatalError(error)
        }
    }

    func peerConnection(_ peerConnection: RTCPeerConnection, didGenerate candidate: RTCIceCandidate) {
        queue.async { [weak self] in
            guard let self, !self.isStopped else { return }
            if self.isOfferSent {
                self.postCandidate(candidate)
            } else {
                self.pendingCandidates.append(candidate)
            }
        }
    }

    func peerConnection(_ peerConnection: RTCPeerConnection, didChange stateChanged: RTCSignalingState) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didAdd stream: RTCMediaStream) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didRemove stream: RTCMediaStream) {}
    func peerConnectionShouldNegotiate(_ peerConnection: RTCPeerConnection) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didChange newState: RTCIceConnectionState) {
        Self.recordDiagnostic("WebRTC ICE state: \(newState)")
    }
    func peerConnection(_ peerConnection: RTCPeerConnection, didChange newState: RTCIceGatheringState) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didRemove candidates: [RTCIceCandidate]) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didOpen dataChannel: RTCDataChannel) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didStartReceivingOn transceiver: RTCRtpTransceiver) {}
}
