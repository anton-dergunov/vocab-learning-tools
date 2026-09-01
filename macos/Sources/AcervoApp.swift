import AppKit
import WebKit

@MainActor
func makeEditMenu() -> NSMenu {
    let menu = NSMenu(title: "Edit")
    menu.addItem(withTitle: "Undo", action: Selector(("undo:")), keyEquivalent: "z")
    let redoItem = menu.addItem(withTitle: "Redo", action: Selector(("redo:")), keyEquivalent: "z")
    redoItem.keyEquivalentModifierMask = [.command, .shift]
    menu.addItem(.separator())
    menu.addItem(withTitle: "Cut", action: Selector(("cut:")), keyEquivalent: "x")
    menu.addItem(withTitle: "Copy", action: Selector(("copy:")), keyEquivalent: "c")
    menu.addItem(withTitle: "Paste", action: Selector(("paste:")), keyEquivalent: "v")
    menu.addItem(withTitle: "Select All", action: Selector(("selectAll:")), keyEquivalent: "a")
    return menu
}

/// The vocabulary itself is the web app's, so these items open the surface that already owns each
/// action rather than reimplementing it natively. A menu, not a second implementation.
@MainActor
func makeVocabularyMenu(target: AnyObject?) -> NSMenu {
    let menu = NSMenu(title: "Vocabulary")
    let export = menu.addItem(
        withTitle: "Export Vocabulary…", action: #selector(AppDelegate.exportVocabulary), keyEquivalent: "e"
    )
    export.keyEquivalentModifierMask = [.command, .shift]
    let load = menu.addItem(
        withTitle: "Import Vocabulary…", action: #selector(AppDelegate.importVocabulary), keyEquivalent: "i"
    )
    load.keyEquivalentModifierMask = [.command, .shift]
    menu.addItem(.separator())
    // No shortcut on deletion: it is the one action re-syncing cannot undo.
    menu.addItem(
        withTitle: "Delete All Vocabulary…", action: #selector(AppDelegate.deleteVocabulary), keyEquivalent: ""
    )
    for item in menu.items where item.action != nil { item.target = target }
    return menu
}

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
final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
    private var window: NSWindow!
    private var webView: WKWebView!
    private let sessionBridge = SessionBridge()
    private var menuBar: MenuBarController!
    private let updates = UpdateService()
    private let settings = SettingsWindowController()
    /// Where each in-flight download is going, so the finished file can be revealed rather than lost.
    private var downloadDestinations: [ObjectIdentifier: URL] = [:]

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
        configuration.userContentController.addScriptMessageHandler(sessionBridge, contentWorld: .page, name: "acervo")
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
        // Without this the file input for importing a bundle opens no panel at all, silently.
        webView.uiDelegate = self

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
        // Exporting hands the page a blob to save. Allowing it instead of downloading it drops the
        // file on the floor with no error anywhere.
        if navigationAction.shouldPerformDownload {
            decisionHandler(.download)
        } else if navigationAction.navigationType == .linkActivated,
           let url = navigationAction.request.url,
           ["http", "https"].contains(url.scheme?.lowercased() ?? "") {
            NSWorkspace.shared.open(url)
            decisionHandler(.cancel)
        } else { decisionHandler(.allow) }
    }

    // MARK: - Saving and choosing files

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
        download.delegate = self
    }

    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) {
        download.delegate = self
    }

    func download(
        _ download: WKDownload,
        decideDestinationUsing response: URLResponse,
        suggestedFilename: String,
        completionHandler: @escaping @MainActor @Sendable (URL?) -> Void
    ) {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = suggestedFilename
        panel.canCreateDirectories = true
        showWindow()
        panel.beginSheetModal(for: window) { [weak self] outcome in
            guard outcome == .OK, let url = panel.url else {
                completionHandler(nil)
                return
            }
            // The panel already asked about replacing; WKDownload refuses a destination that exists.
            try? FileManager.default.removeItem(at: url)
            self?.downloadDestinations[ObjectIdentifier(download)] = url
            completionHandler(url)
        }
    }

    func downloadDidFinish(_ download: WKDownload) {
        if let url = downloadDestinations.removeValue(forKey: ObjectIdentifier(download)) {
            NSWorkspace.shared.activateFileViewerSelecting([url])
        }
    }

    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
        downloadDestinations.removeValue(forKey: ObjectIdentifier(download))
        let alert = NSAlert()
        alert.messageText = "The export could not be saved"
        alert.informativeText = error.localizedDescription
        alert.runModal()
    }

    func webView(
        _ webView: WKWebView,
        runOpenPanelWith parameters: WKOpenPanelParameters,
        initiatedByFrame frame: WKFrameInfo,
        completionHandler: @escaping @MainActor @Sendable ([URL]?) -> Void
    ) {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = parameters.allowsDirectories
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.beginSheetModal(for: window) { outcome in
            completionHandler(outcome == .OK ? panel.urls : nil)
        }
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

        let editItem = NSMenuItem()
        editItem.submenu = makeEditMenu()
        main.addItem(editItem)

        let vocabularyItem = NSMenuItem()
        vocabularyItem.submenu = makeVocabularyMenu(target: self)
        main.addItem(vocabularyItem)

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

    @objc fileprivate func exportVocabulary() { open("export") }
    @objc fileprivate func importVocabulary() { open("import") }
    @objc fileprivate func deleteVocabulary() { open("delete") }

    /// Every confirmation, and every write, stays on the side that owns the vocabulary.
    private func open(_ command: String) {
        showWindow()
        webView.evaluateJavaScript("window.acervo?.command(\"\(command)\")")
    }

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
