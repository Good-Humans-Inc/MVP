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
    
    // MARK: - Hand Pose Analysis for RSI Exercises
    
    func analyzeHandPose(_ handPose: HandPose, for exerciseType: RSIExerciseType) -> RSIExerciseFeedback {
        // Create feedback object
        var feedback = RSIExerciseFeedback(exerciseType: exerciseType)
        
        switch exerciseType {
        case .wristExtension:
            feedback = analyzeWristExtensionExercise(handPose)
        case .fingerStretch:
            feedback = analyzeFingerStretchExercise(handPose)
        case .thumbOpposition:
            feedback = analyzeThumbOppositionExercise(handPose)
        case .wristRotation:
            feedback = analyzeWristRotationExercise(handPose)
        }
        
        return feedback
    }
    
    // Analysis for different RSI exercise types
    private func analyzeWristExtensionExercise(_ handPose: HandPose) -> RSIExerciseFeedback {
        var feedback = RSIExerciseFeedback(exerciseType: .wristExtension)
        
        // Get wrist angle
        if let wristAngle = handPose.getWristAngle() {
            // For wrist extension, we want an angle between 30-60 degrees
            if wristAngle < 30 {
                feedback.messages.append("Try to extend your wrist a bit more")
                feedback.quality = .needsImprovement
            } else if wristAngle > 60 {
                feedback.messages.append("Your wrist is extended too far, relax a bit")
                feedback.quality = .needsImprovement
            } else {
                feedback.messages.append("Good wrist extension angle")
                feedback.quality = .good
            }
            
            feedback.metrics["wristAngle"] = wristAngle
        } else {
            feedback.messages.append("Unable to detect wrist angle properly")
            feedback.quality = .cannotDetermine
        }
        
        return feedback
    }
    
    private func analyzeFingerStretchExercise(_ handPose: HandPose) -> RSIExerciseFeedback {
        var feedback = RSIExerciseFeedback(exerciseType: .fingerStretch)
        
        // Get finger extension values
        let extensionValues = handPose.getFingerExtensionValues()
        
        // For finger stretch, we want all fingers extended
        var allExtended = true
        var anyMissing = false
        
        // Check each finger
        for finger in ["index", "middle", "ring", "little"] {
            if let extensionValue = extensionValues[finger] {
                // Set threshold based on typical finger length (can be calibrated better)
                let threshold: CGFloat = 80.0
                
                if extensionValue < threshold {
                    feedback.messages.append("\(finger.capitalized) finger needs to stretch more")
                    allExtended = false
                }
                
                feedback.metrics["\(finger)Extension"] = extensionValue
            } else {
                anyMissing = true
            }
        }
        
        if anyMissing {
            feedback.messages.append("Some fingers not detected properly")
            feedback.quality = .cannotDetermine
        } else if allExtended {
            feedback.messages.append("Good finger stretch position")
            feedback.quality = .good
        } else {
            feedback.quality = .needsImprovement
        }
        
        return feedback
    }
    
    private func analyzeThumbOppositionExercise(_ handPose: HandPose) -> RSIExerciseFeedback {
        var feedback = RSIExerciseFeedback(exerciseType: .thumbOpposition)
        
        // For thumb opposition, check the distance between thumb tip and each fingertip
        let joints = handPose.joints
        
        if let thumbTip = joints[.thumbTip]?.position {
            var touchingAny = false
            var distances: [String: CGFloat] = [:]
            
            // Check distance to each fingertip
            if let indexTip = joints[.indexTip]?.position {
                let distanceValue = distance(from: thumbTip, to: indexTip)
                distances["indexDistance"] = distanceValue
                if distanceValue < 20 { // Threshold for "touching"
                    touchingAny = true
                    feedback.messages.append("Good opposition with index finger")
                }
            }
            
            if let middleTip = joints[.middleTip]?.position {
                let distanceValue = distance(from: thumbTip, to: middleTip)
                distances["middleDistance"] = distanceValue
                if distanceValue < 20 {
                    touchingAny = true
                    feedback.messages.append("Good opposition with middle finger")
                }
            }
            
            if let ringTip = joints[.ringTip]?.position {
                let distanceValue = distance(from: thumbTip, to: ringTip)
                distances["ringDistance"] = distanceValue
                if distanceValue < 20 {
                    touchingAny = true
                    feedback.messages.append("Good opposition with ring finger")
                }
            }
            
            if let littleTip = joints[.littleTip]?.position {
                let distanceValue = distance(from: thumbTip, to: littleTip)
                distances["littleDistance"] = distanceValue
                if distanceValue < 20 {
                    touchingAny = true
                    feedback.messages.append("Good opposition with little finger")
                }
            }
            
            feedback.metrics = distances
            
            if touchingAny {
                feedback.quality = .good
            } else {
                feedback.messages.append("Try to touch your thumb to each fingertip")
                feedback.quality = .needsImprovement
            }
        } else {
            feedback.messages.append("Thumb not properly detected")
            feedback.quality = .cannotDetermine
        }
        
        return feedback
    }
    
    private func analyzeWristRotationExercise(_ handPose: HandPose) -> RSIExerciseFeedback {
        var feedback = RSIExerciseFeedback(exerciseType: .wristRotation)
        
        // For wrist rotation, we want to track the orientation of the hand
        // This is challenging with just 2D video, but we can approximate
        
        // Check if palm is facing camera (fingers spread out horizontally)
        // or side-facing (fingers aligned vertically)
        let joints = handPose.joints
        
        if let indexMCP = joints[.indexMCP]?.position,
           let littleMCP = joints[.littleMCP]?.position,
           let wrist = joints[.wrist]?.position {
            
            // Calculate angle of hand orientation
            let dx = littleMCP.x - indexMCP.x
            let dy = littleMCP.y - indexMCP.y
            let angle = abs(atan2(dy, dx) * 180 / .pi)
            
            feedback.metrics["handOrientation"] = angle
            
            // Horizontal hand (palm facing camera) would have angle close to 0 or 180
            // Vertical hand (side facing camera) would have angle close to 90
            if (angle < 30 || angle > 150) {
                feedback.messages.append("Palm facing camera - good rotation position")
                feedback.quality = .good
            } else if (angle > 60 && angle < 120) {
                feedback.messages.append("Hand on its side - good rotation position")
                feedback.quality = .good
            } else {
                feedback.messages.append("Continue rotating your wrist fully")
                feedback.quality = .needsImprovement
            }
        } else {
            feedback.messages.append("Hand orientation not properly detected")
            feedback.quality = .cannotDetermine
        }
        
        return feedback
    }
    
    // Helper method to calculate distance between points
    private func distance(from point1: CGPoint, to point2: CGPoint) -> CGFloat {
        let dx = point2.x - point1.x
        let dy = point2.y - point1.y
        return sqrt(dx*dx + dy*dy)
    }
    
    // MARK: - Utility Methods
    
    func getHandTracking() -> HandPose? {
        return visionManager?.currentHandPose
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

// MARK: - RSI Exercise Types and Feedback

enum RSIExerciseType: String, CaseIterable {
    case wristExtension = "Wrist Extension"
    case fingerStretch = "Finger Stretch"
    case thumbOpposition = "Thumb Opposition"
    case wristRotation = "Wrist Rotation"
    
    var description: String {
        switch self {
        case .wristExtension:
            return "Extend your wrist upward, keeping your fingers relaxed"
        case .fingerStretch:
            return "Spread your fingers wide apart, then relax"
        case .thumbOpposition:
            return "Touch your thumb to each fingertip in sequence"
        case .wristRotation:
            return "Rotate your wrist in circular motions"
        }
    }
    
    var targetJoints: [HandJointType] {
        switch self {
        case .wristExtension:
            return [.wrist, .middleMCP, .middlePIP, .middleDIP, .middleTip]
        case .fingerStretch:
            return [.indexTip, .middleTip, .ringTip, .littleTip]
        case .thumbOpposition:
            return [.thumbTip, .indexTip, .middleTip, .ringTip, .littleTip]
        case .wristRotation:
            return [.wrist, .indexMCP, .littleMCP]
        }
    }
}

enum ExerciseQuality {
    case good
    case needsImprovement
    case cannotDetermine
    
    var color: Color {
        switch self {
        case .good:
            return .green
        case .needsImprovement:
            return .orange
        case .cannotDetermine:
            return .gray
        }
    }
}

struct RSIExerciseFeedback {
    let exerciseType: RSIExerciseType
    var quality: ExerciseQuality = .cannotDetermine
    var messages: [String] = []
    var metrics: [String: CGFloat] = [:]
    
    init(exerciseType: RSIExerciseType) {
        self.exerciseType = exerciseType
    }
}

// Import SwiftUI for Color
import SwiftUI
