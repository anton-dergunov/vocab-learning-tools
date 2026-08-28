import AppKit
import SwiftUI

/// A native field keeps the standard macOS editing responder chain intact, including Command-V
/// and the contextual Paste command. The adjacent Paste button also makes the expected action
/// available when a password manager or remote desktop client intercepts the shortcut.
struct ServerAddressField: NSViewRepresentable {
    @Binding var text: String
    let onSubmit: () -> Void

    func makeCoordinator() -> Coordinator { Coordinator(text: $text, onSubmit: onSubmit) }

    func makeNSView(context: Context) -> NSTextField {
        let field = NSTextField()
        field.placeholderString = "https://acervo.example.com"
        field.font = .systemFont(ofSize: NSFont.systemFontSize)
        field.delegate = context.coordinator
        field.focusRingType = .default
        field.lineBreakMode = .byTruncatingMiddle
        field.setAccessibilityLabel("Acervo server address")
        return field
    }

    func updateNSView(_ field: NSTextField, context: Context) {
        if field.stringValue != text { field.stringValue = text }
    }

    final class Coordinator: NSObject, NSTextFieldDelegate {
        @Binding private var text: String
        private let onSubmit: () -> Void

        init(text: Binding<String>, onSubmit: @escaping () -> Void) {
            _text = text
            self.onSubmit = onSubmit
        }

        func controlTextDidChange(_ notification: Notification) {
            guard let field = notification.object as? NSTextField else { return }
            text = field.stringValue
        }

        func control(_ control: NSControl, textView: NSTextView, doCommandBy commandSelector: Selector) -> Bool {
            if commandSelector == #selector(NSResponder.insertNewline(_:)) {
                onSubmit()
                return true
            }
            return false
        }
    }
}

struct SettingsView: View {
    @ObservedObject var updates: UpdateService
    @State private var serverURL: String
    @State private var serverMessage: String?

    let checkNow: () -> Void
    let installUpdate: () -> Void

    init(updates: UpdateService, checkNow: @escaping () -> Void, installUpdate: @escaping () -> Void) {
        self.updates = updates
        self.checkNow = checkNow
        self.installUpdate = installUpdate
        _serverURL = State(initialValue: updates.storedServerURL)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                serverSection
                updatesSection
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(28)
        }
        .frame(minWidth: 600, minHeight: 430)
    }

    private var serverSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Server").font(.title3.weight(.semibold))
            VStack(alignment: .leading, spacing: 10) {
                Text("Server address").font(.headline)
                HStack(spacing: 8) {
                    ServerAddressField(text: $serverURL, onSubmit: save)
                        .frame(maxWidth: .infinity, minHeight: 28)
                    Button("Paste", action: pasteServerAddress)
                }
                .onChange(of: serverURL) { _, _ in serverMessage = nil }

                Text("Use the same HTTPS address that opens Acervo in your browser. This Mac uses it to find and download updates.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)

                HStack(spacing: 10) {
                    Button("Save", action: save)
                        .disabled(serverURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    if let serverMessage {
                        Text(serverMessage)
                            .font(.caption)
                            .foregroundStyle(serverMessage == "Server saved." ? Color.secondary : Color.red)
                            .lineLimit(2)
                    }
                }
            }
            .padding(18)
            .background(.quaternary, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        }
    }

    private var updatesSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Updates").font(.title3.weight(.semibold))
            VStack(alignment: .leading, spacing: 14) {
                Toggle("Check for updates automatically", isOn: Binding(
                    get: { updates.automaticChecks }, set: { updates.automaticChecks = $0 }
                ))
                Toggle("Install updates automatically", isOn: Binding(
                    get: { updates.automaticInstall }, set: { updates.automaticInstall = $0 }
                ))
                .disabled(!updates.automaticChecks)

                Divider()

                HStack(spacing: 10) {
                    Button(updates.state == .checking ? "Checking…" : "Check Now", action: checkNow)
                        .disabled(updates.isBusy || !updates.hasServerURL)
                    status
                }
                Text("Version \(AppVersion.label)").font(.caption).foregroundStyle(.secondary)
            }
            .padding(18)
            .background(.quaternary, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        }
    }

    @ViewBuilder
    private var status: some View {
        switch updates.state {
        case .downloading(let fraction):
            ProgressView(value: fraction).frame(width: 90)
            Text("Downloading \(Int(fraction * 100))%").font(.caption).foregroundStyle(.secondary)
        case .installing:
            ProgressView().controlSize(.small)
            Text("Installing…").font(.caption).foregroundStyle(.secondary)
        case .failed(let message):
            Text(message).font(.caption).foregroundStyle(.red).lineLimit(3)
        case .checking:
            ProgressView().controlSize(.small)
        case .idle:
            if let release = updates.available {
                Text("Build \(release.build) is available").font(.caption).foregroundStyle(.orange)
                Button("Update Now", action: installUpdate).buttonStyle(.borderedProminent).controlSize(.small)
            } else if let message = updates.statusMessage {
                Text(message).font(.caption).foregroundStyle(.secondary)
            } else if let date = updates.lastCheck {
                Text("Last checked: \(date.formatted(date: .abbreviated, time: .shortened))")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private func save() {
        do {
            try updates.saveServerURL(serverURL)
            serverURL = updates.storedServerURL
            serverMessage = "Server saved."
        } catch {
            if case let UpdateFailure.message(message) = error { serverMessage = message }
            else { serverMessage = error.localizedDescription }
        }
    }

    private func pasteServerAddress() {
        guard let value = NSPasteboard.general.string(forType: .string) else {
            serverMessage = "The clipboard does not contain text."
            return
        }
        serverURL = value
    }
}
