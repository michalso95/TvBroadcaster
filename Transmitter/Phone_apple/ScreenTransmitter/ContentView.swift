import SwiftUI
import VisionKit
import AVFoundation

private let appGroupIdentifier = "group.private.ScreenTransmitter"
private let broadcastExtensionIdentifier = "private.ScreenTransmitter.TvBroadcasterBroadcast"
private let receiverURLKey = "receiverURL"

struct ContentView: View {
    @State private var address = UserDefaults(suiteName: appGroupIdentifier)?.string(forKey: receiverURLKey) ?? ""
    @State private var isShowingScanner = false
    @State private var isCheckingReceiver = false
    @State private var statusMessage = "Enter the TV address or scan its QR code."
    @State private var isError = false

    var body: some View {
        ZStack {
            LinearGradient(colors: [Color(red: 0.04, green: 0.08, blue: 0.16), Color(red: 0.08, green: 0.16, blue: 0.27)], startPoint: .topLeading, endPoint: .bottomTrailing)
                .ignoresSafeArea()

            ScrollView {
                VStack(alignment: .leading, spacing: 26) {
                    header
                    connectionCard
                    broadcastCard
                    footer
                }
                .padding(.horizontal, 22)
                .padding(.top, 24)
                .padding(.bottom, 30)
                .frame(maxWidth: 520)
                .frame(maxWidth: .infinity)
            }
        }
        .preferredColorScheme(.dark)
        .sheet(isPresented: $isShowingScanner) {
            scannerSheet
                .presentationDetents([.large])
                .presentationDragIndicator(.visible)
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            Image(systemName: "airplayvideo")
                .font(.system(size: 30, weight: .semibold))
                .foregroundStyle(Color.cyan)
                .frame(width: 62, height: 62)
                .background(Color.cyan.opacity(0.13), in: RoundedRectangle(cornerRadius: 19))
            Text("TV Broadcaster")
                .font(.system(size: 32, weight: .bold, design: .rounded))
            Text("Share your iPhone screen with a TV on your network.")
                .font(.subheadline)
                .foregroundStyle(.white.opacity(0.65))
        }
        .padding(.bottom, 2)
    }

