import SwiftUI
import AVFoundation
import Firebase
import FirebaseFirestore
import FirebaseAppCheck
import UserNotifications
import FirebaseMessaging

typealias Joint = BodyJointType
// App Delegate to handle Firebase
class AppDelegate: NSObject, UIApplicationDelegate, MessagingDelegate, UNUserNotificationCenterDelegate {
    // Track if this is first launch of the app
    @AppStorage("isFirstAppLaunch") private var isFirstAppLaunch = true
    
    // Flag to track if we've set the APNs token
    private var apnsTokenRegistered = false
    
    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        print("📱 Application launching (first launch: \(isFirstAppLaunch))")
        
        // Initialize UserManager early
        _ = UserManager.shared
        print("✅ MVPApp: UserManager initialized during app launch")
        
        // Special setup for first launch
        if isFirstAppLaunch {
            setupForFirstLaunch()
        }
        
        // Check for timezone changes
        checkAndUpdateTimezone()
        
        // Configure App Check for development
        #if DEBUG
        let providerFactory = AppCheckDebugProviderFactory()
        AppCheck.setAppCheckProviderFactory(providerFactory)
        print("🔐 App Check configured for development")
        #endif
        
        // Configure Firebase FIRST before anything else
        FirebaseApp.configure()
        print("🔥 Firebase configured with options: \(String(describing: FirebaseApp.app()?.options))")
        
        // Configure Firestore settings
        let settings = FirestoreSettings()
        settings.host = "firestore.googleapis.com"
        
        // Create custom FirebaseOptions to specify the database
        let db = Firestore.firestore()
        db.settings = settings
        
        // Use the specific database
        let firestoreDB = try! FirebaseFirestore.Firestore.firestore(database: "pep-mvp")
        
        // CRITICAL: Set notification delegates BEFORE requesting permissions
        UNUserNotificationCenter.current().delegate = self
        Messaging.messaging().delegate = self
        print("📨 Firebase Messaging and notification delegates set")
        
        // IMPORTANT: Force registration to always happen on main thread
        DispatchQueue.main.async {
            // Request notification permissions with all options
            let authOptions: UNAuthorizationOptions = [.alert, .badge, .sound]
            UNUserNotificationCenter.current().requestAuthorization(
                options: authOptions) { granted, error in
                    DispatchQueue.main.async {
                        if granted {
                            print("✅ Notification permission granted")
                            // CRUCIAL: Always register for remote notifications on the main thread
                            application.registerForRemoteNotifications()
                        } else if let error = error {
                            print("❌ Notification permission error: \(error.localizedDescription)")
                        } else {
                            print("❌ Notification permission denied")
                        }
                    }
                }
        }
        
