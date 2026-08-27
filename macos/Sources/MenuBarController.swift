import AppKit

enum StatusClickAction: Equatable {
    case openWindow
    case showMenu
}

func statusClickAction(for type: NSEvent.EventType?) -> StatusClickAction {
    type == .rightMouseUp ? .showMenu : .openWindow
}

@MainActor
final class MenuBarController: NSObject {
    private let statusItem = NSStatusBar.system.statusItem(withLength: 34)
    private let openWindow: () -> Void
    private var updateAvailable = false

    init(openWindow: @escaping () -> Void) {
        self.openWindow = openWindow
        super.init()
        guard let button = statusItem.button else { return }
        button.target = self
        button.action = #selector(clicked)
        button.sendAction(on: [.leftMouseUp, .rightMouseUp])
        button.toolTip = "Acervo"
        refreshImage()
    }

    func setUpdateAvailable(_ release: MacRelease?) {
        updateAvailable = release != nil
        refreshImage()
    }

    @objc private func clicked() {
        switch statusClickAction(for: NSApp.currentEvent?.type) {
        case .openWindow:
            openWindow()
        case .showMenu:
            let menu = NSMenu()
            menu.addItem(withTitle: "Quit Acervo", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
            statusItem.menu = menu
            statusItem.button?.performClick(nil)
            statusItem.menu = nil
        }
    }

    private func refreshImage() {
        let image = NSImage(
            systemSymbolName: "character.book.closed.fill",
            accessibilityDescription: updateAvailable ? "Acervo; an update is available" : "Acervo"
        )!
        image.isTemplate = true
        statusItem.button?.image = image
    }
}
