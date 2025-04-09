import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var appState: AppState
    
    // Environment objects
    @EnvironmentObject private var voiceManager: VoiceManager
    @EnvironmentObject private var cameraManager: CameraManager
    @EnvironmentObject private var resourceCoordinator: ResourceCoordinator
    @EnvironmentObject private var visionManager: VisionManager
    
    var body: some View {
        ZStack {
            if appState.hasUserId {
                // Returning user - Go directly to most recommended exercise
                if let currentExercise = appState.currentExercise {
                    ExerciseDetailView(exercise: currentExercise)
                        .environmentObject(appState)
                        .environmentObject(voiceManager)
                        .environmentObject(cameraManager)
                        .environmentObject(resourceCoordinator)
                        .environmentObject(visionManager)
                        .transition(.opacity)
                } else {
                    // Loading state while fetching current exercise
                    ProgressView("Loading your exercise...")
                        .onAppear {
                            loadRecommendedExercise()
                        }
                }
            } else {
                // New user - Show onboarding
                OnboardingView()
                    .environmentObject(appState)
                    .environmentObject(voiceManager)
                    .environmentObject(cameraManager)
                    .environmentObject(resourceCoordinator)
                    .environmentObject(visionManager)
                    .transition(.opacity)
            }
        }
        .onAppear {
            // Check if user ID exists in UserDefaults
            if let userId = UserDefaults.standard.string(forKey: "PatientID") {
                appState.userId = userId
                appState.hasUserId = true
                loadRecommendedExercise()
            }
        }
    }
    
    private func loadRecommendedExercise() {
        guard let userId = appState.userId else { return }
        
        // Make API call to get recommended exercise
        APIService.getRecommendedExercise(userId: userId) { result in
            DispatchQueue.main.async {
                switch result {
                case .success(let exercise):
                    appState.currentExercise = exercise
                case .failure(let error):
                    // Create a fallback exercise if API fails
                    print("Error loading recommended exercise: \(error)")
                    appState.currentExercise = Exercise.fallbackExercise
                }
            }
        }
    }
}

// API Service class for network calls
class APIService {
    static func getRecommendedExercise(userId: String, completion: @escaping (Result<Exercise, Error>) -> Void) {
        // Implement API call to get recommended exercise
        // This would call your generate_exercises cloud function
        
        // For now, return a fallback exercise after a delay to simulate network call
        DispatchQueue.global().asyncAfter(deadline: .now() + 1.0) {
            completion(.success(Exercise.fallbackExercise))
        }
    }
}

// Add fallback exercise to Exercise model
extension Exercise {
    static var fallbackExercise: Exercise {
        return Exercise(
            id: UUID(),
            name: "Knee Flexion",
            description: "Improve range of motion in your knee joint",
            imageURLString: "https://example.com/knee-flexion.mp4",
            duration: 180,
            targetJoints: [.leftKnee, .rightKnee],
            instructions: [
                "Sit on a chair with your feet flat on the floor",
                "Slowly lift your right foot and bend your knee",
                "Hold for 5 seconds",
                "Slowly lower your foot back to the floor",
                "Repeat 10 times"
            ]
        )
    }
}
