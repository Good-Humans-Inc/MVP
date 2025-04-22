import Foundation
import UserNotifications
import Firebase
import FirebaseMessaging

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
    }
    
    // MARK: - Public Methods
    
    /// Request notification permissions from the user
    func requestAuthorization(completion: @escaping (Bool, Error?) -> Void) {
        let options: UNAuthorizationOptions = [.alert, .sound, .badge]
        
        notificationCenter.requestAuthorization(options: options) { [weak self] granted, error in
            DispatchQueue.main.async {
                self?.isAuthorized = granted
                
                if granted {
                    // Register for remote notifications
                    UIApplication.shared.registerForRemoteNotifications()
                }
                
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
    
    // MARK: - MessagingDelegate
    
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
    
    private func updateFCMTokenInBackend(token: String) {
        // Get user ID from UserDefaults or your app's state management
        guard let userId = UserDefaults.standard.string(forKey: "UserID") else {
            print("❌ No user ID found for FCM token update")
            return
        }
        
        // Prepare the request
        let url = URL(string: "https://us-central1-pepmvp.cloudfunctions.net/update_fcm_token")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let body = [
            "user_id": userId,
            "fcm_token": token
        ]
        
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        
        // Make the request
        URLSession.shared.dataTask(with: request) { data, response, error in
            if let error = error {
                print("❌ Error updating FCM token: \(error.localizedDescription)")
                return
            }
            
            if let httpResponse = response as? HTTPURLResponse {
                if httpResponse.statusCode == 200 {
                    print("✅ FCM token updated successfully in backend")
                } else {
                    print("❌ Failed to update FCM token in backend: \(httpResponse.statusCode)")
                }
            }
        }.resume()
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