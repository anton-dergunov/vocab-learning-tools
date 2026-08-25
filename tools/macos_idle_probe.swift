#!/usr/bin/env swift
// Diagnostic only: reports the public macOS signals proposed for a future
// image-generation LaunchAgent. It never opens a capture device or starts work.

import AVFoundation
import CoreAudio
import CoreGraphics
import Foundation
import IOKit.ps
import Darwin.Mach

struct Signal<Value: Encodable>: Encodable {
    let available: Bool
    let value: Value?
    let error: String?

    static func success(_ value: Value) -> Signal<Value> {
        Signal(available: true, value: value, error: nil)
    }

    static func failure(_ message: String) -> Signal<Value> {
        Signal(available: false, value: nil, error: message)
    }
}

struct MemorySnapshot: Encodable {
    let availableBytes: UInt64
    let physicalBytes: UInt64
    let availableRatio: Double
    let pressure: String
}

struct CaptureSnapshot: Encodable {
    let active: Bool
    let activeDevices: [String]
}

struct ProbeSnapshot: Encodable {
    let timestamp: String
    let idleSeconds: Signal<Double>
    let onACPower: Signal<Bool>
    let thermalState: Signal<String>
    let lowPowerMode: Signal<Bool>
    let memory: Signal<MemorySnapshot>
    let microphoneCapture: Signal<CaptureSnapshot>
    let cameraCapture: Signal<CaptureSnapshot>
    let modernScreenSharingDetectable: Bool
    let eligibleWithRecommendedDefaults: Bool
    let blockingReasons: [String]
}

func idleSeconds() -> Signal<Double> {
    let value = CGEventSource.secondsSinceLastEventType(
        .combinedSessionState,
        eventType: .null
    )
    guard value.isFinite, value >= 0 else {
        return .failure("CoreGraphics returned an invalid idle duration")
    }
    return .success(value)
}

func acPower() -> Signal<Bool> {
    guard let unmanaged = IOPSCopyPowerSourcesInfo() else {
        return .failure("IOPSCopyPowerSourcesInfo returned no snapshot")
    }
    let snapshot = unmanaged.takeRetainedValue()
    guard let source = IOPSGetProvidingPowerSourceType(snapshot)?.takeUnretainedValue() else {
        return .failure("Unable to resolve the providing power source")
    }
    return .success(source as String == kIOPMACPowerKey as String)
}

func thermalName(_ state: ProcessInfo.ThermalState) -> String {
    switch state {
    case .nominal: return "nominal"
    case .fair: return "fair"
    case .serious: return "serious"
    case .critical: return "critical"
    @unknown default: return "unknown"
    }
}

func memorySnapshot() -> Signal<MemorySnapshot> {
    var pageSize: vm_size_t = 0
    guard host_page_size(mach_host_self(), &pageSize) == KERN_SUCCESS else {
        return .failure("host_page_size failed")
    }
    var stats = vm_statistics64()
    var count = mach_msg_type_number_t(
        MemoryLayout<vm_statistics64_data_t>.size / MemoryLayout<integer_t>.size
    )
    let result: kern_return_t = withUnsafeMutablePointer(to: &stats) { pointer in
        pointer.withMemoryRebound(to: integer_t.self, capacity: Int(count)) { rebound in
            host_statistics64(mach_host_self(), HOST_VM_INFO64, rebound, &count)
        }
    }
    guard result == KERN_SUCCESS else {
        return .failure("host_statistics64 failed with code \(result)")
    }
    let availablePages = UInt64(stats.free_count + stats.inactive_count + stats.purgeable_count)
    let available = availablePages * UInt64(pageSize)
    let physical = ProcessInfo.processInfo.physicalMemory
    guard physical > 0 else { return .failure("physicalMemory is zero") }
    let ratio = Double(available) / Double(physical)
    let pressure = ratio < 0.08 ? "critical" : (ratio < 0.15 ? "warning" : "normal")
    return .success(
        MemorySnapshot(
            availableBytes: available,
            physicalBytes: physical,
            availableRatio: ratio,
            pressure: pressure
        )
    )
}

func audioDeviceName(_ id: AudioDeviceID) -> String {
    var address = AudioObjectPropertyAddress(
        mSelector: kAudioObjectPropertyName,
        mScope: kAudioObjectPropertyScopeGlobal,
        mElement: kAudioObjectPropertyElementMain
    )
    var name: Unmanaged<CFString>?
    var size = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
    let status = AudioObjectGetPropertyData(id, &address, 0, nil, &size, &name)
    guard status == noErr, let name else { return "Audio device \(id)" }
    return name.takeUnretainedValue() as String
}

func hasInputStreams(_ id: AudioDeviceID) -> Bool {
    var address = AudioObjectPropertyAddress(
        mSelector: kAudioDevicePropertyStreamConfiguration,
        mScope: kAudioObjectPropertyScopeInput,
        mElement: kAudioObjectPropertyElementMain
    )
    var size: UInt32 = 0
    guard AudioObjectGetPropertyDataSize(id, &address, 0, nil, &size) == noErr,
          size >= UInt32(MemoryLayout<AudioBufferList>.size) else { return false }
    let raw = UnsafeMutableRawPointer.allocate(
        byteCount: Int(size), alignment: MemoryLayout<AudioBufferList>.alignment
    )
    defer { raw.deallocate() }
    guard AudioObjectGetPropertyData(id, &address, 0, nil, &size, raw) == noErr else {
        return false
    }
    let list = UnsafeMutableAudioBufferListPointer(
        raw.assumingMemoryBound(to: AudioBufferList.self)
    )
    return list.reduce(0) { $0 + Int($1.mNumberChannels) } > 0
}

