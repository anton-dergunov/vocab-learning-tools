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

final class NativeMarker: NSObject, WKScriptMessageHandler {
    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {}
}
