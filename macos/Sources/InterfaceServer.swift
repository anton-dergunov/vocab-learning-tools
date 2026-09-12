import Foundation

/// Serves the bundled interface over `http://127.0.0.1`, so the app has a real web origin.
///
/// A custom scheme was the obvious way to load a bundled single-page app, and it worked for
/// everything the interface did on its own. It stops working the moment the page has to embed
/// somebody else's: YouTube validates the embedding document's origin and referrer, `acervo://app`
/// is not a web origin at all, and the embed comes back as error 153 — "Embedded playback
/// unavailable" — with nothing the page can do to satisfy it.
///
/// Loopback HTTP is the conventional answer and it fixes the class rather than the case. `127.0.0.1`
/// is a **secure context** by specification, so `crypto`, IndexedDB and third-party embeds behave
/// exactly as they do in a browser — which is where the interface is developed and tested. Nothing
/// else about the app changes.
///
/// **The port is fixed, because the origin contains it.** Storage in a web view is keyed by origin,
/// so a port that moved between launches would throw the replica away every time the app opened —
/// and a replica thrown away can only be refilled *from the server*, which is exactly the thing
/// that is not there when you are offline. An app that quietly needed the network to show you
/// yesterday's words would not be offline-first in any sense that matters.
///
/// So it never moves on its own. It is deliberately in the **registered** range rather than the
/// ephemeral one: the ephemeral range is where the system hands out ports for outbound connections,
/// so a port remembered from there could be taken by any program's client socket between launches.
/// Nothing is auto-assigned from 27703.
///
/// And if it cannot be had, the app **says so and stops** rather than opening on another origin.
/// Silently moving would show an empty vocabulary and call it your own; naming the port is
/// something you can act on, and `AcervoInterfacePort` overrides it if this machine really has a
/// permanent conflict.
///
/// Written on POSIX sockets rather than `Network.framework`, for one reason worth recording:
/// `NWListener` refuses to bind under a restricted execution environment, so the tests below could
/// not be run where this was written. Forty more lines buys a server whose behaviour is checked
/// rather than assumed.
///
/// Bound to `127.0.0.1` alone and never to `0.0.0.0`, so nothing off this machine can reach it —
/// the same rule the deployment lives by about not claiming a host's ports.
final class InterfaceServer: @unchecked Sendable {
    /// The one port, in the registered range where nothing is auto-assigned.
    static let defaultPort: UInt16 = 27703
    /// An override, for a machine with a permanent conflict. Absent almost always.
    static let portDefaultsKey = "AcervoInterfacePort"

    private let root: URL
    private let defaults: UserDefaults
    private let lock = NSLock()
    private var descriptor: Int32 = -1

    private(set) var port: UInt16 = 0

    init(root: URL, defaults: UserDefaults = .standard) {
        self.root = root.standardizedFileURL
        self.defaults = defaults
    }

    var origin: URL? { port == 0 ? nil : URL(string: "http://127.0.0.1:\(port)") }
    var startURL: URL? { origin?.appendingPathComponent("index.html") }

    /// The port this app serves on, always the same one unless it has been overridden.
    var wanted: UInt16 {
        // An absent key reads as 0, and 0 converts to `UInt16` perfectly well — so the absence has
        // to be tested rather than coalesced, or every launch binds "any free port" instead.
        let override = defaults.integer(forKey: Self.portDefaultsKey)
        guard override > 0, let chosen = UInt16(exactly: override) else { return Self.defaultPort }
        return chosen
    }

    /// Bind the one port. Throws rather than moving — see the note above about offline.
    func start() throws {
        let ready = try Self.bind(to: wanted)

        lock.lock()
        descriptor = ready.fd
        port = ready.port
        lock.unlock()

        let root = self.root
        Thread.detachNewThread { [weak self] in
            while true {
                let client = accept(ready.fd, nil, nil)
                if client < 0 {
                    // `stop()` closed the socket, or the process is going away.
                    if self == nil || errno != EINTR { return }
                    continue
                }
                DispatchQueue.global(qos: .userInitiated).async {
                    Self.answer(client, root: root)
                }
            }
        }
    }

    func stop() {
        lock.lock()
        let held = descriptor
        descriptor = -1
        lock.unlock()
        if held >= 0 { close(held) }
    }

    deinit { stop() }

