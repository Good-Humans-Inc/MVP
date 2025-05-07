    // Simplified Example for LoggingService.swift
    import Foundation
    import os // For OSLog
    import FirebaseCrashlytics
    import UIKit // Add this import for UIDevice

    class LoggingService {
        static let shared = LoggingService()
        private let defaultSubsystem = Bundle.main.bundleIdentifier ?? "com.yourapp"
        private var currentSessionID: String?

        // MARK: - Log Entry Structure
        struct LogPayload: Codable {
            let appVersion: String?
            let osVersion: String?
            let deviceModel: String?
            let fileName: String?
            let functionName: String?
            let lineNumber: UInt?
        }

        struct LogEntry: Codable {
            let timestamp: String // ISO 8601
            let severity: String // e.g., INFO, ERROR, DEBUG
            let message: String
            let sessionID: String?
            let iosClientInfo: LogPayload?
            let data: [String: String]? // For additional custom data, simplified to [String: String] for now
        }

        private func getOSLogger(category: String) -> Logger {
            return Logger(subsystem: defaultSubsystem, category: category)
        }

        // MARK: - Session Management
        func startNewSession() {
            self.currentSessionID = UUID().uuidString
            self.info("New session started", category: "SessionManagement", data: ["session_id": self.currentSessionID ?? "N/A"])
        }

        func getCurrentSessionID() -> String? {
            return self.currentSessionID
        }

        func info(_ message: String, category: String = "App", data: [String: String]? = nil, file: String = #file, function: String = #function, line: UInt = #line) {
            let logMsg = "[\(URL(fileURLWithPath: file).lastPathComponent):\(line)] \(function) - \(message)"
            getOSLogger(category: category).info("\(logMsg)")
            Crashlytics.crashlytics().log("INFO: [\(category)] \(logMsg)")

            let clientInfo = LogPayload(
                appVersion: Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String,
                osVersion: UIDevice.current.systemVersion,
                deviceModel: UIDevice.current.model,
                fileName: URL(fileURLWithPath: file).lastPathComponent,
                functionName: function,
                lineNumber: line
            )

            let entry = LogEntry(
                timestamp: ISO8601DateFormatter().string(from: Date()),
                severity: "INFO",
                message: message,
                sessionID: self.currentSessionID,
                iosClientInfo: clientInfo,
                data: data
            )

            if let jsonData = try? JSONEncoder().encode(entry),
               let jsonString = String(data: jsonData, encoding: .utf8) {
                print("INFO_JSON: \(jsonString)")
            }
        }

        func error(_ message: String, error: Error? = nil, category: String = "Error", data: [String: String]? = nil, file: String = #file, function: String = #function, line: UInt = #line, userInfo: [String: Any]? = nil) {
            let logMsg = "[\(URL(fileURLWithPath: file).lastPathComponent):\(line)] \(function) - \(message)"
            getOSLogger(category: category).error("🛑 ERROR: \(logMsg) \(error?.localizedDescription ?? "")")

            Crashlytics.crashlytics().log("ERROR: [\(category)] \(logMsg)")
            if let error = error {
                var combinedUserInfo = userInfo ?? [:]
                let nsError = error as NSError
                combinedUserInfo["error_domain"] = nsError.domain
                combinedUserInfo["error_code"] = nsError.code
                for (key, value) in nsError.userInfo {
                    if let stringKey = key as? String {
                         combinedUserInfo["nserror_\(stringKey)"] = String(describing: value)
                    }
                }
                Crashlytics.crashlytics().record(error: error, userInfo: combinedUserInfo.isEmpty ? nil : combinedUserInfo)
            } else if let userInfo = userInfo {
                Crashlytics.crashlytics().setCustomKeysAndValues(userInfo.mapValues { String(describing: $0) })
            }

            let clientInfo = LogPayload(
                appVersion: Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String,
                osVersion: UIDevice.current.systemVersion,
                deviceModel: UIDevice.current.model,
                fileName: URL(fileURLWithPath: file).lastPathComponent,
                functionName: function,
                lineNumber: line
            )

            let entry = LogEntry(
                timestamp: ISO8601DateFormatter().string(from: Date()),
                severity: "ERROR",
                message: message + (error != nil ? " | Error: \(error!.localizedDescription)" : ""),
                sessionID: self.currentSessionID,
                iosClientInfo: clientInfo,
                data: data
            )
            
            if let jsonData = try? JSONEncoder().encode(entry),
               let jsonString = String(data: jsonData, encoding: .utf8) {
                print("ERROR_JSON: \(jsonString)")
            }
        }

        func setUserID(_ id: String?) {
            Crashlytics.crashlytics().setUserID(id)
            getOSLogger(category: "UserSession").info("Crashlytics UserID set: \(id ?? "nil", privacy: .private(mask: .hash))")
        }

        func setCustomKey(_ key: String, value: Any?) {
            Crashlytics.crashlytics().setCustomValue(value ?? "nil", forKey: key)
             getOSLogger(category: "AppContext").debug("Crashlytics key '\(key)' set.")
        }
    }
    
