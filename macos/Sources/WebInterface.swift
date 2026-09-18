import AppKit
import Foundation
import WebKit

enum WebInterface {
    static let scheme = "acervo"
    static let host = "app"
    static let startURL = URL(string: "\(scheme)://\(host)/index.html")!

    static let startupDiagnostics = #"""
    (() => {
      const show = message => {
        const root = document.getElementById('root');
        if (!root) return;
        root.innerHTML = `<main style="max-width:680px;margin:80px auto;padding:32px;font:15px -apple-system;color:#071a38"><h1 style="font:600 32px Georgia,serif">Acervo could not open</h1><p>${String(message)}</p><p>Please quit and reopen the app.</p></main>`;
      };
      window.addEventListener('error', event => show(event.message || 'The interface failed to start.'));
      window.addEventListener('unhandledrejection', event => show(event.reason?.message || event.reason || 'The interface failed to start.'));
    })();
    """#

    static func bundledInterfaceDirectory() -> URL? {
        if let nested = Bundle.main.url(forResource: "index", withExtension: "html", subdirectory: "dist") {
            return nested.deletingLastPathComponent()
        }
        return Bundle.main.url(forResource: "index", withExtension: "html")?.deletingLastPathComponent()
    }
}

/// The identifiers WebKit gives the navigation items in its own context menu.
///
/// Matched by raw value rather than through WebKit's constants, which import into Swift awkwardly;
/// these strings are the values those constants hold.
private let navigationMenuItems: Set<String> = [
    "WKMenuItemIdentifierReload",
    "WKMenuItemIdentifierGoBack",
    "WKMenuItemIdentifierGoForward",
]

/// Take WebKit's navigation items out of a context menu.
///
/// Acervo has no routing: the open word, the chosen vocabulary and the search are state in one
/// React tree, so reloading or going back does not return you to where you were — it drops you on
/// the default list, having thrown away what you were reading. These three are the only items in
/// that menu that navigate; Copy, Look Up, Services and Inspect Element are untouched.
///
/// Separators left leading or doubled by the removal go too, or the menu opens with a rule above
/// everything.
func pruneNavigationItems(from menu: NSMenu) {
    for item in menu.items where navigationMenuItems.contains(item.identifier?.rawValue ?? "") {
        menu.removeItem(item)
    }
    while let first = menu.items.first, first.isSeparatorItem {
        menu.removeItem(first)
    }
    while let last = menu.items.last, last.isSeparatorItem {
        menu.removeItem(last)
    }
    var index = menu.items.count - 1
    while index > 0 {
        if menu.items[index].isSeparatorItem, menu.items[index - 1].isSeparatorItem {
            menu.removeItem(at: index)
        }
        index -= 1
    }
}

/// The web view Acervo runs in, which is an ordinary `WKWebView` apart from its context menu.
///
/// A subclass only because `willOpenMenu(_:with:)` is an `NSView` method: there is no delegate
/// callback for the macOS context menu the way there is on iOS.
final class AcervoWebView: WKWebView {
    override func willOpenMenu(_ menu: NSMenu, with event: NSEvent) {
        super.willOpenMenu(menu, with: event)
        pruneNavigationItems(from: menu)
    }
}

final class WebInterfaceSchemeHandler: NSObject, WKURLSchemeHandler {
    private let root: URL

    init(root: URL) { self.root = root.standardizedFileURL }

    func webView(_ webView: WKWebView, start task: WKURLSchemeTask) {
        guard let url = task.request.url, let file = resolve(url) else {
            task.didFailWithError(UpdateFailure.message("The bundled web interface is missing."))
            return
        }
        do {
            let data = try Data(contentsOf: file)
            let response = HTTPURLResponse(
                url: url,
                statusCode: 200,
                httpVersion: "HTTP/1.1",
                headerFields: [
                    "Content-Type": Self.contentType(for: file.pathExtension),
                    "Content-Length": String(data.count),
                    "Cache-Control": "no-cache"
                ]
            )!
            task.didReceive(response)
            task.didReceive(data)
            task.didFinish()
        } catch { task.didFailWithError(error) }
    }

    func webView(_ webView: WKWebView, stop task: WKURLSchemeTask) {}
    func resolveForTesting(_ url: URL) -> URL? { resolve(url) }

    private func resolve(_ url: URL) -> URL? {
        guard url.scheme == WebInterface.scheme, url.host == WebInterface.host else { return nil }
        var path = url.path
        if path.isEmpty || path == "/" { path = "/index.html" }
        let candidate = root.appendingPathComponent(String(path.dropFirst())).standardizedFileURL
        guard candidate.path == root.path || candidate.path.hasPrefix(root.path + "/"),
              FileManager.default.fileExists(atPath: candidate.path) else { return nil }
        return candidate
    }

    static func contentType(for extensionName: String) -> String {
        switch extensionName.lowercased() {
        case "html": "text/html; charset=utf-8"
        case "js": "text/javascript; charset=utf-8"
        case "css": "text/css; charset=utf-8"
        case "json", "webmanifest": "application/json; charset=utf-8"
        case "svg": "image/svg+xml"
        case "png": "image/png"
        case "ico": "image/x-icon"
        case "woff": "font/woff"
        case "woff2": "font/woff2"
        default: "application/octet-stream"
        }
    }
}