func microphoneCapture() -> Signal<CaptureSnapshot> {
    var address = AudioObjectPropertyAddress(
        mSelector: kAudioHardwarePropertyDevices,
        mScope: kAudioObjectPropertyScopeGlobal,
        mElement: kAudioObjectPropertyElementMain
    )
    var size: UInt32 = 0
    let system = AudioObjectID(kAudioObjectSystemObject)
    guard AudioObjectGetPropertyDataSize(system, &address, 0, nil, &size) == noErr else {
        return .failure("Unable to enumerate Core Audio devices")
    }
    let count = Int(size) / MemoryLayout<AudioDeviceID>.size
    var devices = [AudioDeviceID](repeating: 0, count: count)
    guard AudioObjectGetPropertyData(system, &address, 0, nil, &size, &devices) == noErr else {
        return .failure("Unable to read Core Audio device ids")
    }

    var activeNames: [String] = []
    for device in devices where hasInputStreams(device) {
        var runningAddress = AudioObjectPropertyAddress(
            mSelector: kAudioDevicePropertyDeviceIsRunningSomewhere,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        var running: UInt32 = 0
        var runningSize = UInt32(MemoryLayout<UInt32>.size)
        let status = AudioObjectGetPropertyData(
            device, &runningAddress, 0, nil, &runningSize, &running
        )
        guard status == noErr else {
            return .failure("Unable to query input activity for \(audioDeviceName(device))")
        }
        if running != 0 { activeNames.append(audioDeviceName(device)) }
    }
    return .success(CaptureSnapshot(active: !activeNames.isEmpty, activeDevices: activeNames))
}

func cameraCapture() -> Signal<CaptureSnapshot> {
    let devices = AVCaptureDevice.DiscoverySession(
        deviceTypes: [.builtInWideAngleCamera, .external],
        mediaType: .video,
        position: .unspecified
    ).devices
    let active = devices.filter { $0.isInUseByAnotherApplication }.map(\.localizedName)
    return .success(CaptureSnapshot(active: !active.isEmpty, activeDevices: active))
}

func makeSnapshot() -> ProbeSnapshot {
    let idle = idleSeconds()
    let ac = acPower()
    let thermal = Signal<String>.success(thermalName(ProcessInfo.processInfo.thermalState))
    let lowPower = Signal<Bool>.success(ProcessInfo.processInfo.isLowPowerModeEnabled)
    let memory = memorySnapshot()
    let microphone = microphoneCapture()
    let camera = cameraCapture()
    var reasons: [String] = []

    func require(_ condition: Bool?, _ reason: String, unavailable: String) {
        guard let condition else { reasons.append(unavailable); return }
        if !condition { reasons.append(reason) }
    }
    require(idle.value.map { $0 >= 300 }, "user-idle-less-than-300-seconds", unavailable: "idle-signal-unavailable")
    require(ac.value, "not-on-ac-power", unavailable: "power-signal-unavailable")
    require(thermal.value.map { $0 == "nominal" }, "thermal-state-not-nominal", unavailable: "thermal-signal-unavailable")
    require(lowPower.value.map { !$0 }, "low-power-mode-enabled", unavailable: "low-power-signal-unavailable")
    require(memory.value.map { $0.pressure == "normal" }, "memory-pressure-not-normal", unavailable: "memory-signal-unavailable")
    require(microphone.value.map { !$0.active }, "microphone-capture-active", unavailable: "microphone-signal-unavailable")
    require(camera.value.map { !$0.active }, "camera-capture-active", unavailable: "camera-signal-unavailable")

    let formatter = ISO8601DateFormatter()
    return ProbeSnapshot(
        timestamp: formatter.string(from: Date()),
        idleSeconds: idle,
        onACPower: ac,
        thermalState: thermal,
        lowPowerMode: lowPower,
        memory: memory,
        microphoneCapture: microphone,
        cameraCapture: camera,
        modernScreenSharingDetectable: false,
        eligibleWithRecommendedDefaults: reasons.isEmpty,
        blockingReasons: reasons
    )
}

func emit(_ snapshot: ProbeSnapshot) throws {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
    let data = try encoder.encode(snapshot)
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data("\n".utf8))
}

let arguments = CommandLine.arguments.dropFirst()
let watch = arguments.contains("--watch")
let intervalIndex = arguments.firstIndex(of: "--interval")
let interval: TimeInterval = intervalIndex.flatMap { index in
    let next = arguments.index(after: index)
    return next < arguments.endIndex ? Double(arguments[next]) : nil
} ?? 1.0

do {
    repeat {
        try emit(makeSnapshot())
        if watch { Thread.sleep(forTimeInterval: max(0.2, interval)) }
    } while watch
} catch {
    FileHandle.standardError.write(Data("macOS idle probe failed: \(error)\n".utf8))
    exit(1)
}
