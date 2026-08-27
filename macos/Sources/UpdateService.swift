import AppKit
import CryptoKit
import Foundation

@MainActor
final class UpdateService: ObservableObject {
    enum State: Equatable {
        case idle
        case checking
        case downloading(Double)
        case installing
        case failed(String)
    }

    static let serverURLKey = "AcervoServerBaseURL"
    private enum Keys {
        static let automatic = "AcervoAutomaticUpdateChecks"
        static let automaticInstall = "AcervoAutomaticUpdateInstall"
        static let lastCheck = "AcervoLastUpdateCheck"
    }

    private static let checkInterval: TimeInterval = 6 * 3600
    private static let chunkBytes = 1_048_576

    @Published private(set) var available: MacRelease?
    @Published private(set) var state: State = .idle
    @Published private(set) var lastCheck: Date?
    @Published private(set) var statusMessage: String?

    var onAvailabilityChanged: ((MacRelease?) -> Void)?
    var confirmRestart: ((MacRelease) -> Bool)?

    private let defaults: UserDefaults
    private let session: URLSession
    private var timer: Timer?

    init(defaults: UserDefaults = .standard, session: URLSession = .shared) {
        self.defaults = defaults
        self.session = session
        if defaults.object(forKey: Keys.automatic) == nil { defaults.set(true, forKey: Keys.automatic) }
        lastCheck = defaults.object(forKey: Keys.lastCheck) as? Date
    }

    var storedServerURL: String { defaults.string(forKey: Self.serverURLKey) ?? "" }
    var hasServerURL: Bool { !storedServerURL.isEmpty }

    func saveServerURL(_ raw: String) throws {
        let normalized = try ServerAddress.normalize(raw)
        defaults.set(normalized, forKey: Self.serverURLKey)
        statusMessage = "Server saved."
        if automaticChecks { start() }
    }

    var automaticChecks: Bool {
        get { defaults.bool(forKey: Keys.automatic) }
        set {
            objectWillChange.send()
            defaults.set(newValue, forKey: Keys.automatic)
            if newValue { start() } else { timer?.invalidate() }
        }
    }

    var automaticInstall: Bool {
        get { defaults.bool(forKey: Keys.automaticInstall) }
        set { objectWillChange.send(); defaults.set(newValue, forKey: Keys.automaticInstall) }
    }

    var isBusy: Bool {
        switch state {
        case .checking, .downloading, .installing: true
        case .idle, .failed: false
        }
    }

    func start() {
        timer?.invalidate()
        guard automaticChecks, hasServerURL, !AppVersion.isDevelopmentBuild else { return }
        Task { await self.check(force: false) }
        let timer = Timer.scheduledTimer(withTimeInterval: Self.checkInterval, repeats: true) { [weak self] _ in
            Task { @MainActor in await self?.check(force: false) }
        }
        timer.tolerance = 300
        self.timer = timer
    }

