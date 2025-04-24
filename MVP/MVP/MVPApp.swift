import SwiftUI
import AVFoundation
import Firebase
import UserNotifications
import FirebaseMessaging

typealias Joint = BodyJointType
// App Delegate to handle Firebase
class AppDelegate: NSObject, UIApplicationDelegate {
    // Track if this is first launch of the app
    @AppStorage("isFirstAppLaunch") private var isFirstAppLaunch = true
    
    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        print("📱 Application launching (first launch: \(isFirstAppLaunch))")
        
        // Special setup for first launch
        if isFirstAppLaunch {
            setupForFirstLaunch()
        }
        
        // Configure Firebase
        FirebaseApp.configure()
        print("🔥 Firebase configured with options: \(String(describing: FirebaseApp.app()?.options))")
        
        // Set messaging delegate
        Messaging.messaging().delegate = self
        print("📨 Firebase Messaging delegate set")
        
        // Request notification permissions
        requestNotificationPermissions()
        
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
    
    // Request notification permissions
    private func requestNotificationPermissions() {
        let center = UNUserNotificationCenter.current()
        center.requestAuthorization(options: [.alert, .sound, .badge]) { granted, error in
            if granted {
                print("✅ Notification permission granted")
                DispatchQueue.main.async {
                    UIApplication.shared.registerForRemoteNotifications()
                }
            } else if let error = error {
                print("❌ Notification permission error: \(error.localizedDescription)")
            } else {
                print("❌ Notification permission denied")
            }
        }
    }
    
    // Handle successful registration for remote notifications
    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        // Convert token to string
        let tokenParts = deviceToken.map { data in String(format: "%02.2hhx", data) }
        let token = tokenParts.joined()
        print("📱 APNs Device Token: \(token)")
        
        // Set the APNs token in Firebase Messaging
        Messaging.messaging().apnsToken = deviceToken
        print("🔥 APNs token set in Firebase Messaging")
        
        // Request FCM token explicitly
        Messaging.messaging().token { token, error in
            if let error = error {
                print("❌ Error fetching FCM token after APNs registration: \(error)")
            }
            if let token = token {
                print("✅ FCM token generated after APNs registration: \(token)")
            }
        }
    }
    
    // Handle failed registration for remote notifications
    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
        print("❌ Failed to register for remote notifications: \(error.localizedDescription)")
    }
    
    // Handle incoming remote notifications when app is in foreground
    func application(_ application: UIApplication, didReceiveRemoteNotification userInfo: [AnyHashable : Any], fetchCompletionHandler completionHandler: @escaping (UIBackgroundFetchResult) -> Void) {
        print("📱 Received remote notification: \(userInfo)")
        
//        // Process the notification data
//        if let exerciseId = userInfo["exerciseId"] as? String {
//            // Handle exercise notification
//            print("📱 Remote notification for exercise: \(exerciseId)")
//            // You can post a notification to handle this in your app
//            NotificationCenter.default.post(name: NSNotification.Name("OpenExerciseFromNotification"), object: nil, userInfo: ["exerciseId": exerciseId])
//            completionHandler(.newDataFetched)
//        } else {
//            completionHandler(.noData)
//        }
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
        
        let voice = VoiceManager()
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
