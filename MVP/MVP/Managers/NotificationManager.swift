import Foundation
import UserNotifications
import Firebase
import FirebaseMessaging
import FirebaseFirestore

class NotificationManager: NSObject, ObservableObject, UNUserNotificationCenterDelegate, MessagingDelegate {
    // MARK: - Published Properties
    @Published var isAuthorized = false
    @Published var fcmToken: String?
    @Published var notificationPreferences = NotificationPreferences()
    
    // MARK: - Private Properties
    private let notificationCenter = UNUserNotificationCenter.current()
    private let defaults = UserDefaults.standard
    
    // MARK: - Initialization
    override init() {
        super.init()
        
        // Set delegates
        notificationCenter.delegate = self
        Messaging.messaging().delegate = self
        
        // Load saved preferences
        loadPreferences()
        
        // Check current authorization status
        checkAuthorizationStatus()
        
        // Request authorization and then register for remote notifications
        requestAuthorization { granted, error in
            if granted {
                print("✅ Notification permission granted")
                DispatchQueue.main.async {
                    UIApplication.shared.registerForRemoteNotifications()
                }
            } else {
                print("❌ Notification permission denied: \(String(describing: error))")
            }
        }
    }
    
    // MARK: - Public Methods
    
    /// Request notification permissions from the user
    func requestAuthorization(completion: @escaping (Bool, Error?) -> Void) {
        let options: UNAuthorizationOptions = [.alert, .sound, .badge]
        
        notificationCenter.requestAuthorization(options: options) { [weak self] granted, error in
            DispatchQueue.main.async {
                self?.isAuthorized = granted
                completion(granted, error)
            }
        }
    }
    
    /// Schedule a local notification
    func scheduleLocalNotification(title: String, body: String, timeInterval: TimeInterval, identifier: String, isOneTime: Bool = false) {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default
        content.userInfo = ["is_one_time": isOneTime]
        
        let trigger = UNTimeIntervalNotificationTrigger(timeInterval: timeInterval, repeats: false)
        let request = UNNotificationRequest(identifier: identifier, content: content, trigger: trigger)
        
        notificationCenter.add(request) { error in
            if let error = error {
                print("❌ Error scheduling local notification: \(error.localizedDescription)")
            } else {
                print("✅ Local notification scheduled successfully")
            }
        }
    }
    
    /// Schedule a daily notification at a specific time
    func scheduleDailyNotification(title: String, body: String, hour: Int, minute: Int, identifier: String, isOneTime: Bool = false) {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default
        content.userInfo = ["is_one_time": isOneTime]
        
        var dateComponents = DateComponents()
        dateComponents.hour = hour
        dateComponents.minute = minute
        
        let trigger = UNCalendarNotificationTrigger(dateMatching: dateComponents, repeats: !isOneTime)
        let request = UNNotificationRequest(identifier: identifier, content: content, trigger: trigger)
        
        notificationCenter.add(request) { error in
            if let error = error {
                print("❌ Error scheduling daily notification: \(error.localizedDescription)")
            } else {
                print("✅ Daily notification scheduled successfully")
            }
        }
    }
    
    /// Schedule a weekly notification on specific days
    func scheduleWeeklyNotification(title: String, body: String, hour: Int, minute: Int, weekdays: [Int], identifier: String) {
        for weekday in weekdays {
            let content = UNMutableNotificationContent()
            content.title = title
            content.body = body
            content.sound = .default
            
            var dateComponents = DateComponents()
            dateComponents.hour = hour
            dateComponents.minute = minute
            dateComponents.weekday = weekday
            
            let trigger = UNCalendarNotificationTrigger(dateMatching: dateComponents, repeats: true)
            let request = UNNotificationRequest(identifier: "\(identifier)_\(weekday)", content: content, trigger: trigger)
            
            notificationCenter.add(request) { error in
                if let error = error {
                    print("❌ Error scheduling weekly notification: \(error.localizedDescription)")
                } else {
                    print("✅ Weekly notification scheduled successfully for weekday \(weekday)")
                }
            }
        }
    }
    
    /// Cancel all pending notifications
    func cancelAllNotifications() {
        notificationCenter.removeAllPendingNotificationRequests()
        print("✅ All pending notifications cancelled")
    }
    
    /// Cancel a specific notification by identifier
    func cancelNotification(identifier: String) {
        notificationCenter.removePendingNotificationRequests(withIdentifiers: [identifier])
        print("✅ Notification cancelled: \(identifier)")
    }
    
    /// Update notification preferences
    func updatePreferences(_ preferences: NotificationPreferences) {
        self.notificationPreferences = preferences
        savePreferences()
        
        // Apply the new preferences
        applyNotificationPreferences()
    }
    
    /// Apply current notification preferences
    func applyNotificationPreferences() {
        // Cancel existing notifications
        cancelAllNotifications()
        
        // Schedule new notifications based on preferences
        if notificationPreferences.isEnabled {
            scheduleDailyNotification(
                title: "Time for your PT exercises!",
                body: "Don't forget to complete your physical therapy exercises today.",
                hour: notificationPreferences.hour,
                minute: notificationPreferences.minute,
                identifier: "daily_exercise_reminder",
                isOneTime: false
            )
        }
    }
    
