import AVFoundation
import CoreMedia
import Foundation
import ReplayKit
import WebRTC

private let appGroupIdentifier = "group.com.example.TvBroadcaster"
private let receiverURLKey = "receiverURL"

final class SampleHandler: RPBroadcastSampleHandler {
    private var streamer: WebRTCStreamer?
    private var didFinish = false

    override func broadcastStarted(withSetupInfo setupInfo: [String: NSObject]?) {
        guard let value = UserDefaults(suiteName: appGroupIdentifier)?.string(forKey: receiverURLKey),
              let url = URL(string: value) else {
            finishBroadcastWithError(StreamerError.receiverNotConfigured)
            return
        }
        streamer = WebRTCStreamer(receiverURL: url) { [weak self] error in
            guard let self, !self.didFinish else { return }
            self.didFinish = true
            self.finishBroadcastWithError(error)
        }
        streamer?.start()
    }

    override func broadcastPaused() {
        streamer?.setPaused(true)
    }

    override func broadcastResumed() {
        streamer?.setPaused(false)
    }

    override func broadcastFinished() {
        streamer?.stop()
        streamer = nil
    }

    override func processSampleBuffer(_ sampleBuffer: CMSampleBuffer, with sampleBufferType: RPSampleBufferType) {
        guard sampleBufferType == .video else { return }
        streamer?.process(sampleBuffer)
    }
}
