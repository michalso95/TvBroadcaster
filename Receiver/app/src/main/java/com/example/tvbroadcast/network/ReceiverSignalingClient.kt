package com.example.tvbroadcast.network

import android.util.Log
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.PrintWriter
import java.net.NetworkInterface
import java.net.ServerSocket
import java.net.Socket
import java.util.Collections

data class SignalingMessage(
    val type: String, // "offer", "answer", "candidate"
    val sdp: String? = null,
    val candidate: String? = null,
    val sdpMid: String? = null,
    val sdpMLineIndex: Int? = null
)

class ReceiverSignalingClient(private val port: Int = 8080) {
    private val tag = "ReceiverSignalingClient"
    private var serverSocket: ServerSocket? = null
    private var serverJob: Job? = null
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    private val _connectionState = MutableStateFlow(false)
    val connectionState: StateFlow<Boolean> = _connectionState

    private val _localIpAddress = MutableStateFlow(getLocalIpAddress() ?: "Unknown")
    val localIpAddress: StateFlow<String> = _localIpAddress

    var signalingListener: SignalingListener? = null

    interface SignalingListener {
        suspend fun onOfferReceived(sdp: String): String?
        fun onCandidateReceived(msg: SignalingMessage)
    }

    fun startServer() {
        if (serverSocket != null) return
        serverJob = scope.launch {
            try {
                serverSocket = ServerSocket(port)
                Log.i(tag, "Signaling server started on port $port, IP: ${_localIpAddress.value}")
                while (isActive) {
                    val socket = try {
                        serverSocket?.accept()
                    } catch (e: Exception) {
                        break
                    } ?: break

                    launch {
                        handleClient(socket)
                    }
                }
            } catch (e: Exception) {
                Log.e(tag, "Error in signaling server", e)
            }
        }
    }

    private suspend fun handleClient(socket: Socket) {
        try {
            _connectionState.value = true
            Log.i(tag, "Client connected: ${socket.inetAddress.hostAddress}")

            val reader = BufferedReader(InputStreamReader(socket.getInputStream()))
            val writer = PrintWriter(socket.getOutputStream(), true)

            var line: String?
            val requestBuilder = StringBuilder()
            var contentLength = 0
            var method = "GET"

            val firstLine = reader.readLine()
            if (firstLine != null) {
                requestBuilder.append(firstLine).append("\n")
                if (firstLine.startsWith("POST", ignoreCase = true)) {
                    method = "POST"
                } else if (firstLine.startsWith("GET", ignoreCase = true)) {
                    method = "GET"
                }
            }

            while (reader.readLine().also { line = it } != null) {
                if (line.isNullOrEmpty()) {
                    break
                } else {
                    requestBuilder.append(line).append("\n")
                    if (line.startsWith("Content-Length:", ignoreCase = true)) {
                        contentLength = line.substring(15).trim().toIntOrNull() ?: 0
                    }
                }
            }

            if (method == "POST") {
                val bodyChars = CharArray(contentLength)
                var readCount = 0
                while (readCount < contentLength) {
                    val c = reader.read()
                    if (c == -1) break
                    bodyChars[readCount++] = c.toChar()
                }
                val body = String(bodyChars, 0, readCount)

                val responseJson = processSignalingBody(body)

                writer.println("HTTP/1.1 200 OK")
                writer.println("Content-Type: application/json")
                writer.println("Connection: close")
                writer.println()
                writer.println(responseJson)
                writer.flush()
            } else {
                // GET request
                writer.println("HTTP/1.1 200 OK")
                writer.println("Content-Type: application/json")
                writer.println("Connection: close")
                writer.println()
                writer.println("{\"status\":\"receiver_ready\",\"ip\":\"${_localIpAddress.value}\"}")
                writer.flush()
            }
        } catch (e: Exception) {
            Log.e(tag, "Error handling client connection", e)
        } finally {
            try {
                socket.close()
            } catch (_: Exception) {}
            _connectionState.value = false
            Log.i(tag, "Client disconnected")
        }
    }

    private suspend fun processSignalingBody(body: String): String {
        return try {
            val json = JSONObject(body)
            val type = json.optString("type")
            when (type) {
                "offer" -> {
                    val sdp = json.optString("sdp")
                    val answerSdp = signalingListener?.onOfferReceived(sdp)
                    if (answerSdp != null) {
                        JSONObject().apply {
                            put("type", "answer")
                            put("sdp", answerSdp)
                        }.toString()
                    } else {
                        JSONObject().apply {
                            put("status", "error")
                            put("message", "Failed to create answer")
                        }.toString()
                    }
                }
                "candidate" -> {
                    val candidate = if (json.has("candidate") && !json.isNull("candidate")) json.optString("candidate") else null
                    val sdpMid = if (json.has("sdpMid") && !json.isNull("sdpMid")) json.optString("sdpMid") else null
                    val sdpMLineIndex = if (json.has("sdpMLineIndex") && !json.isNull("sdpMLineIndex")) json.optInt("sdpMLineIndex", 0) else null
                    val msg = SignalingMessage(type, null, candidate, sdpMid, sdpMLineIndex)
                    signalingListener?.onCandidateReceived(msg)
                    "{\"status\":\"ok\"}"
                }
                else -> {
                    "{\"status\":\"unknown_type\"}"
                }
            }
        } catch (e: Exception) {
            Log.e(tag, "Failed to process signaling body: $body", e)
            "{\"status\":\"error\",\"message\":\"${e.localizedMessage}\"}"
        }
    }

    fun stopServer() {
        try {
            serverJob?.cancel()
            serverSocket?.close()
            serverSocket = null
            _connectionState.value = false
            Log.i(tag, "Signaling server stopped")
        } catch (e: Exception) {
            Log.e(tag, "Error stopping server", e)
        }
    }

    private fun getLocalIpAddress(): String? {
        try {
            val interfaces = Collections.list(NetworkInterface.getNetworkInterfaces())
            for (intf in interfaces) {
                val addrs = Collections.list(intf.inetAddresses)
                for (addr in addrs) {
                    if (!addr.isLoopbackAddress) {
                        val sAddr = addr.hostAddress ?: continue
                        val isIPv4 = sAddr.indexOf(':') < 0
                        if (isIPv4) return sAddr
                    }
                }
            }
        } catch (_: Exception) {}
        return null
    }
}
