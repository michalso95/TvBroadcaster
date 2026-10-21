import Foundation

struct ReceiverAddress {
    let url: URL

    init(_ input: String) throws {
        let trimmed = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            throw AddressError.empty
        }

        let candidate = trimmed.contains("://") ? trimmed : "http://\(trimmed)"
        guard var components = URLComponents(string: candidate),
              components.scheme?.lowercased() == "http",
              let host = components.host, !host.isEmpty,
              components.user == nil, components.password == nil,
              components.query == nil, components.fragment == nil else {
            throw AddressError.invalid
        }

        let path = components.percentEncodedPath
        if !path.isEmpty, path != "/" {
            throw AddressError.invalid
        }
        guard components.port == nil || (1...65535).contains(components.port!) else {
            throw AddressError.invalid
        }
        components.port = components.port ?? 8080
        components.path = "/"

        guard let url = components.url else {
            throw AddressError.invalid
        }
        self.url = url
    }

    enum AddressError: LocalizedError {
        case empty
        case invalid

        var errorDescription: String? {
            switch self {
            case .empty:
                return "Enter the TV's IP address or host name."
            case .invalid:
                return "Enter a host name or an HTTP address such as http://192.168.1.50:8080."
            }
        }
    }
}