    private var connectionCard: some View {
        VStack(alignment: .leading, spacing: 16) {
            Label("Connect to your TV", systemImage: "wifi")
                .font(.headline)
            TextField("IP address or host name", text: $address)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .keyboardType(.URL)
                .padding(15)
                .background(.white.opacity(0.07), in: RoundedRectangle(cornerRadius: 14))
                .overlay(RoundedRectangle(cornerRadius: 14).stroke(.white.opacity(0.1)))

            Button(action: openScanner) {
                Label("Scan TV QR code", systemImage: "qrcode.viewfinder")
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                    .background(.white.opacity(0.08), in: RoundedRectangle(cornerRadius: 14))
            }
            .buttonStyle(.plain)

            Button(action: connectToReceiver) {
                HStack {
                    if isCheckingReceiver { ProgressView().tint(.white) }
                    Text(isCheckingReceiver ? "Checking TV…" : "Save and continue")
                    Spacer()
                    Image(systemName: "arrow.right")
                }
                .fontWeight(.semibold)
                .padding(16)
                .background(Color.cyan, in: RoundedRectangle(cornerRadius: 14))
                .foregroundStyle(Color(red: 0.02, green: 0.09, blue: 0.14))
            }
            .disabled(isCheckingReceiver)
            .buttonStyle(.plain)

            Label(statusMessage, systemImage: isError ? "exclamationmark.circle.fill" : "info.circle.fill")
                .font(.footnote)
                .foregroundStyle(isError ? Color.orange : Color.white.opacity(0.58))
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(20)
        .background(.white.opacity(0.055), in: RoundedRectangle(cornerRadius: 22))
        .overlay(RoundedRectangle(cornerRadius: 22).stroke(.white.opacity(0.08)))
    }

    private var broadcastCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            Label("Start screen sharing", systemImage: "record.circle")
                .font(.headline)
            Text("When the receiver is ready, use the system broadcast button below and choose TV Broadcaster. iOS will ask you to confirm before sharing.")
                .font(.subheadline)
                .foregroundStyle(.white.opacity(0.62))
                .fixedSize(horizontal: false, vertical: true)
            BroadcastPicker(extensionIdentifier: broadcastExtensionIdentifier)
                .frame(height: 52)
                .frame(maxWidth: .infinity)
                .background(.white.opacity(0.08), in: RoundedRectangle(cornerRadius: 14))
                .clipShape(RoundedRectangle(cornerRadius: 14))
                .disabled(UserDefaults(suiteName: appGroupIdentifier)?.string(forKey: receiverURLKey) == nil)
                .opacity(UserDefaults(suiteName: appGroupIdentifier)?.string(forKey: receiverURLKey) == nil ? 0.45 : 1)
        }
        .padding(20)
        .background(.white.opacity(0.055), in: RoundedRectangle(cornerRadius: 22))
        .overlay(RoundedRectangle(cornerRadius: 22).stroke(.white.opacity(0.08)))
    }

    private var footer: some View {
        HStack(spacing: 8) {
            Image(systemName: "lock.shield")
            Text("Video is sent directly to your receiver using WebRTC.")
        }
        .font(.caption)
        .foregroundStyle(.white.opacity(0.48))
        .frame(maxWidth: .infinity, alignment: .center)
    }

    @ViewBuilder
    private var scannerSheet: some View {
        NavigationStack {
            Group {
                if DataScannerViewController.isSupported && DataScannerViewController.isAvailable {
                    QRScannerView(onScan: { value in
                        address = value
                        isShowingScanner = false
                        statusMessage = "QR code scanned. Check the address, then continue."
                        isError = false
                    }, onCancel: {
                        isShowingScanner = false
                    })
                    .ignoresSafeArea()
                } else {
                    VStack(spacing: 14) {
                        Image(systemName: "qrcode.viewfinder")
                            .font(.system(size: 44))
                            .foregroundStyle(Color.cyan)
                        Text("QR scanning unavailable")
                            .font(.headline)
                        Text("This iPhone does not support live QR scanning.")
                            .font(.subheadline)
                            .foregroundStyle(.white.opacity(0.65))
                            .multilineTextAlignment(.center)
                    }
                    .padding(32)
                }
            }
            .navigationTitle("Scan TV QR code")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") { isShowingScanner = false }
                }
            }
        }
        .preferredColorScheme(.dark)
    }

    private func openScanner() {
        guard DataScannerViewController.isSupported else {
            statusMessage = "Live QR scanning requires a supported iPhone running iOS 16 or later."
            isError = true
            return
        }
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized:
            isShowingScanner = true
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .video) { granted in
                DispatchQueue.main.async {
                    if granted {
                        isShowingScanner = true
                    } else {
                        statusMessage = "Allow camera access in Settings to scan the TV QR code."
                        isError = true
                    }
                }
            }
        default:
            statusMessage = "Allow camera access in Settings to scan the TV QR code."
            isError = true
        }
    }

    private func connectToReceiver() {
        let receiver: ReceiverAddress
        do {
            receiver = try ReceiverAddress(address)
        } catch {
            statusMessage = error.localizedDescription
            isError = true
            return
        }

        isCheckingReceiver = true
        isError = false
        statusMessage = "Checking receiver…"
        var request = URLRequest(url: receiver.url)
        request.httpMethod = "GET"
        request.timeoutInterval = 5
        URLSession.shared.dataTask(with: request) { _, response, error in
            DispatchQueue.main.async {
                isCheckingReceiver = false
                if let error {
                    statusMessage = "Could not reach the TV. Check that the TV is on the same network. (\(error.localizedDescription))"
                    isError = true
                    return
                }
                guard let response = response as? HTTPURLResponse, (200..<400).contains(response.statusCode) else {
                    statusMessage = "The address responded, but it does not look like a ready TV receiver."
                    isError = true
                    return
                }
                address = receiver.url.absoluteString
                UserDefaults(suiteName: appGroupIdentifier)?.set(receiver.url.absoluteString, forKey: receiverURLKey)
                statusMessage = "TV receiver found. Start a broadcast to share your screen."
                isError = false
            }
        }.resume()
    }
}

#Preview {
    ContentView()
}
