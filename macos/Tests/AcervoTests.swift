import CryptoKit
import WebKit
import XCTest
@testable import Acervo

final class NavigationProbe: NSObject, WKNavigationDelegate {
    let finished: XCTestExpectation
    init(_ finished: XCTestExpectation) { self.finished = finished }
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) { finished.fulfill() }
}

final class StubURLProtocol: URLProtocol {
    nonisolated(unsafe) static var body = Data()
    nonisolated(unsafe) static var ignoresRanges = false
    nonisolated(unsafe) static var rangesAsked: [String] = []

    static func reset() {
        body = Data()
        ignoresRanges = false
        rangesAsked = []
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func stopLoading() {}

    override func startLoading() {
        var payload = Self.body
        var status = 200
        if let header = request.value(forHTTPHeaderField: "Range") {
            Self.rangesAsked.append(header)
            if !Self.ignoresRanges, let range = Self.slice(header, of: Self.body.count) {
                payload = Self.body.subdata(in: range)
                status = 206
            }
        }
        let response = HTTPURLResponse(
            url: request.url!, statusCode: status, httpVersion: "HTTP/1.1", headerFields: nil
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: payload)
        client?.urlProtocolDidFinishLoading(self)
    }

    private static func slice(_ header: String, of count: Int) -> Range<Int>? {
        let numbers = header.replacingOccurrences(of: "bytes=", with: "").split(separator: "-")
        guard numbers.count == 2, let first = Int(numbers[0]), let last = Int(numbers[1]),
              first < count else { return nil }
        return first..<min(last + 1, count)
    }
}

final class AcervoTests: XCTestCase {
    func testReleaseComparisonUsesBuildStamp() {
        let release = MacRelease(version: "0.1.0", build: "202608271230", file: "a.zip", size: 1, sha256: "x", url: "/a.zip")
        XCTAssertTrue(release.isNewer(than: "202608271229"))
        XCTAssertFalse(release.isNewer(than: "202608271230"))
        XCTAssertFalse(release.isNewer(than: "202608271231"))
    }

    func testServerAddressRequiresSecurePublicOrigin() throws {
        XCTAssertEqual(try ServerAddress.normalize(" https://acervo.example.com/api/acervo/v1/ "), "https://acervo.example.com")
        XCTAssertEqual(try ServerAddress.normalize("http://localhost:27702/"), "http://localhost:27702")
        XCTAssertThrowsError(try ServerAddress.normalize("http://acervo.example.com"))
        XCTAssertThrowsError(try ServerAddress.normalize("https://user:secret@acervo.example.com"))
    }

    func testStatusClicksSeparateOpenAndContextMenu() {
        XCTAssertEqual(statusClickAction(for: .leftMouseUp), .openWindow)
        XCTAssertEqual(statusClickAction(for: .rightMouseUp), .showMenu)
        XCTAssertEqual(statusClickAction(for: nil), .openWindow)
    }

    @MainActor
    func testEditMenuProvidesStandardTextFieldShortcuts() throws {
        let menu = makeEditMenu()
        let expected = ["Cut": "x", "Copy": "c", "Paste": "v", "Select All": "a"]
        for (title, shortcut) in expected {
            let item = try XCTUnwrap(menu.item(withTitle: title))
            XCTAssertEqual(item.keyEquivalent, shortcut)
            XCTAssertEqual(item.keyEquivalentModifierMask, .command)
        }
        XCTAssertEqual(menu.item(withTitle: "Paste")?.action, Selector(("paste:")))
    }

    @MainActor
    func testMenuBarIconIsACompactTemplateImage() {
        let icon = makeMenuBarIcon(accessibilityDescription: "Acervo")
        XCTAssertEqual(icon.size, NSSize(width: 20, height: 18))
        XCTAssertTrue(icon.isTemplate)
        XCTAssertEqual(icon.accessibilityDescription, "Acervo")
        XCTAssertNotNil(icon.tiffRepresentation)
    }

    @MainActor
    func testMenuBarIconCanShowAnUpdateMark() {
        let icon = makeMenuBarIcon(
            accessibilityDescription: "Acervo; an update is available",
            updateAvailable: true
        )
        XCTAssertTrue(icon.isTemplate)
        XCTAssertEqual(icon.accessibilityDescription, "Acervo; an update is available")
        XCTAssertNotNil(icon.tiffRepresentation)
    }

    func testSchemeHandlerRefusesTraversalAndKnowsTypes() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try Data("ok".utf8).write(to: root.appendingPathComponent("index.html"))
        let handler = WebInterfaceSchemeHandler(root: root)
        XCTAssertNotNil(handler.resolveForTesting(URL(string: "acervo://app/index.html")!))
        XCTAssertNil(handler.resolveForTesting(URL(string: "acervo://app/../outside")!))
        XCTAssertEqual(WebInterfaceSchemeHandler.contentType(for: "js"), "text/javascript; charset=utf-8")
        XCTAssertEqual(WebInterfaceSchemeHandler.contentType(for: "webmanifest"), "application/json; charset=utf-8")
    }