    private static func bind(to wanted: UInt16) throws -> (fd: Int32, port: UInt16) {
        let fd = socket(AF_INET, SOCK_STREAM, 0)
        guard fd >= 0 else { throw UpdateFailure.message("The interface server could not open a socket.") }
        var reuse: Int32 = 1
        setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &reuse, socklen_t(MemoryLayout<Int32>.size))

        var address = sockaddr_in()
        address.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        address.sin_family = sa_family_t(AF_INET)
        address.sin_port = wanted.bigEndian
        address.sin_addr.s_addr = inet_addr("127.0.0.1")

        let bound = withUnsafePointer(to: &address) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        guard bound == 0, listen(fd, 32) == 0 else {
            close(fd)
            throw UpdateFailure.message(
                "Another program is using port \(wanted) on this computer, which is where Acervo "
                + "serves its own interface. Quit that program and reopen Acervo, or set "
                + "AcervoInterfacePort to a free port."
            )
        }

        var actual = sockaddr_in()
        var length = socklen_t(MemoryLayout<sockaddr_in>.size)
        withUnsafeMutablePointer(to: &actual) {
            _ = $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { getsockname(fd, $0, &length) }
        }
        let assigned = UInt16(bigEndian: actual.sin_port)
        guard assigned != 0 else {
            close(fd)
            throw UpdateFailure.message("The interface server could not learn its own port.")
        }
        return (fd, assigned)
    }

    private static func answer(_ client: Int32, root: URL) {
        defer { close(client) }
        var request = Data()
        var buffer = [UInt8](repeating: 0, count: 4096)
        // The head is all that is read: this serves static files and has no body to consume.
        while request.count < 16 * 1024 {
            let read = recv(client, &buffer, buffer.count, 0)
            if read <= 0 { break }
            request.append(contentsOf: buffer[0..<read])
            if request.range(of: Data("\r\n\r\n".utf8)) != nil { break }
        }
        guard let target = requestedPath(request) else { return }
        var payload = response(for: target, root: root)
        payload.withUnsafeBytes { bytes in
            var sent = 0
            while sent < bytes.count {
                let wrote = send(client, bytes.baseAddress!.advanced(by: sent), bytes.count - sent, 0)
                if wrote <= 0 { return }
                sent += wrote
            }
        }
    }

    /// The path out of a request line, or nothing. Only `GET` is answered; the interface is static.
    static func requestedPath(_ data: Data) -> String? {
        guard let head = String(data: data.prefix(8 * 1024), encoding: .utf8),
              let line = head.split(separator: "\r\n", maxSplits: 1).first else { return nil }
        let parts = line.split(separator: " ")
        guard parts.count >= 2, parts[0] == "GET" else { return nil }
        return String(parts[1].split(separator: "?").first ?? "/")
    }

    func response(for target: String) -> Data { Self.response(for: target, root: root) }

    static func response(for target: String, root: URL) -> Data {
        guard let file = resolve(target, root: root) else {
            return head(status: "404 Not Found", type: "text/plain; charset=utf-8", length: 0)
        }
        guard let body = try? Data(contentsOf: file) else {
            return head(status: "500 Internal Server Error", type: "text/plain; charset=utf-8", length: 0)
        }
        var answer = head(
            status: "200 OK",
            type: WebInterfaceSchemeHandler.contentType(for: file.pathExtension),
            length: body.count
        )
        answer.append(body)
        return answer
    }

    private static func head(status: String, type: String, length: Int) -> Data {
        Data([
            "HTTP/1.1 \(status)",
            "Content-Type: \(type)",
            "Content-Length: \(length)",
            "Cache-Control: no-cache",
            "Connection: close",
            "",
            ""
        ].joined(separator: "\r\n").utf8)
    }

    func resolve(_ target: String) -> URL? { Self.resolve(target, root: root) }

    /// The same containment rule the scheme handler has: nothing outside the bundled root, ever.
    static func resolve(_ target: String, root: URL) -> URL? {
        var path = target.removingPercentEncoding ?? target
        if path.isEmpty || path == "/" { path = "/index.html" }
        guard path.hasPrefix("/") else { return nil }
        let candidate = root.appendingPathComponent(String(path.dropFirst())).standardizedFileURL
        guard candidate.path == root.path || candidate.path.hasPrefix(root.path + "/"),
              FileManager.default.fileExists(atPath: candidate.path) else { return nil }
        return candidate
    }
}
