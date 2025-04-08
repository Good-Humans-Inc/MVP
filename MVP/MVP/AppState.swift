import Foundation
import SwiftUI
import Combine

// MARK: - App State
class AppState: ObservableObject {
    // MARK: - Published Properties
    @Published var hasUserId: Bool = false
    @Published var userId: String? = nil
    @Published var currentExercise: Exercise? = nil
    @Published var isExerciseActive: Bool = false
    @Published var exerciseReport: ExerciseReport? = nil
    
    // Voice agent states
    @Published var currentAgentType: AgentType = .none
    
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
        // Load from UserDefaults
        if let storedId = UserDefaults.standard.string(forKey: "PatientID") {
            userId = storedId
            hasUserId = true
        }
    }
    
    // MARK: - State Updates
    func updateUserId(_ id: String) {
        userId = id
        hasUserId = true
        UserDefaults.standard.set(id, forKey: "PatientID")
    }
    
    func setCurrentExercise(_ exercise: Exercise) {
        currentExercise = exercise
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

// MARK: - Agent Type Enum
enum AgentType {
    case none
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
