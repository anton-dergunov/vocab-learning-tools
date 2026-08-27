import SwiftUI

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
        Form {
            Section("Server") {
                VStack(alignment: .leading, spacing: 10) {
                    TextField(
                        "",
                        text: $serverURL,
                        prompt: Text("https://acervo.example.com")
                    )
                    .accessibilityLabel("Acervo server address")
                    .textFieldStyle(.roundedBorder)
                    .controlSize(.large)
                    .frame(maxWidth: .infinity)
                    .onSubmit(save)
                    .onChange(of: serverURL) { _, _ in serverMessage = nil }

                    Text("Use the same HTTPS address that opens Acervo in your browser. This Mac uses it to find and download updates.")
                        .font(.caption)
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
                .padding(.vertical, 2)
            }

            Section("Updates") {
                Toggle("Check for updates automatically", isOn: Binding(
                    get: { updates.automaticChecks }, set: { updates.automaticChecks = $0 }
                ))
                Toggle("Install updates automatically", isOn: Binding(
                    get: { updates.automaticInstall }, set: { updates.automaticInstall = $0 }
                ))
                .disabled(!updates.automaticChecks)

                HStack(spacing: 10) {
                    Button(updates.state == .checking ? "Checking…" : "Check Now", action: checkNow)
                        .disabled(updates.isBusy || !updates.hasServerURL)
                    status
                }
                Text("Version \(AppVersion.label)").font(.caption).foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
        .padding(12)
        .frame(minWidth: 540, minHeight: 390)
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
}