    /// Get FCM token only after APNs token is set
    func getFCMToken(completion: @escaping (String?) -> Void) {
        // Check if we already have an FCM token
        if let existingToken = fcmToken {
            print("✅ Using existing FCM token")
            completion(existingToken)
            return
        }
        
        // Check if we're registered for remote notifications
        if !UIApplication.shared.isRegisteredForRemoteNotifications {
            print("⚠️ Not registered for remote notifications yet, requesting registration")
            UIApplication.shared.registerForRemoteNotifications()
            
            // Wait a bit and try again
            DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) { [weak self] in
                self?.getFCMToken(completion: completion)
            }
            return
        }
        
        // Try to get FCM token
        Messaging.messaging().token { [weak self] token, error in
            if let error = error {
                print("❌ Error fetching FCM token: \(error.localizedDescription)")
                completion(nil)
                return
            }
            
            if let token = token {
                print("📱 FCM Token: \(token)")
                self?.fcmToken = token
                
                // Send token to backend if we have a user ID
                if let userId = UserDefaults.standard.string(forKey: "UserID") {
                    self?.updateFCMTokenInBackend(token: token)
                }
                
                completion(token)
            } else {
                print("❌ No FCM token available")
                completion(nil)
            }
        }
    }
    
    // MARK: - MessagingDelegate Methods
    
    /// Handle FCM token refresh
    func messaging(_ messaging: Messaging, didReceiveRegistrationToken fcmToken: String?) {
        print("📱 Firebase registration token: \(String(describing: fcmToken))")
        
        // Store token
        self.fcmToken = fcmToken
        
        // Send this token to backend
        if let token = fcmToken {
            updateFCMTokenInBackend(token: token)
        }
    }
    
    // MARK: - Backend Integration
    
    /// Update FCM token in backend
    func updateFCMTokenInBackend(token: String) {
        guard let userId = UserDefaults.standard.string(forKey: "UserID") else {
            print("❌ No user ID available for FCM token update - will retry when user ID is available")
            return
        }
        
        print("�� Updating FCM token via API for user: \(userId)")
        
        guard let url = URL(string: "https://us-central1-pepmvp.cloudfunctions.net/update_fcm_token") else {
            print("❌ Invalid URL for FCM token update")
            return
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let body: [String: String] = [
            "user_id": userId,
            "fcm_token": token
        ]
        
        guard let jsonData = try? JSONSerialization.data(withJSONObject: body) else {
            print("❌ Failed to serialize request body")
            return
        }
        
        request.httpBody = jsonData
        
        URLSession.shared.dataTask(with: request) { data, response, error in
            if let error = error {
                print("❌ Error updating FCM token: \(error.localizedDescription)")
                return
            }
            
            if let httpResponse = response as? HTTPURLResponse {
                if httpResponse.statusCode == 200 {
                    print("✅ FCM token updated successfully via API")
                } else {
                    print("❌ FCM token update failed with status: \(httpResponse.statusCode)")
                }
            }
        }.resume()
    }
    
    // MARK: - UNUserNotificationCenterDelegate
    
    /// Handle notification when app is in foreground
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification, withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        // Show notification even when app is in foreground
        completionHandler([.banner, .sound, .badge])
    }
    
    /// Handle notification tap
    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse, withCompletionHandler completionHandler: @escaping () -> Void) {
        // Handle notification tap
        let userInfo = response.notification.request.content.userInfo
        
        // Check if this is a one-time notification
        let isOneTime = userInfo["is_one_time"] as? Bool ?? false
        
        // Process the notification data
        if let exerciseId = userInfo["exerciseId"] as? String {
            // Handle exercise notification
            print("📱 Notification tapped for exercise: \(exerciseId)")
            // You can post a notification to handle this in your app
            NotificationCenter.default.post(name: NSNotification.Name("OpenExerciseFromNotification"), object: nil, userInfo: ["exerciseId": exerciseId])
        }
        
        completionHandler()
    }
    
    // MARK: - Private Methods
    
    /// Check current authorization status
    private func checkAuthorizationStatus() {
        notificationCenter.getNotificationSettings { [weak self] settings in
            DispatchQueue.main.async {
                self?.isAuthorized = settings.authorizationStatus == .authorized
            }
        }
    }
    
    /// Load saved preferences from UserDefaults
    private func loadPreferences() {
        if let data = defaults.data(forKey: "notificationPreferences"),
           let preferences = try? JSONDecoder().decode(NotificationPreferences.self, from: data) {
            self.notificationPreferences = preferences
        }
    }
    
    /// Save preferences to UserDefaults
    private func savePreferences() {
        if let data = try? JSONEncoder().encode(notificationPreferences) {
            defaults.set(data, forKey: "notificationPreferences")
        }
    }
}

// MARK: - Notification Preferences Model
struct NotificationPreferences: Codable {
    var isEnabled: Bool = true
    var frequency: NotificationFrequency = .daily
    var hour: Int = 9 // Default to 9 AM
    var minute: Int = 0
    var weekdays: [Int] = [2, 4, 6] // Default to Monday, Wednesday, Friday (2, 4, 6)
}

// MARK: - Notification Frequency Enum
enum NotificationFrequency: String, Codable, CaseIterable {
    case daily
    case weekly
} 

