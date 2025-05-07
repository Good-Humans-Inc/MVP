    // Simplified Example for LoggingService.swift
    import Foundation
    import os // For OSLog
    import FirebaseCrashlytics

    class LoggingService {
        static let shared = LoggingService()
        private let defaultSubsystem = Bundle.main.bundleIdentifier ?? "com.yourapp"

        private func getOSLogger(category: String) -> Logger {
            return Logger(subsystem: defaultSubsystem, category: category)
        }

        func info(_ message: String, category: String = "App", file: String = #file, function: String = #function, line: UInt = #line) {
            let logMsg = "[\(URL(fileURLWithPath: file).lastPathComponent):\(line)] \(function) - \(message)"
            getOSLogger(category: category).info("\(logMsg)")
            Crashlytics.crashlytics().log("INFO: [\(category)] \(logMsg)")
        }

        func error(_ message: String, error: Error? = nil, category: String = "Error", file: String = #file, function: String = #function, line: UInt = #line, userInfo: [String: Any]? = nil) {
            let logMsg = "[\(URL(fileURLWithPath: file).lastPathComponent):\(line)] \(function) - \(message)"
            getOSLogger(category: category).error("🛑 ERROR: \(logMsg) \(error?.localizedDescription ?? "")")

            Crashlytics.crashlytics().log("ERROR: [\(category)] \(logMsg)")
            if let error = error {
                // Combine provided userInfo with error's details for Crashlytics
                var combinedUserInfo = userInfo ?? [:]
                let nsError = error as NSError
                combinedUserInfo["error_domain"] = nsError.domain
                combinedUserInfo["error_code"] = nsError.code
                // Add other relevant nsError.userInfo keys, ensuring values are Crashlytics-compatible
                for (key, value) in nsError.userInfo {
                    if let stringKey = key as? String {
                         combinedUserInfo["nserror_\(stringKey)"] = String(describing: value)
                    }
                }
                Crashlytics.crashlytics().record(error: error, userInfo: combinedUserInfo.isEmpty ? nil : combinedUserInfo)
            } else if let userInfo = userInfo {
                Crashlytics.crashlytics().setCustomKeysAndValues(userInfo.mapValues { String(describing: $0) })
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