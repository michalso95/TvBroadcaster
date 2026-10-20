package com.example.tvbroadcast

import android.graphics.Bitmap
import android.graphics.Color
import android.os.Bundle
import android.os.PowerManager
import android.view.View
import android.view.WindowManager
import android.widget.ImageView
import android.widget.TextView
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.lifecycle.lifecycleScope
import com.example.tvbroadcast.network.ReceiverSignalingClient
import com.example.tvbroadcast.webrtc.WebRtcReceiverManager
import com.google.zxing.BarcodeFormat
import com.google.zxing.qrcode.QRCodeWriter
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import org.webrtc.RendererCommon
import org.webrtc.SurfaceViewRenderer

class MainActivity : AppCompatActivity() {
    private lateinit var signalingClient: ReceiverSignalingClient
    private lateinit var webRtcReceiverManager: WebRtcReceiverManager
    private lateinit var surfaceViewRenderer: SurfaceViewRenderer
    private lateinit var ipTextView: TextView
    private lateinit var statusTextView: TextView
    private lateinit var statusLayout: View
    private lateinit var qrCodeImageView: ImageView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContentView(R.layout.activity_main)

        ViewCompat.setOnApplyWindowInsetsListener(findViewById(R.id.main)) { v, insets ->
            val systemBars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            v.setPadding(systemBars.left, systemBars.top, systemBars.right, systemBars.bottom)
            insets
        }

        ipTextView = findViewById(R.id.tv_ip_address)
        statusTextView = findViewById(R.id.tv_connection_status)
        statusLayout = findViewById(R.id.status_layout)
        surfaceViewRenderer = findViewById(R.id.surface_view_renderer)
        qrCodeImageView = findViewById(R.id.iv_qr_code)

        signalingClient = ReceiverSignalingClient(8080)
        webRtcReceiverManager = WebRtcReceiverManager(applicationContext, signalingClient)

        surfaceViewRenderer.init(webRtcReceiverManager.eglBase.eglBaseContext, null)
        surfaceViewRenderer.setEnableHardwareScaler(true)
        surfaceViewRenderer.setScalingType(RendererCommon.ScalingType.SCALE_ASPECT_FIT)
        surfaceViewRenderer.setMirror(false)

        webRtcReceiverManager.attachVideoRenderer(surfaceViewRenderer)
        webRtcReceiverManager.startListening()

        lifecycleScope.launch {
            signalingClient.localIpAddress.collectLatest { ip ->
                ipTextView.text = "Receiver IP: $ip:8080"
                if (ip != "Unknown") {
                    val qrBitmap = generateQRCode("http://$ip:8080")
                    if (qrBitmap != null) {
                        qrCodeImageView.setImageBitmap(qrBitmap)
                    }
                }
            }
        }

        lifecycleScope.launch {
            webRtcReceiverManager.remoteVideoTrack.collectLatest { track ->
                if (track != null) {
                    statusLayout.visibility = View.GONE
                    statusTextView.text = "Status: Connected (Streaming...)"
                    statusTextView.setTextColor(resources.getColor(android.R.color.holo_green_light, theme))
                    window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

                    // Wake up screen and dismiss screensaver (Ambient Mode) on Android TV when transmission starts
                    val powerManager = getSystemService(POWER_SERVICE) as PowerManager
                    @Suppress("DEPRECATION")
                    val wakeLock = powerManager.newWakeLock(
                        PowerManager.FULL_WAKE_LOCK or
                        PowerManager.ACQUIRE_CAUSES_WAKEUP or
                        PowerManager.ON_AFTER_RELEASE,
                        "TvBroadcast:TransmissionWakeLock"
                    )
                    wakeLock.acquire(3000L)

                    if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O_MR1) {
                        setShowWhenLocked(true)
                        setTurnScreenOn(true)
                    } else {
                        @Suppress("DEPRECATION")
                        window.addFlags(
                            WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or
                            WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON or
                            WindowManager.LayoutParams.FLAG_DISMISS_KEYGUARD
                        )
                    }
                } else {
                    statusLayout.visibility = View.VISIBLE
                    statusTextView.text = "Status: Waiting for transmitter..."
                    statusTextView.setTextColor(resources.getColor(android.R.color.darker_gray, theme))
                    window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                }
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        webRtcReceiverManager.release()
        surfaceViewRenderer.release()
    }

    private fun generateQRCode(text: String, width: Int = 512, height: Int = 512): Bitmap? {
        return try {
            val qrCodeWriter = QRCodeWriter()
            val bitMatrix = qrCodeWriter.encode(text, BarcodeFormat.QR_CODE, width, height)
            val bmp = Bitmap.createBitmap(width, height, Bitmap.Config.RGB_565)
            for (x in 0 until width) {
                for (y in 0 until height) {
                    bmp.setPixel(x, y, if (bitMatrix.get(x, y)) Color.BLACK else Color.WHITE)
                }
            }
            bmp
        } catch (_: Exception) {
            null
        }
    }
}