    func check(force: Bool) async {
        guard state != .checking else { return }
        if !force {
            guard automaticChecks, hasServerURL, !AppVersion.isDevelopmentBuild else { return }
            if let lastCheck, Date().timeIntervalSince(lastCheck) < Self.checkInterval - 60 { return }
        }
        guard let manifestURL = serverURL(path: "/api/acervo/v1/mac-release") else {
            if force { state = .failed("Enter the Acervo server URL first.") }
            return
        }

        statusMessage = nil
        state = .checking
        do {
            var request = URLRequest(url: manifestURL)
            request.timeoutInterval = 15
            request.setValue("application/json", forHTTPHeaderField: "Accept")
            let (data, response) = try await session.data(for: request)
            guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
                throw UpdateFailure.message("The server did not answer the update check.")
            }
            let now = Date()
            defaults.set(now, forKey: Keys.lastCheck)
            lastCheck = now
            let offered = try JSONDecoder().decode(MacRelease.Envelope.self, from: data).data
            let newer = offered.flatMap { $0.isNewer(than: AppVersion.build) ? $0 : nil }
            available = newer
            onAvailabilityChanged?(newer)
            state = .idle
            statusMessage = newer == nil ? "Acervo is up to date." : nil
            if newer != nil, !force, automaticInstall { await install() }
        } catch {
            available = nil
            onAvailabilityChanged?(nil)
            state = force ? .failed(describe(error)) : .idle
        }
    }

    func install() async {
        guard let release = available else { return }
        guard let downloadURL = serverURL(path: release.url) else {
            state = .failed("The server gave an invalid download address.")
            return
        }
        let bundle = URL(fileURLWithPath: Bundle.main.bundlePath)
        guard bundle.pathExtension == "app" else {
            state = .failed("This development build cannot replace itself.")
            return
        }
        guard FileManager.default.isWritableFile(atPath: bundle.deletingLastPathComponent().path) else {
            state = .failed("Acervo cannot replace itself here. Move it to a writable Applications folder and try again.")
            return
        }

        state = .downloading(0)
        do {
            let archive = try await download(downloadURL, expecting: release)
            state = .installing
            try await Task.detached(priority: .userInitiated) {
                defer { try? FileManager.default.removeItem(at: archive) }
                try Self.verify(archive, size: release.size, sha256: release.sha256)
                let replacement = try Self.expand(archive)
                defer { try? FileManager.default.removeItem(at: replacement.deletingLastPathComponent()) }
                _ = try FileManager.default.replaceItemAt(bundle, withItemAt: replacement)
            }.value
            state = .idle
            available = nil
            onAvailabilityChanged?(nil)
            guard confirmRestart?(release) ?? true else { return }
            relaunch(at: bundle)
        } catch {
            let message = describe(error)
            state = .failed(message)
            presentFailure(message)
        }
    }

    static func progressUpdate(_ fraction: Double, whileShowing state: State) -> State? {
        guard case .downloading = state else { return nil }
        return .downloading(fraction)
    }

    func downloadForTesting(_ url: URL, size: Int) async throws -> URL {
        try await download(url, expecting: MacRelease(version: "0", build: "0", file: "test.zip", size: size, sha256: "", url: url.path))
    }

    private func download(_ url: URL, expecting release: MacRelease) async throws -> URL {
        let destination = FileManager.default.temporaryDirectory
            .appendingPathComponent("AcervoUpdate-\(UUID().uuidString).zip")
        guard FileManager.default.createFile(atPath: destination.path, contents: nil) else {
            throw UpdateFailure.message("The update could not be saved.")
        }
        let handle = try FileHandle(forWritingTo: destination)
        defer { try? handle.close() }

        guard release.size > 0 else {
            try handle.write(contentsOf: try await piece(of: url, range: nil).data)
            return destination
        }
        var received = 0
        while received < release.size {
            let last = min(received + Self.chunkBytes, release.size) - 1
            let answer = try await piece(of: url, range: (received, last))
            guard !answer.data.isEmpty else { throw UpdateFailure.message("The update stopped arriving.") }
            try handle.write(contentsOf: answer.data)
            received += answer.data.count
            if let next = Self.progressUpdate(min(1, Double(received) / Double(release.size)), whileShowing: state) {
                state = next
            }
            if !answer.partial { break }
        }
        return destination
    }

    private func piece(of url: URL, range: (first: Int, last: Int)?) async throws -> (data: Data, partial: Bool) {
        var request = URLRequest(url: url)
        request.timeoutInterval = 60
        request.cachePolicy = .reloadIgnoringLocalCacheData
        if let range { request.setValue("bytes=\(range.first)-\(range.last)", forHTTPHeaderField: "Range") }
        for attempt in 0..<2 {
            do {
                let (data, response) = try await session.data(for: request)
                guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
                    throw UpdateFailure.message("The update could not be downloaded.")
                }
                return (data, http.statusCode == 206)
            } catch {
                if attempt == 1 { throw error }
            }
        }
        throw UpdateFailure.message("The update could not be downloaded.")
    }

    nonisolated static func verify(_ archive: URL, size: Int, sha256 expected: String) throws {
        let data = try Data(contentsOf: archive, options: .mappedIfSafe)
        if size > 0, data.count != size { throw UpdateFailure.message("The downloaded update has the wrong size.") }
        let checksum = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        guard checksum.caseInsensitiveCompare(expected) == .orderedSame else {
            throw UpdateFailure.message("The downloaded update did not match its checksum and was discarded.")
        }
    }

    private nonisolated static func expand(_ archive: URL) throws -> URL {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("AcervoUpdate-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/ditto")
        process.arguments = ["-x", "-k", archive.path, directory.path]
        try process.run()
        process.waitUntilExit()
        guard process.terminationStatus == 0 else { throw UpdateFailure.message("The update archive could not be expanded.") }
        let contents = try FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil)
        guard let application = contents.first(where: { $0.pathExtension == "app" }) else {
            throw UpdateFailure.message("The archive did not contain an application.")
        }
        return application
    }

    private func serverURL(path: String) -> URL? {
        let base = storedServerURL
        guard !base.isEmpty else { return nil }
        if let absolute = URL(string: path), absolute.scheme != nil { return absolute }
        return URL(string: base.hasSuffix("/") ? String(base.dropLast()) + path : base + path)
    }

    private func relaunch(at bundle: URL) {
        let script = FileManager.default.temporaryDirectory.appendingPathComponent("acervo-relaunch-\(UUID().uuidString).sh")
        let quoted = bundle.path.replacingOccurrences(of: "'", with: "'\\''")
        let contents = "#!/bin/sh\nsleep 1\nopen '\(quoted)'\nrm -f \"$0\"\n"
        try? contents.write(to: script, atomically: true, encoding: .utf8)
        try? FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: script.path)
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/sh")
        process.arguments = [script.path]
        try? process.run()
        NSApp.terminate(nil)
    }

    private func describe(_ error: Error) -> String {
        if case let UpdateFailure.message(text) = error { return text }
        return (error as NSError).localizedDescription
    }

    private func presentFailure(_ message: String) {
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
        let alert = NSAlert()
        alert.messageText = "Acervo could not install the update"
        alert.informativeText = message
        alert.alertStyle = .warning
        alert.addButton(withTitle: "OK")
        alert.runModal()
    }
}

enum UpdateFailure: Error {
    case message(String)
}
