import AppKit
import WebKit

@main
struct AcervoApplication {
    static func main() {
        let application = NSApplication.shared
        let delegate = AppDelegate()
        application.delegate = delegate
        application.run()
        withExtendedLifetime(delegate) {}
    }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate {
    private var window: NSWindow!
    private var webView: WKWebView!
    private let nativeMarker = NativeMarker()
    private var menuBar: MenuBarController!
    private let updates = UpdateService()
    private let settings = SettingsWindowController()

    func applicationDidFinishLaunching(_ notification: Notification) {
        installMainMenu()
        createWindow()
        menuBar = MenuBarController(openWindow: { [weak self] in self?.showWindow() })
        showWindow()

        updates.onAvailabilityChanged = { [weak self] release in self?.menuBar.setUpdateAvailable(release) }
        updates.confirmRestart = { [weak self] release in self?.confirmRestart(for: release) ?? true }
        updates.start()

        if !updates.hasServerURL {
            DispatchQueue.main.async { [weak self] in self?.showSettings() }
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showWindow()
        return true
    }

    func windowWillClose(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
    }

    private func createWindow() {
        let configuration = WKWebViewConfiguration()
        configuration.defaultWebpagePreferences.allowsContentJavaScript = true
        configuration.userContentController.add(nativeMarker, name: "acervo")
        configuration.userContentController.addUserScript(WKUserScript(
            source: WebInterface.startupDiagnostics,
            injectionTime: .atDocumentStart,
            forMainFrameOnly: true
        ))
        if let interfaceRoot = WebInterface.bundledInterfaceDirectory() {
            configuration.setURLSchemeHandler(WebInterfaceSchemeHandler(root: interfaceRoot), forURLScheme: WebInterface.scheme)
        }
        webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = self

        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 960, height: 680),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = "Acervo"
        window.minSize = NSSize(width: 560, height: 420)
        window.contentView = webView
        window.delegate = self
        window.isReleasedWhenClosed = false
        window.setFrameAutosaveName("AcervoMainWindow")
        window.center()

        if WebInterface.bundledInterfaceDirectory() != nil {
            webView.load(URLRequest(url: WebInterface.startURL))
        } else {
            showLoadError("The bundled web interface is missing. Rebuild the application.")
        }
    }

    private func showWindow() {
        NSApp.setActivationPolicy(.regular)
        window?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func webView(
        _ webView: WKWebView,
        decidePolicyFor navigationAction: WKNavigationAction,
        decisionHandler: @escaping @MainActor @Sendable (WKNavigationActionPolicy) -> Void
    ) {
        if navigationAction.navigationType == .linkActivated,
           let url = navigationAction.request.url,
           ["http", "https"].contains(url.scheme?.lowercased() ?? "") {
            NSWorkspace.shared.open(url)
            decisionHandler(.cancel)
        } else { decisionHandler(.allow) }
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        showLoadError(error.localizedDescription)
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        showLoadError(error.localizedDescription)
    }

    private func showLoadError(_ message: String) {
        let escaped = message
            .replacingOccurrences(of: "&", with: "&amp;")
            .replacingOccurrences(of: "<", with: "&lt;")
        webView.loadHTMLString("<main style='font:16px -apple-system;padding:48px'><h1>Unable to open Acervo</h1><p>\(escaped)</p></main>", baseURL: nil)
    }

    private func installMainMenu() {
        let main = NSMenu()
        let appItem = NSMenuItem()
        let appMenu = NSMenu()
        let aboutItem = appMenu.addItem(withTitle: "About Acervo", action: #selector(showAbout), keyEquivalent: "")
        aboutItem.target = self
        let updateItem = appMenu.addItem(withTitle: "Check for Updates…", action: #selector(checkForUpdates), keyEquivalent: "")
        updateItem.target = self
        appMenu.addItem(.separator())
        let settingsItem = appMenu.addItem(withTitle: "Settings…", action: #selector(showSettingsMenu), keyEquivalent: ",")
        settingsItem.target = self
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Quit Acervo", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu
        main.addItem(appItem)

        let windowItem = NSMenuItem()
        let windowMenu = NSMenu(title: "Window")
        windowMenu.addItem(withTitle: "Minimize", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        windowMenu.addItem(withTitle: "Close", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        windowItem.submenu = windowMenu
        main.addItem(windowItem)
        NSApp.mainMenu = main
        NSApp.windowsMenu = windowMenu
    }

    @objc private func showAbout() {
        NSApp.orderFrontStandardAboutPanel(options: [
            .applicationName: "Acervo",
            .applicationVersion: AppVersion.name,
            .version: AppVersion.build
        ])
    }

    @objc private func checkForUpdates() {
        showSettings()
        Task { [weak self] in await self?.updates.check(force: true) }
    }

    @objc private func showSettingsMenu() { showSettings() }

    private func showSettings() {
        settings.show(
            updates: updates,
            checkNow: { [weak self] in Task { await self?.updates.check(force: true) } },
            installUpdate: { [weak self] in Task { await self?.updates.install() } }
        )
    }

    private func confirmRestart(for release: MacRelease) -> Bool {
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
        let alert = NSAlert()
        alert.messageText = "Acervo has been updated"
        alert.informativeText = "Build \(release.build) is installed and starts the next time Acervo opens."
        alert.addButton(withTitle: "Restart Now")
        alert.addButton(withTitle: "Later")
        return alert.runModal() == .alertFirstButtonReturn
    }
}