        // Only mark first launch as complete after setup is done
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) { [weak self] in
            self?.isFirstAppLaunch = false
            print("📱 First launch setup completed")
        }
        
        return true
    }
    
    // Setup specific configurations for first launch
    private func setupForFirstLaunch() {
        print("🔄 Setting up app for first launch")
        
        // Reset all UserDefaults flags related to initialization
        UserDefaults.standard.set(false, forKey: "cameraManagerInitialized")
        UserDefaults.standard.set(false, forKey: "hasStartedExerciseBefore")
        
        // Pre-initialize AVCaptureSession at app startup to reduce failures
        let captureSession = AVCaptureSession()
        let sessionQueue = DispatchQueue(label: "session queue")
        
        // Request camera permissions right away
        AVCaptureDevice.requestAccess(for: .video) { granted in
            print("📷 Camera permission pre-request result: \(granted)")
            
            // If granted, do an initial configuration
            if granted {
                sessionQueue.async {
                    captureSession.beginConfiguration()
                    
                    // Attempt to add an input
                    if let device = AVCaptureDevice.default(for: .video),
                       let input = try? AVCaptureDeviceInput(device: device),
                       captureSession.canAddInput(input) {
                        captureSession.addInput(input)
                    }
                    
                    captureSession.commitConfiguration()
                    
                    // Start and immediately stop the session
                    captureSession.startRunning()
                    Thread.sleep(forTimeInterval: 0.5)
                    captureSession.stopRunning()
                    
                    print("✅ Camera session pre-initialized")
                }
            }
        }
        
        // Pre-configure audio session to initialize the system
        do {
            let audioSession = AVAudioSession.sharedInstance()
            
            // First make sure it's not active
            try? audioSession.setActive(false, options: .notifyOthersOnDeactivation)
            
            // Configure with default settings
            try audioSession.setCategory(.playAndRecord,
                                      mode: .default,
                                      options: [.defaultToSpeaker])
            
            // Briefly activate and deactivate to initialize
            try audioSession.setActive(true)
            try audioSession.setActive(false)
            
            print("✅ Audio session pre-initialized for first launch")
        } catch {
            print("❌ Error pre-initializing audio session: \(error)")
        }
    }
    
    // MARK: - Timezone Management
    
    private func checkAndUpdateTimezone() {
        // Since Container is not accessible, go directly to checkTimezoneChangeDirect
        checkTimezoneChangeDirect()
        
        // We'll let the NotificationManager check timezone changes when it's initialized
        print("🕒 Timezone check handled by AppDelegate, NotificationManager will check again when ready")
    }
    
    private func checkTimezoneChangeDirect() {
        // Get current timezone offset
        let currentOffset = TimeZone.current.secondsFromGMT() / 3600
        let currentOffsetString = String(currentOffset)
        
        // Get last known timezone offset
        let timezoneCacheKey = "lastKnownTimezone"
        let defaults = UserDefaults.standard
        let lastKnownOffset = defaults.string(forKey: timezoneCacheKey)
        
        print("📱 Current timezone offset: \(currentOffsetString), Last known: \(lastKnownOffset ?? "none")")
        
        // Check if timezone has changed
        if lastKnownOffset != currentOffsetString {
            print("🕒 Timezone has changed from \(lastKnownOffset ?? "unknown") to \(currentOffsetString)")
            
            // Update server when user ID is available
            if let userId = UserDefaults.standard.string(forKey: "UserId") {
                updateTimezoneOnServer(userId: userId, timezone: currentOffsetString)
            } else {
                print("⚠️ User ID not available yet, timezone update will be handled by NotificationManager")
            }
            
            // Cache the new timezone
            defaults.set(currentOffsetString, forKey: timezoneCacheKey)
        }
    }
    
    private func updateTimezoneOnServer(userId: String, timezone: String) {
        guard let url = URL(string: "https://us-central1-pepmvp.cloudfunctions.net/update_timezone") else {
            print("❌ Invalid URL for timezone update")
            return
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let body: [String: String] = [
            "user_id": userId,
            "timezone": timezone
        ]
        
        print("🕒 Updating timezone on server: \(body)")
        
        guard let jsonData = try? JSONSerialization.data(withJSONObject: body) else {
            print("❌ Failed to serialize timezone update request")
            return
        }
        
        request.httpBody = jsonData
        
        URLSession.shared.dataTask(with: request) { data, response, error in
            if let error = error {
                print("❌ Error updating timezone: \(error.localizedDescription)")
                return
            }
            
            if let httpResponse = response as? HTTPURLResponse {
                if httpResponse.statusCode == 200 {
                    print("✅ Timezone updated successfully")
                } else {
                    print("❌ Timezone update failed with status: \(httpResponse.statusCode)")
                }
            }
        }.resume()
    }
    
    // MARK: - Remote Notification Handling
    
    // CRITICAL: This method must be present, even if empty
    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        // Convert token to string for logging
        let tokenParts = deviceToken.map { data in String(format: "%02.2hhx", data) }
        let token = tokenParts.joined()
        print("📱 APNs device token received: \(token)")
        
        // Save the APNs token locally
        UserDefaults.standard.set(token, forKey: "APNsToken")
        
        // Set the APNs token in Firebase using both available methods
        Messaging.messaging().apnsToken = deviceToken
        Messaging.messaging().setAPNSToken(deviceToken, type: .prod) // or .sandbox for development
        
        print("🔄 APNs token explicitly set in Firebase Messaging")
        
        // Set the flag indicating we have the APNs token
        apnsTokenRegistered = true
        
        // Manually request FCM token now that we have APNs token
        refreshFCMToken()
    }
    
    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
        print("❌ Failed to register for remote notifications: \(error.localizedDescription)")
        
        // Try to register again after a delay
        DispatchQueue.main.asyncAfter(deadline: .now() + 5.0) {
            print("🔄 Retrying remote notification registration")
            application.registerForRemoteNotifications()
        }
    }
    
    // Force a refresh of the FCM token
    private func refreshFCMToken() {
        print("🔄 Manually refreshing FCM token after APNs token set")
        
        Messaging.messaging().token { token, error in
            if let error = error {
                print("❌ Error retrieving FCM token: \(error.localizedDescription)")
                
                // Retry after delay if this fails
                DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
                    self.refreshFCMToken()
                }
                return
            }
            
            if let token = token {
                print("✅ FCM token retrieved after APNs registration: \(token)")
                UserDefaults.standard.set(token, forKey: "FCMToken")
            } else {
                print("⚠️ FCM token is nil after refresh attempt")
            }
        }
    }
    
    // MARK: - MessagingDelegate Methods
    
    func messaging(_ messaging: Messaging, didReceiveRegistrationToken fcmToken: String?) {
        print("📱 Firebase registration token received: \(String(describing: fcmToken))")
        
        if let token = fcmToken {
            // Store token in UserDefaults
            UserDefaults.standard.set(token, forKey: "FCMToken")
            print("✅ FCM Token saved to UserDefaults")
            
            if apnsTokenRegistered {
                print("✅ Both tokens are now registered and linked!")
            } else {
                print("⚠️ FCM token received but waiting for APNs token - this may cause notification issues")
                
                // Try to re-register for remote notifications if we don't have an APNs token yet
                DispatchQueue.main.async {
                    UIApplication.shared.registerForRemoteNotifications()
                }
            }
        }
    }
    
    // MARK: - UNUserNotificationCenterDelegate Methods
    
    func userNotificationCenter(_ center: UNUserNotificationCenter,
                              willPresent notification: UNNotification,
                              withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        // Show notification when app is in foreground
        completionHandler([.banner, .sound, .badge])
    }
    
    func userNotificationCenter(_ center: UNUserNotificationCenter,
                              didReceive response: UNNotificationResponse,
                              withCompletionHandler completionHandler: @escaping () -> Void) {
        let userInfo = response.notification.request.content.userInfo
        print("📱 Notification received: \(userInfo)")
        
        // Handle notification tap
        if let exerciseId = userInfo["exerciseId"] as? String {
            NotificationCenter.default.post(
                name: NSNotification.Name("OpenExerciseFromNotification"),
                object: nil,
                userInfo: ["exerciseId": exerciseId]
            )
        }
        
        completionHandler()
    }
    
    // Handle incoming remote notifications when app is in foreground
    func application(_ application: UIApplication, didReceiveRemoteNotification userInfo: [AnyHashable : Any], fetchCompletionHandler completionHandler: @escaping (UIBackgroundFetchResult) -> Void) {
        print("📱 Received remote notification: \(userInfo)")
        
        // Process the notification data
        if let exerciseId = userInfo["exerciseId"] as? String {
            // Handle exercise notification
            print("📱 Remote notification for exercise: \(exerciseId)")
            // Post notification to handle this in your app
            NotificationCenter.default.post(
                name: NSNotification.Name("OpenExerciseFromNotification"),
                object: nil,
                userInfo: ["exerciseId": exerciseId]
            )
            completionHandler(.newData)
        } else {
            // Handle other types of notifications
            if let notificationType = userInfo["type"] as? String {
                switch notificationType {
                case "exercise_reminder":
                    // Process exercise reminder
                    handleExerciseReminder(userInfo)
                    completionHandler(.newData)
                default:
                    completionHandler(.noData)
                }
            } else {
                completionHandler(.noData)
            }
        }
    }
    
    // Handle exercise reminders
    private func handleExerciseReminder(_ userInfo: [AnyHashable: Any]) {
        // Update app badge
        if let badge = userInfo["badge"] as? Int {
            DispatchQueue.main.async {
                UIApplication.shared.applicationIconBadgeNumber = badge
            }
        }
        
        // Schedule local notification if needed
        if let title = userInfo["title"] as? String,
           let body = userInfo["body"] as? String {
            let content = UNMutableNotificationContent()
            content.title = title
            content.body = body
            content.sound = .default
            
            // Create trigger for immediate display
            let trigger = UNTimeIntervalNotificationTrigger(timeInterval: 1, repeats: false)
            
            // Create request
            let request = UNNotificationRequest(
                identifier: UUID().uuidString,
                content: content,
                trigger: trigger
            )
            
            // Add request to notification center
            UNUserNotificationCenter.current().add(request) { error in
                if let error = error {
                    print("❌ Error scheduling local notification: \(error)")
                }
            }
        }
    }
}