    func testChecksumAndSizeAreVerified() throws {
        let file = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let data = Data("acervo".utf8)
        try data.write(to: file)
        defer { try? FileManager.default.removeItem(at: file) }
        let checksum = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        XCTAssertNoThrow(try UpdateService.verify(file, size: data.count, sha256: checksum))
        XCTAssertThrowsError(try UpdateService.verify(file, size: data.count + 1, sha256: checksum))
        XCTAssertThrowsError(try UpdateService.verify(file, size: data.count, sha256: String(repeating: "0", count: 64)))
    }

    @MainActor
    func testArchiveIsAssembledFromRangedChunks() async throws {
        defer { StubURLProtocol.reset() }
        let size = 1_048_576 * 2 + 500
        StubURLProtocol.body = Data((0..<size).map { UInt8($0 % 251) })
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [StubURLProtocol.self]
        let defaultsSuite = UUID().uuidString
        let defaults = UserDefaults(suiteName: defaultsSuite)!
        defer { defaults.removePersistentDomain(forName: defaultsSuite) }
        let updates = UpdateService(
            defaults: defaults,
            session: URLSession(configuration: configuration)
        )
        let url = try XCTUnwrap(URL(string: "https://acervo.example.com/api/acervo/downloads/Acervo.zip"))

        let file = try await updates.downloadForTesting(url, size: size)
        defer { try? FileManager.default.removeItem(at: file) }

        XCTAssertEqual(try Data(contentsOf: file), StubURLProtocol.body)
        XCTAssertEqual(StubURLProtocol.rangesAsked, [
            "bytes=0-1048575",
            "bytes=1048576-2097151",
            "bytes=2097152-2097651",
        ])
    }

    func testReleaseManifestEnvelopeDecodesAbsentAndPresentReleases() throws {
        let decoder = JSONDecoder()
        XCTAssertNil(try decoder.decode(MacRelease.Envelope.self, from: Data(#"{"data":null}"#.utf8)).data)
        let manifest = Data(#"{"data":{"version":"0.1.0","build":"202608270001","file":"Acervo.zip","size":42,"sha256":"abc","url":"/api/acervo/downloads/Acervo.zip"}}"#.utf8)
        let release = try decoder.decode(MacRelease.Envelope.self, from: manifest).data
        XCTAssertEqual(release?.build, "202608270001")
        XCTAssertEqual(release?.size, 42)
    }

    @MainActor
    func testBundledInterfaceRendersAndHasIndexedDB() async throws {
        guard let root = WebInterface.bundledInterfaceDirectory() else {
            return XCTFail("The test host did not bundle web/dist")
        }
        let defaultsSuite = "AcervoTests.WebInterface.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: defaultsSuite))
        addTeardownBlock { defaults.removePersistentDomain(forName: defaultsSuite) }
        let configuration = WKWebViewConfiguration()
        let bridge = SessionBridge(defaults: defaults)
        configuration.userContentController.addScriptMessageHandler(bridge, contentWorld: .page, name: "acervo")
        configuration.setURLSchemeHandler(WebInterfaceSchemeHandler(root: root), forURLScheme: WebInterface.scheme)
        let webView = WKWebView(frame: .init(x: 0, y: 0, width: 800, height: 600), configuration: configuration)
        let window = NSWindow(contentRect: webView.frame, styleMask: [.titled], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.contentView = webView
        window.orderFront(nil)
        addTeardownBlock { @MainActor in
            window.close()
            configuration.userContentController.removeScriptMessageHandler(forName: "acervo")
        }
        let loaded = expectation(description: "Acervo interface loaded")
        let probe = NavigationProbe(loaded)
        webView.navigationDelegate = probe
        webView.load(URLRequest(url: WebInterface.startURL))
        await fulfillment(of: [loaded], timeout: 10)
        try await Task.sleep(for: .milliseconds(500))
        let title = try await webView.evaluateJavaScript("document.querySelector('h1')?.textContent") as? String
        XCTAssertEqual(title, "Acervo")
        let signInField = try await webView.evaluateJavaScript(
            "document.querySelector('#serverUrl') ? true : false"
        ) as? Bool
        XCTAssertEqual(signInField, true, "The host must load the real interface, not a placeholder")
        let indexedDB = try await webView.callAsyncJavaScript(
            "return await new Promise(resolve => { const request = indexedDB.open('acervo-host-test'); request.onsuccess = () => { request.result.close(); resolve(true); }; request.onerror = () => resolve(false); });",
            arguments: [:],
            in: nil,
            contentWorld: .page
        ) as? Bool
        XCTAssertEqual(indexedDB, true)
        withExtendedLifetime((probe, bridge)) {}
    }
}
