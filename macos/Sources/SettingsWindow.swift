import AppKit
import SwiftUI

@MainActor
final class SettingsWindowController {
    private var window: NSWindow?

    func show(updates: UpdateService, checkNow: @escaping () -> Void, installUpdate: @escaping () -> Void) {
        NSApp.setActivationPolicy(.regular)
        if let window {
            window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }
        let controller = NSHostingController(rootView: SettingsView(
            updates: updates,
            checkNow: checkNow,
            installUpdate: installUpdate
        ))
        let window = NSWindow(contentViewController: controller)
        window.title = "Acervo Settings"
        window.styleMask = [.titled, .closable, .miniaturizable, .resizable]
        window.isReleasedWhenClosed = false
        window.contentMinSize = NSSize(width: 500, height: 360)
        window.setContentSize(NSSize(width: 580, height: 410))
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        self.window = window
    }
}
