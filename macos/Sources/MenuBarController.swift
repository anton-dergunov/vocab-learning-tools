import AppKit

enum StatusClickAction: Equatable {
    case openWindow
    case showMenu
}

func statusClickAction(for type: NSEvent.EventType?) -> StatusClickAction {
    type == .rightMouseUp ? .showMenu : .openWindow
}

func makeMenuBarIcon(accessibilityDescription: String) -> NSImage {
    let canvasSize = NSSize(width: 20, height: 18)
    let symbolConfiguration = NSImage.SymbolConfiguration(pointSize: 17, weight: .regular)
    let book = NSImage(
        systemSymbolName: "book.fill",
        accessibilityDescription: nil
    )!.withSymbolConfiguration(symbolConfiguration)!

    let image = NSImage(size: canvasSize, flipped: false) { _ in
        let bookSize = book.size
        let bookOrigin = NSPoint(
            x: (canvasSize.width - bookSize.width) / 2,
            y: (canvasSize.height - bookSize.height) / 2
        )
        book.draw(
            at: bookOrigin,
            from: .zero,
            operation: .sourceOver,
            fraction: 1
        )

        guard let context = NSGraphicsContext.current?.cgContext else { return false }
        context.saveGState()
        context.setBlendMode(.clear)
        context.setShouldAntialias(true)

        let attributes: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: 6.2, weight: .heavy),
            .foregroundColor: NSColor.black,
        ]

        func cutOut(_ letter: String, centeredAtX centerX: CGFloat) {
            let glyph = NSAttributedString(string: letter, attributes: attributes)
            let glyphSize = glyph.size()
            glyph.draw(at: NSPoint(
                x: centerX - glyphSize.width / 2,
                y: 5.6
            ))
        }

        cutOut("A", centeredAtX: 5.5)
        cutOut("Ñ", centeredAtX: 14.5)
        context.restoreGState()
        return true
    }
    image.isTemplate = true
    image.accessibilityDescription = accessibilityDescription
    return image
}

@MainActor
final class MenuBarController: NSObject {
    private let statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
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
        statusItem.button?.image = makeMenuBarIcon(
            accessibilityDescription: updateAvailable ? "Acervo; an update is available" : "Acervo"
        )
        statusItem.button?.imageScaling = .scaleNone
    }
}
