package com.example.tvbroadcast.webrtc

import android.content.Context
import android.util.Log
import com.example.tvbroadcast.network.ReceiverSignalingClient
import com.example.tvbroadcast.network.SignalingMessage
import kotlinx.coroutines.CancellableContinuation
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeout
import org.webrtc.DataChannel
import org.webrtc.DefaultVideoDecoderFactory
import org.webrtc.DefaultVideoEncoderFactory
import org.webrtc.EglBase
import org.webrtc.IceCandidate
import org.webrtc.MediaConstraints
import org.webrtc.MediaStream
import org.webrtc.PeerConnection
import org.webrtc.PeerConnectionFactory
import org.webrtc.RtpReceiver
import org.webrtc.RtpTransceiver
import org.webrtc.SdpObserver
import org.webrtc.SessionDescription
import org.webrtc.SurfaceViewRenderer
import org.webrtc.VideoTrack
import kotlin.coroutines.resume

class WebRtcReceiverManager(
    private val context: Context,
    private val signalingClient: ReceiverSignalingClient
) : ReceiverSignalingClient.SignalingListener {
    private val tag = "WebRtcReceiverManager"
    private var factory: PeerConnectionFactory? = null
    private var peerConnection: PeerConnection? = null
    private val scope = CoroutineScope(Dispatchers.Main)

    private val _remoteVideoTrack = MutableStateFlow<VideoTrack?>(null)
    val remoteVideoTrack: StateFlow<VideoTrack?> = _remoteVideoTrack

    val eglBase: EglBase = EglBase.create()

    private val iceServers = listOf(
        PeerConnection.IceServer.builder("stun:stun.l.google.com:19302").createIceServer(),
        PeerConnection.IceServer.builder("stun:stun1.l.google.com:19302").createIceServer()
    )

    private var iceGatheringDeferred: CompletableDeferred<Unit>? = null

    init {
        initPeerConnectionFactory()
    }

    private fun initPeerConnectionFactory() {
        PeerConnectionFactory.initialize(
            PeerConnectionFactory.InitializationOptions.builder(context)
                .setEnableInternalTracer(true)
                .createInitializationOptions()
        )
        val options = PeerConnectionFactory.Options()
        factory = PeerConnectionFactory.builder()
            .setOptions(options)
            .setVideoEncoderFactory(DefaultVideoEncoderFactory(eglBase.eglBaseContext, true, true))
            .setVideoDecoderFactory(DefaultVideoDecoderFactory(eglBase.eglBaseContext))
            .createPeerConnectionFactory()
    }

    fun startListening() {
        signalingClient.signalingListener = this
        signalingClient.startServer()
    }

    override suspend fun onOfferReceived(sdp: String): String? = suspendCancellableCoroutine { continuation ->
        scope.launch(Dispatchers.Main) {
            try {
                Log.i(tag, "Received offer SDP: $sdp")
                val sanitizedSdp = sdp.replace("a=fmtp:102 apt=102", "a=fmtp:102 apt=101")
                createPeerConnection()
                val sessionDescription = SessionDescription(SessionDescription.Type.OFFER, sanitizedSdp)
                
                peerConnection?.setRemoteDescription(object : SdpObserver {
                    override fun onCreateSuccess(desc: SessionDescription?) {}
                    override fun onSetSuccess() {
                        Log.i(tag, "Remote description set successfully")
                        createAnswerAndGetSdp(continuation)
                    }
                    override fun onCreateFailure(err: String?) {
                        Log.e(tag, "Failed to set remote description: $err")
                        continuation.resume(null)
                    }
                    override fun onSetFailure(err: String?) {
                        Log.e(tag, "Failed to set remote description: $err")
                        continuation.resume(null)
                    }
                }, sessionDescription)
            } catch (e: Exception) {
                Log.e(tag, "Error handling offer", e)
                continuation.resume(null)
            }
        }
    }

    override fun onCandidateReceived(msg: SignalingMessage) {
        if (!msg.candidate.isNullOrEmpty() && !msg.sdpMid.isNullOrEmpty() && msg.sdpMLineIndex != null) {
            try {
                val candidate = IceCandidate(msg.sdpMid, msg.sdpMLineIndex, msg.candidate)
                peerConnection?.addIceCandidate(candidate)
                Log.i(tag, "Added ICE candidate from client")
            } catch (e: Exception) {
                Log.e(tag, "Failed to add ICE candidate", e)
            }
        }
    }

    private fun createAnswerAndGetSdp(continuation: CancellableContinuation<String?>) {
        val constraints = MediaConstraints()
        peerConnection?.createAnswer(object : SdpObserver {
            override fun onCreateSuccess(answer: SessionDescription?) {
                if (answer != null) {
                    iceGatheringDeferred = CompletableDeferred()
                    peerConnection?.setLocalDescription(object : SdpObserver {
                        override fun onCreateSuccess(desc: SessionDescription?) {}
                        override fun onSetSuccess() {
                            Log.i(tag, "Local description set successfully")
                        }
                        override fun onCreateFailure(err: String?) {}
                        override fun onSetFailure(err: String?) {}
                    }, answer)

                    scope.launch {
                        try {
                            withTimeout(1500) {
                                iceGatheringDeferred?.await()
                            }
                        } catch (_: Exception) {
                            Log.w(tag, "ICE gathering timed out, proceeding with current SDP")
                        }
                        val localDesc = peerConnection?.localDescription
                        if (localDesc != null) {
                            continuation.resume(localDesc.description)
                        } else {
                            continuation.resume(null)
                        }
                    }
                } else {
                    continuation.resume(null)
                }
            }
            override fun onSetSuccess() {}
            override fun onCreateFailure(err: String?) {
                Log.e(tag, "Failed to create answer: $err")
                continuation.resume(null)
            }
            override fun onSetFailure(err: String?) {}
        }, constraints)
    }

    private fun createPeerConnection() {
        if (peerConnection != null) {
            try {
                peerConnection?.dispose()
            } catch (_: Exception) {}
            peerConnection = null
        }
        val rtcConfig = PeerConnection.RTCConfiguration(iceServers).apply {
            sdpSemantics = PeerConnection.SdpSemantics.UNIFIED_PLAN
        }

        peerConnection = factory?.createPeerConnection(rtcConfig, object : PeerConnection.Observer {
            override fun onSignalingChange(state: PeerConnection.SignalingState?) {
                Log.i(tag, "Signaling state changed: $state")
            }
            override fun onIceConnectionChange(state: PeerConnection.IceConnectionState?) {
                Log.i(tag, "ICE connection state changed: $state")
                if (state == PeerConnection.IceConnectionState.DISCONNECTED ||
                    state == PeerConnection.IceConnectionState.FAILED ||
                    state == PeerConnection.IceConnectionState.CLOSED) {
                    Log.i(tag, "ICE connection disconnected/failed/closed. Resetting remote video track and peer connection.")
                    scope.launch {
                        _remoteVideoTrack.value = null
                        try {
                            peerConnection?.dispose()
                        } catch (_: Exception) {}
                        peerConnection = null
                    }
                }
            }
            override fun onIceConnectionReceivingChange(p0: Boolean) {}
            override fun onIceGatheringChange(state: PeerConnection.IceGatheringState?) {
                Log.i(tag, "ICE gathering state changed: $state")
                if (state == PeerConnection.IceGatheringState.COMPLETE) {
                    iceGatheringDeferred?.complete(Unit)
                }
            }
            override fun onIceCandidate(candidate: IceCandidate?) {
                if (candidate != null) {
                    Log.i(tag, "New ICE candidate gathered: ${candidate.sdp}")
                }
            }
            override fun onIceCandidatesRemoved(p0: Array<out IceCandidate>?) {}
            override fun onTrack(transceiver: RtpTransceiver?) {
                val track = transceiver?.receiver?.track()
                Log.i(tag, "onTrack called: transceiver=${transceiver?.mid}, kind=${track?.kind()}, id=${track?.id()}")
                if (track is VideoTrack) {
                    track.setEnabled(true)
                    _remoteVideoTrack.value = track
                    Log.i(tag, "Received remote VideoTrack via onTrack: id=${track.id()}, enabled=${track.enabled()}, state=${track.state()}")
                }
            }
            override fun onAddStream(stream: MediaStream) {
                if (stream.videoTracks.isNotEmpty()) {
                    val track = stream.videoTracks[0]
                    track.setEnabled(true)
                    _remoteVideoTrack.value = track
                    Log.i(tag, "Received remote video track via onAddStream: id=${track.id()}, enabled=${track.enabled()}")
                }
            }
            override fun onRemoveStream(p0: MediaStream?) {}
            override fun onDataChannel(p0: DataChannel?) {}
            override fun onRenegotiationNeeded() {}
            override fun onAddTrack(receiver: RtpReceiver?, mediaStreams: Array<out MediaStream>?) {
                receiver?.track()?.let { track ->
                    if (track is VideoTrack) {
                        track.setEnabled(true)
                        _remoteVideoTrack.value = track
                        Log.i(tag, "Received remote video track via onAddTrack: id=${track.id()}, enabled=${track.enabled()}")
                    }
                }
            }
        })
    }

    fun attachVideoRenderer(renderer: SurfaceViewRenderer) {
        scope.launch {
            var previousTrack: VideoTrack? = null

            remoteVideoTrack.collect { track ->
                if (previousTrack != null) {
                    try {
                        previousTrack?.removeSink(renderer)
                    } catch (_: Exception) {}
                    previousTrack = null
                }

                if (track != null) {
                    Log.i(tag, "Attaching video sink to SurfaceViewRenderer for track ID: ${track.id()}, enabled: ${track.enabled()}")
                    track.setEnabled(true)
                    track.addSink(renderer)
                    previousTrack = track
                } else {
                    Log.i(tag, "remoteVideoTrack is null in attachVideoRenderer")
                    renderer.clearImage()
                }
            }
        }
    }

    fun release() {
        try {
            signalingClient.stopServer()
            peerConnection?.dispose()
            peerConnection = null
            factory?.dispose()
            factory = null
            eglBase.release()
        } catch (e: Exception) {
            Log.e(tag, "Error releasing WebRTC resources", e)
        }
    }
}
