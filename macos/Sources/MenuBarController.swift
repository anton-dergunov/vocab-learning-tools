import AppKit

enum StatusClickAction: Equatable {
    case openWindow
    case showMenu
}

func statusClickAction(for type: NSEvent.EventType?) -> StatusClickAction {
    type == .rightMouseUp ? .showMenu : .openWindow
}

/// The canvas is wider than the book so the update mark has space of its own. The book keeps the
/// leading `bookBoxWidth` points it has always had, so neither it nor the cut-out letters move.
private let bookBoxWidth: CGFloat = 20

func makeMenuBarIcon(accessibilityDescription: String, updateAvailable: Bool = false) -> NSImage {
    let canvasSize = NSSize(width: 27, height: 18)
    let symbolConfiguration = NSImage.SymbolConfiguration(pointSize: 18, weight: .regular)
    let book = NSImage(
        systemSymbolName: "book.fill",
        accessibilityDescription: nil
    )!.withSymbolConfiguration(symbolConfiguration)!

    let image = NSImage(size: canvasSize, flipped: false) { _ in
        let bookSize = book.size
        let bookOrigin = NSPoint(
            x: (bookBoxWidth - bookSize.width) / 2,
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
            .font: NSFont.systemFont(ofSize: 6.7, weight: .heavy),
            .foregroundColor: NSColor.black,
        ]

        func cutOut(_ letter: String, centeredAtX centerX: CGFloat) {
            let glyph = NSAttributedString(string: letter, attributes: attributes)
            let glyphSize = glyph.size()
            glyph.draw(at: NSPoint(
                x: centerX - glyphSize.width / 2,
                y: 5.3
            ))
        }

        // A half-point shift is one physical pixel on a Retina menu bar.
        cutOut("A", centeredAtX: 5)
        cutOut("Ñ", centeredAtX: 15)
        context.restoreGState()

        if updateAvailable {
            // The mark sits in reserved space rather than on the book, which is what lets it be
            // large enough to read at menu-bar size. The cleared ring is insurance against the
            // glyph's bounds spilling past the book box.
            NSGraphicsContext.current?.cgContext.setBlendMode(.clear)
            NSBezierPath(ovalIn: NSRect(x: 21, y: 11, width: 6, height: 6)).fill()
            NSGraphicsContext.current?.cgContext.setBlendMode(.normal)
            NSColor.labelColor.setFill()
            NSBezierPath(ovalIn: NSRect(x: 22, y: 12, width: 4, height: 4)).fill()
        }
        return true
    }
    image.isTemplate = true
    image.accessibilityDescription = accessibilityDescription
    return image
}

/// A waiting update earns a line in this menu, because the mark beside the book is deliberately the
/// only thing that announces it.
@MainActor
func makeStatusMenu(mark: UpdateMark?, target: AnyObject?) -> NSMenu {
    let menu = NSMenu()
    switch mark {
    case .pendingRestart:
        menu.addItem(
            withTitle: "Restart to Update", action: #selector(MenuBarController.restartToUpdate), keyEquivalent: ""
        )
        menu.addItem(.separator())
    case .available:
        menu.addItem(
            withTitle: "Check for Updates…", action: #selector(MenuBarController.checkForUpdates), keyEquivalent: ""
        )
        menu.addItem(.separator())
    case nil:
        break
    }
    menu.addItem(withTitle: "Quit Acervo", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
    for item in menu.items where item.action != #selector(NSApplication.terminate(_:)) {
        item.target = target
    }
    return menu
}

@MainActor
final class MenuBarController: NSObject {
    // A constant width, wide enough for the mark, so the icon never shifts when one appears.
    private let statusItem = NSStatusBar.system.statusItem(withLength: 33)
    private let openWindow: () -> Void
    private let restartToUpdateAction: () -> Void
    private let checkForUpdatesAction: () -> Void
    private var mark: UpdateMark?

    init(
        openWindow: @escaping () -> Void,
        restartToUpdate: @escaping () -> Void,
        checkForUpdates: @escaping () -> Void
    ) {
        self.openWindow = openWindow
        self.restartToUpdateAction = restartToUpdate
        self.checkForUpdatesAction = checkForUpdates
        super.init()
        guard let button = statusItem.button else { return }
        button.target = self
        button.action = #selector(clicked)
        button.sendAction(on: [.leftMouseUp, .rightMouseUp])
        refreshImage()
    }

    func setUpdateMark(_ mark: UpdateMark?) {
        self.mark = mark
        refreshImage()
    }

    @objc fileprivate func restartToUpdate() { restartToUpdateAction() }
    @objc fileprivate func checkForUpdates() { checkForUpdatesAction() }

    @objc private func clicked() {
        switch statusClickAction(for: NSApp.currentEvent?.type) {
        case .openWindow:
            openWindow()
        case .showMenu:
            statusItem.menu = makeStatusMenu(mark: mark, target: self)
            statusItem.button?.performClick(nil)
            statusItem.menu = nil
        }
    }

    private func refreshImage() {
        let description = switch mark {
        case .pendingRestart: "Acervo; an update is ready and starts when Acervo restarts"
        case .available: "Acervo; an update is available"
        case nil: "Acervo"
        }
        statusItem.button?.image = makeMenuBarIcon(
            accessibilityDescription: description,
            updateAvailable: mark != nil
        )
        statusItem.button?.imageScaling = .scaleNone
        statusItem.button?.toolTip = description
    }
}
