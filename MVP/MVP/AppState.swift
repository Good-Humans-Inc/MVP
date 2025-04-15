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
            if isOnboardingComplete {
                // When onboarding completes, ensure we load the exercise
                DispatchQueue.main.async { [weak self] in
                    if let userId = self?.userId {
                        print("🔄 DEBUG: AppState - Triggering exercise load after onboarding completion")
                        APIService.getRecommendedExercise(userId: userId) { result in
                            DispatchQueue.main.async {
                                switch result {
                                case .success(let exercise):
                                    print("✅ DEBUG: AppState - Successfully loaded exercise after onboarding")
                                    self?.currentExercise = exercise
                                case .failure(let error):
                                    print("⚠️ DEBUG: AppState - Failed to load exercise after onboarding: \(error)")
                                    self?.currentExercise = Exercise.fallbackExercise
                                }
                            }
                        }
                    }
                }
            }
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
    
    // Add flag to track first exercise
    @Published var isFirstExercise: Bool = true
    
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
        if let storedId = UserDefaults.standard.string(forKey: "UserID") {
            userId = storedId
            hasUserId = true
            print("📱 DEBUG: AppState - Loaded stored user ID: \(storedId)")
        }
        
        // Load first exercise flag
        isFirstExercise = UserDefaults.standard.bool(forKey: "IsFirstExercise")
        print("📱 DEBUG: AppState - Loaded isFirstExercise: \(isFirstExercise)")
    }
    
    // MARK: - State Updates
    func updateUserId(_ id: String) {
        print("🔄 DEBUG: AppState - Updating user ID to: \(id)")
        userId = id
        hasUserId = true
        UserDefaults.standard.set(id, forKey: "UserID")
        
        // When setting user ID, ensure first exercise flag is true
        isFirstExercise = true
        UserDefaults.standard.set(true, forKey: "IsFirstExercise")
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
    
    // Add method to mark exercise as completed
    func markExerciseCompleted() {
        isFirstExercise = false
        UserDefaults.standard.set(false, forKey: "IsFirstExercise")
        print("📱 DEBUG: AppState - Marked exercise as completed, isFirstExercise: \(isFirstExercise)")
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
    case firstExercise
    case exercise
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
