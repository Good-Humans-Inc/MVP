import Foundation
import AVFoundation
import Combine
import Speech

class ResourceCoordinator: NSObject, ObservableObject {
    // Reference to AppState
    private let appState: AppState
    
    // Published properties for UI updates
    @Published var isExerciseSessionActive = false
    @Published var allPermissionsGranted = false
    @Published var coordinationError: String?
    
    // Audio session manager
    private let audioSession = AVAudioSession.sharedInstance()
    
    // References to the managers this coordinator will manage
    private weak var cameraManager: CameraManager?
    private weak var visionManager: VisionManager?
    private weak var voiceManager: VoiceManager?
    
    // Initialize with AppState
    init(appState: AppState) {
        self.appState = appState
        super.init()
        
        // Update initial resource state
        updateResourceState(isInitialized: false)
    }
    
    // Update resource state in AppState
    private func updateResourceState(isInitialized: Bool? = nil, isCleaningUp: Bool? = nil, error: String? = nil) {
        DispatchQueue.main.async {
            if let isInitialized = isInitialized {
                self.appState.resourceState.isInitialized = isInitialized
            }
            if let isCleaningUp = isCleaningUp {
                self.appState.resourceState.isCleaningUp = isCleaningUp
            }
            if let error = error {
                self.appState.resourceState.error = error
            }
        }
    }
    
    func configure(cameraManager: CameraManager, visionManager: VisionManager, voiceManager: VoiceManager) {
        self.cameraManager = cameraManager
        self.visionManager = visionManager
        self.voiceManager = voiceManager
        
        // Update resource state
        updateResourceState(isInitialized: true)
    }
    
    // MARK: - Permission Handling
    
    func checkInitialPermissions() {
        print("🔍 ResourceCoordinator.checkInitialPermissions called")
        checkAllPermissions { _ in /* No action needed on initial check */ }
    }
    
    func checkAllPermissions(completion: @escaping (Bool) -> Void) {
        print("🔍 Checking all permissions")
        
        // Reset the permission flag
        allPermissionsGranted = false
        
        // Check camera permission
        let cameraStatus = AVCaptureDevice.authorizationStatus(for: .video)
        print("📷 Camera permission status: \(cameraStatus.rawValue)")
        
        // Check microphone permission - using updated API
        var microphoneGranted = false
        
        // Use the appropriate API based on iOS version
        if #available(iOS 17.0, *) {
            AVAudioApplication.requestRecordPermission { granted in
                microphoneGranted = granted
                print("🎤 Microphone permission granted: \(granted)")
                
                DispatchQueue.main.async {
                    // For RSI exercises, we only need camera and microphone
                    let allGranted = (cameraStatus == .authorized) && microphoneGranted
                    
                    self.allPermissionsGranted = allGranted
                    print("🔐 All permissions granted: \(allGranted)")
                    completion(allGranted)
                }
            }
        } else {
            // Use the older API for iOS 16 and below
            audioSession.requestRecordPermission { granted in
                microphoneGranted = granted
                print("🎤 Microphone permission granted: \(granted)")
                
                DispatchQueue.main.async {
                    // For RSI exercises, we only need camera and microphone
                    let allGranted = (cameraStatus == .authorized) && microphoneGranted
                    
                    self.allPermissionsGranted = allGranted
                    print("🔐 All permissions granted: \(allGranted)")
                    completion(allGranted)
                }
            }
        }
    }
    
    // MARK: - Exercise Session Management
    
    func startExerciseSession(completion: @escaping (Bool) -> Void) {
        print("🚀 ResourceCoordinator.startExerciseSession called")
        
        // Check permissions first
        checkAllPermissions { allGranted in
            guard allGranted else {
                self.coordinationError = "Missing required permissions"
                print("❌ Missing required permissions for exercise session")
                completion(false)
                return
            }
            
            // Set up a single audio session for everything
            do {
                print("🔈 ResourceCoordinator configuring master audio session")
                
                // First deactivate any existing audio session to ensure clean state
                try self.audioSession.setActive(false, options: .notifyOthersOnDeactivation)
                
                // This is the key configuration that works for both speaking and listening
                try self.audioSession.setCategory(.playAndRecord,
                                              mode: .spokenAudio,
                                              options: [.defaultToSpeaker, .allowBluetooth, .mixWithOthers])
                try self.audioSession.setPreferredSampleRate(48000.0)
                try self.audioSession.setPreferredIOBufferDuration(0.005) // 5ms buffer
                try self.audioSession.setActive(true, options: .notifyOthersOnDeactivation)
                print("✅ Master audio session configured")
            } catch {
                self.coordinationError = "Failed to configure audio session: \(error.localizedDescription)"
                print("❌ Audio session config error: \(error)")
                completion(false)
                return
            }
            
            // Now we're in an active exercise session
            self.isExerciseSessionActive = true
            completion(true)
        }
    }
    
    func stopExerciseSession(completion: (() -> Void)? = nil) {
        print("🛑 ResourceCoordinator.stopExerciseSession called")
        
        // Update resource state
        updateResourceState(isCleaningUp: true)
        
        // Stop the camera session
        cameraManager?.resetSession()
        
        // Stop vision processing
        visionManager?.stopProcessing()
        
        // Stop speech synthesis
        voiceManager?.stopSpeaking()
        
        // Deactivate audio session
        do {
            try audioSession.setActive(false, options: .notifyOthersOnDeactivation)
            print("✅ Audio session deactivated in stopExerciseSession")
        } catch {
            print("❌ Error deactivating audio session: \(error.localizedDescription)")
            updateResourceState(error: error.localizedDescription)
        }
        
        // Update state
        isExerciseSessionActive = false
        updateResourceState(isCleaningUp: false)
        
        // Trigger completion handler
        DispatchQueue.main.async {
            completion?()
        }
    }
    
    // MARK: - Audio Route Detection
    
    func printAudioRouteInfo() {
        // Print detailed information about the current audio route
        let currentRoute = audioSession.currentRoute
        
        print("AUDIO ROUTE INFORMATION:")
        print("- Inputs:")
        for input in currentRoute.inputs {
            print("  • \(input.portName) (Type: \(input.portType.rawValue))")
        }
        
        print("- Outputs:")
        for output in currentRoute.outputs {
            print("  • \(output.portName) (Type: \(output.portType.rawValue))")
        }
    }
}
