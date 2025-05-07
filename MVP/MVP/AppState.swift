import Foundation
import SwiftUI
import Combine

// MARK: - App State
class AppState: ObservableObject {
    // MARK: - Published Properties
    @Published var hasUserId: Bool = false {
        didSet {
            print("🔄 DEBUG: AppState - hasUserId changed to: \(hasUserId)")
        }
    }
    @Published var userId: String? = nil {
        didSet {
            print("🔄 DEBUG: AppState - userId changed to: \(userId ?? "nil")")
        }
    }
    @Published var currentExercise: Exercise? = nil {
        didSet {
            print("🔄 DEBUG: AppState - currentExercise changed to: \(currentExercise?.name ?? "nil")")
        }
    }
    @Published var isExerciseActive: Bool = false
    @Published var exerciseReport: ExerciseReport? = nil
    @Published var isOnboardingComplete: Bool = false {
        didSet {
            print("🔄 DEBUG: AppState - isOnboardingComplete changed to: \(isOnboardingComplete)")
            // If isOnboardingComplete is true, we now assume that the component
            // that set this flag (e.g., OnboardingView) has already ensured
            // that appState.currentExercise is populated with the correct exercise
            // and that it has been saved to UserDefaults.

            // Therefore, the automatic fetch previously here is removed to avoid
            // potential race conditions or overwriting the correctly set exercise.

            // We can add a check here for debugging purposes:
            if isOnboardingComplete && self.currentExercise == nil {
                print("⚠️ DEBUG: AppState - isOnboardingComplete is true, but currentExercise is nil. This might indicate an issue in the onboarding flow where the exercise was not set before completing onboarding.")
            }
            // printStateFlags() // Optionally log state flags here if needed
        }
    }
    
    // Voice agent states
    @Published var currentAgentType: VoiceAgentType? = nil
    
    // MARK: - Child States
    @Published var voiceState: VoiceState
    @Published var cameraState: CameraState
    @Published var speechState: SpeechState
    @Published var resourceState: ResourceState
    @Published var visionState: VisionState
    
    // MARK: - Private Properties
    private var cancellables = Set<AnyCancellable>()
    
    // MARK: - Initialization
    init() {
        self.voiceState = VoiceState()
        self.cameraState = CameraState()
        self.speechState = SpeechState()
        self.resourceState = ResourceState()
        self.visionState = VisionState()
        
        loadPersistedState()
    }
    
    // MARK: - State Management
    private func loadPersistedState() {
        print("🔄 DEBUG: AppState - Loading persisted state")
        // Load from UserDefaults
        if let storedId = UserDefaults.standard.string(forKey: "UserId") {
            userId = storedId
            hasUserId = true
            print("📱 DEBUG: AppState - Loaded stored user ID: \(storedId)")
        }
        
        // Print all state flags
        printStateFlags()
    }
    
    // Add method to print all state flags
    private func printStateFlags() {
        print("""
        📊 DEBUG: AppState - Current State:
        - hasUserId: \(hasUserId)
        - userId: \(userId ?? "nil")
        - isOnboardingComplete: \(isOnboardingComplete)
        - currentExercise: \(currentExercise?.name ?? "nil")
        """)
    }
    
    // MARK: - State Updates
    func updateUserId(_ id: String) {
        print("🔄 DEBUG: AppState - Updating user ID to: \(id)")
        userId = id
        hasUserId = true
        UserDefaults.standard.set(id, forKey: "UserId")
        
        printStateFlags()
    }
    
    func setCurrentExercise(_ exercise: Exercise) {
        print("🔄 DEBUG: AppState - Setting current exercise to: \(exercise.name)")
        DispatchQueue.main.async { [weak self] in
            self?.currentExercise = exercise
        }
    }
    
    func setExerciseReport(_ report: ExerciseReport) {
        exerciseReport = report
    }
    
    // MARK: - Cleanup
    func cleanup() {
        voiceState.cleanup()
        cameraState.cleanup()
        speechState.cleanup()
        resourceState.cleanup()
        visionState.cleanup()
    }
}

// MARK: - Voice Agent Type Enum (for internal AppState usage)
enum VoiceAgentType {
    case onboarding
    case exerciseCoach
}

// MARK: - Exercise Report Model
struct ExerciseReport: Codable, Identifiable {
    let id: String
    let generalFeeling: String
    let performanceQuality: String
    let painReport: String
    let completed: Bool
    let setsCompleted: Int
    let repsCompleted: Int
    let dayStreak: Int
    let motivationalMessage: String
    let date: Date
    
    static var placeholder: ExerciseReport {
        return ExerciseReport(
            id: UUID().uuidString,
            generalFeeling: "You seemed comfortable throughout the session.",
            performanceQuality: "Good form maintained for most repetitions.",
            painReport: "No significant pain reported during the exercise.",
            completed: true,
            setsCompleted: 3,
            repsCompleted: 10,
            dayStreak: 1,
            motivationalMessage: "Great job completing your exercise! Keep it up to continue your progress.",
            date: Date()
        )
    }
}

// Child states remain largely the same as your original code
class VoiceState: ObservableObject {
    @Published var isSpeaking = false
    @Published var isListening = false
    @Published var lastSpokenText: String = ""
    @Published var voiceError: String?
    
    func cleanup() {
        isSpeaking = false
        isListening = false
        lastSpokenText = ""
        voiceError = nil
    }
}

class CameraState: ObservableObject {
    @Published var isSessionRunning = false
    @Published var isCameraAuthorized = false
    @Published var cameraError: String?
    
    func cleanup() {
        isSessionRunning = false
        isCameraAuthorized = false
        cameraError = nil
    }
}

class SpeechState: ObservableObject {
    @Published var isListening = false
    @Published var recognizedText = ""
    @Published var isSpeechAuthorized = false
    @Published var speechError: String?
    
    func cleanup() {
        isListening = false
        recognizedText = ""
        isSpeechAuthorized = false
        speechError = nil
    }
}

class ResourceState: ObservableObject {
    @Published var isInitialized = false
    @Published var isCleaningUp = false
    @Published var error: String?
    
    func cleanup() {
        isInitialized = false
        isCleaningUp = false
        error = nil
    }
}

class VisionState: ObservableObject {
    @Published var currentPose = BodyPose()
    @Published var isProcessing = false
    @Published var error: String?
    
    func cleanup() {
        currentPose = BodyPose()
        isProcessing = false
        error = nil
    }
}
