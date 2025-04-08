import SwiftUI
import AVFoundation
import Firebase
import UserNotifications

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
