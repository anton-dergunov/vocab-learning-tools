import SwiftUI

struct SettingsView: View {
    @ObservedObject var updates: UpdateService
    @FocusState private var serverFieldIsFocused: Bool
    @State private var serverURL: String
    @State private var serverMessage: String?
    @State private var pendingSave: Task<Void, Never>?

    let checkNow: () -> Void
    let installUpdate: () -> Void
    let restartNow: () -> Void

    init(
        updates: UpdateService,
        checkNow: @escaping () -> Void,
        installUpdate: @escaping () -> Void,
        restartNow: @escaping () -> Void
    ) {
        self.updates = updates
        self.checkNow = checkNow
        self.installUpdate = installUpdate
        self.restartNow = restartNow
        _serverURL = State(initialValue: updates.storedServerURL)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 30) {
                serverSection
                updatesSection
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(28)
        }
        .frame(minWidth: 500, minHeight: 360)
        .onDisappear {
            pendingSave?.cancel()
            saveServerURL(normalizeField: false)
        }
    }

    private var serverSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Server")
                .font(.title3.weight(.semibold))

            TextField("https://acervo.example.com", text: $serverURL)
                .textFieldStyle(.roundedBorder)
                .controlSize(.large)
                .focused($serverFieldIsFocused)
                .accessibilityLabel("Acervo server address")
                .onSubmit { saveServerURL() }
                .onChange(of: serverURL) { _, _ in scheduleSave() }
                .onChange(of: serverFieldIsFocused) { wasFocused, isFocused in
                    if wasFocused, !isFocused { saveServerURL() }
                }

            Text("Use the same HTTPS address that opens Acervo in your browser. This Mac uses it to find and download updates.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            if let serverMessage {
                Text(serverMessage)
                    .font(.caption)
                    .foregroundStyle(.red)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var updatesSection: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Updates")
                .font(.title3.weight(.semibold))

            Toggle("Check for updates automatically", isOn: Binding(
                get: { updates.automaticChecks }, set: { updates.automaticChecks = $0 }
            ))
            Toggle("Install updates automatically", isOn: Binding(
                get: { updates.automaticInstall }, set: { updates.automaticInstall = $0 }
            ))
            .disabled(!updates.automaticChecks)

            Text("Updates install quietly in the background and start the next time Acervo opens. Acervo never restarts itself.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            Divider()

            HStack(spacing: 10) {
                Button(updates.state == .checking ? "Checking…" : "Check Now", action: checkNow)
                    .disabled(updates.isBusy || !updates.hasServerURL)
                status
            }

            Text("Version \(AppVersion.label)")
                .font(.caption)
                .foregroundStyle(.secondary)
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
            if let pending = updates.pendingBuild {
                Text("Build \(pending) starts when Acervo restarts").font(.caption).foregroundStyle(.orange)
                Button("Restart Now", action: restartNow).buttonStyle(.borderedProminent).controlSize(.small)
            } else if let release = updates.available {
                Text("Build \(release.build) is available").font(.caption).foregroundStyle(.orange)
                // The label names the restart, so nothing has to confirm it afterwards.
                Button("Update and Restart", action: installUpdate).buttonStyle(.borderedProminent).controlSize(.small)
            } else if let message = updates.statusMessage {
                Text(message).font(.caption).foregroundStyle(.secondary)
            } else if let date = updates.lastCheck {
                Text("Last checked: \(date.formatted(date: .abbreviated, time: .shortened))")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private func saveServerURL(normalizeField: Bool = true) {
        pendingSave?.cancel()
        guard serverURL != updates.storedServerURL else { return }
        do {
            try updates.saveServerURL(serverURL)
            if normalizeField { serverURL = updates.storedServerURL }
            serverMessage = nil
        } catch {
            guard normalizeField else { return }
            if case let UpdateFailure.message(message) = error { serverMessage = message }
            else { serverMessage = error.localizedDescription }
        }
    }

    private func scheduleSave() {
        serverMessage = nil
        pendingSave?.cancel()
        pendingSave = Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(500))
            guard !Task.isCancelled else { return }
            saveServerURL(normalizeField: false)
        }
    }
}
