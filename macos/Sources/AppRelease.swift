import Foundation

enum AppVersion {
    static var name: String {
        Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "0.0.0"
    }

    static var build: String {
        Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "0"
    }

    static var label: String { "\(name) (\(build))" }

    static var isDevelopmentBuild: Bool {
        build == "0" || !Bundle.main.bundlePath.hasSuffix(".app")
    }
}

struct MacRelease: Decodable, Equatable {
    let version: String
    let build: String
    let file: String
    let size: Int
    let sha256: String
    let url: String

    struct Envelope: Decodable { let data: MacRelease? }

    func isNewer(than currentBuild: String) -> Bool {
        guard let offered = UInt64(build) else { return false }
        guard let current = UInt64(currentBuild) else { return true }
        return offered > current
    }
}

enum ServerAddress {
    static func normalize(_ raw: String) throws -> String {
        let value = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: #"/+$"#, with: "", options: .regularExpression)
        guard var components = URLComponents(string: value),
              let scheme = components.scheme?.lowercased(),
              let host = components.host?.lowercased(), !host.isEmpty else {
            throw UpdateFailure.message("Enter a valid server URL.")
        }
        let local = host == "localhost" || host == "127.0.0.1" || host == "::1"
        guard scheme == "https" || (local && scheme == "http") else {
            throw UpdateFailure.message("Use HTTPS. HTTP is allowed only for local development.")
        }
        guard components.user == nil, components.password == nil,
              components.query == nil, components.fragment == nil else {
            throw UpdateFailure.message("Enter only the server base URL.")
        }
        components.path = components.path.replacingOccurrences(
            of: #"/api/acervo/v\d+/?$"#, with: "", options: .regularExpression
        )
        guard let normalized = components.url?.absoluteString else {
            throw UpdateFailure.message("Enter a valid server URL.")
        }
        return normalized.hasSuffix("/") ? String(normalized.dropLast()) : normalized
    }
}