@main
struct MVPApp: App {
    // Use the UIApplicationDelegateAdaptor to connect AppDelegate
    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    
    // Initialize AppState first
    private let appState = AppState()
    
    // Initialize managers with AppState
    @StateObject private var voiceManager: VoiceManager
    @StateObject private var cameraManager: CameraManager
    @StateObject private var visionManager: VisionManager
    @StateObject private var resourceCoordinator: ResourceCoordinator
    @StateObject private var notificationManager: NotificationManager
    
    init() {
        // Initialize managers with dependency injection
        let vision = VisionManager(appState: appState)
        _visionManager = StateObject(wrappedValue: vision)
        
        let camera = CameraManager(appState: appState, visionManager: vision)
        _cameraManager = StateObject(wrappedValue: camera)
        
        let voice = VoiceManager(appState: appState)
        _voiceManager = StateObject(wrappedValue: voice)
        
        let resources = ResourceCoordinator(appState: appState)
        _resourceCoordinator = StateObject(wrappedValue: resources)
        
        let notifications = NotificationManager()
        _notificationManager = StateObject(wrappedValue: notifications)
        print("📱 DEBUG: NotificationManager initialized")
        
        print("🚀 App initialization complete")
    }
    
    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(appState)
                .environmentObject(voiceManager)
                .environmentObject(cameraManager)
                .environmentObject(visionManager)
                .environmentObject(resourceCoordinator)
                .environmentObject(notificationManager)
                .onAppear {
                    // Configure resource coordinator with other managers
                    resourceCoordinator.configure(
                        cameraManager: cameraManager,
                        visionManager: visionManager,
                        voiceManager: voiceManager
                    )
                }
                .onChange(of: appState.isExerciseActive) { _, isActive in
                    // Handle app state changes
                    if !isActive {
                        // Clean up resources when exercise ends
                        cleanupResources()
                    }
                }
        }
    }
    
    private func cleanupResources() {
        voiceManager.cleanUp()
        cameraManager.cleanUp()
        visionManager.cleanUp()
        resourceCoordinator.stopExerciseSession()
        
        // Force deactivate audio session
        do {
            try AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
            print("✅ Audio session deactivated on cleanup")
        } catch {
            print("❌ Failed to deactivate audio session: \(error)")
        }
    }
}