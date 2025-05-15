import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var appState: AppState
    
    // Environment objects
    @EnvironmentObject private var voiceManager: VoiceManager
    @EnvironmentObject private var cameraManager: CameraManager
    @EnvironmentObject private var resourceCoordinator: ResourceCoordinator
    @EnvironmentObject private var visionManager: VisionManager
    @EnvironmentObject private var notificationManager: NotificationManager
    @EnvironmentObject private var userManager: UserManager
    
    // Add state to track changes
    @State private var shouldShowExerciseDetail: Bool = false
    @State private var showingNotificationSettings: Bool = false
    
    var body: some View {
        Group {
            // Primary condition: Is onboarding complete and do we have an exercise?
            if appState.isOnboardingComplete, let exercise = appState.currentExercise {
                ExerciseDetailView(exercise: exercise)
                    .environmentObject(appState)
                    .environmentObject(voiceManager)
                    .environmentObject(cameraManager)
                    .environmentObject(resourceCoordinator)
                    .environmentObject(visionManager)
                    .environmentObject(notificationManager)
                    .environmentObject(userManager)
                    .transition(.opacity)
            } else {
                // If onboarding is not complete, always show OnboardingView.
                // Exercise loading for users who completed onboarding previously but app restarted
                // will be handled by onAppear logic or if currentExercise gets populated by other means.
                OnboardingView()
                    .environmentObject(appState)
                    .environmentObject(voiceManager)
                    .environmentObject(cameraManager)
                    .environmentObject(resourceCoordinator)
                    .environmentObject(visionManager)
                    .environmentObject(notificationManager)
                    // Pass userManager to OnboardingView if it needs it directly
                    // (It currently accesses UserManager.shared, but explicit passing is good practice if direct interaction is needed)
                    .environmentObject(userManager) 
            }
        }
        .onChange(of: appState.isOnboardingComplete) { complete in // Keep this for loading exercises for returning users
            if complete && appState.userId != nil && appState.currentExercise == nil {
                print("🔄 DEBUG: ContentView - Onboarding complete, userId available, but no exercise. Loading exercise.")
                loadRecommendedExercise(userId: appState.userId!)
            }
        }
        .onAppear {
            // Check for existing user on appear
            if let userId = UserDefaults.standard.string(forKey: "UserId") { // Assuming "UserId" is the key used by AppState/UserManager
                // Ensure AppState is updated. UserManager might already do this.
                if appState.userId == nil {
                    appState.updateUserId(userId) // Ensure AppState has it if not already set by UserManager
                }
                
                // If onboarding was already completed and we have a user ID, but no current exercise (e.g., app restart)
                if UserDefaults.standard.bool(forKey: "OnboardingComplete") && appState.currentExercise == nil { // Check persisted onboarding completion
                     print("🔄 DEBUG: ContentView.onAppear - Returning user, onboarding was complete. Loading exercise.")
                    loadRecommendedExercise(userId: userId)
                } else if appState.currentExercise != nil {
                    // If onboarding is marked complete in AppState and exercise exists, the main body handles it.
                    // If onboarding is NOT marked complete in AppState, OnboardingView will show.
                    print("🔄 DEBUG: ContentView.onAppear - State will be handled by main body logic.")
                }
            } else {
                print("🔄 DEBUG: ContentView.onAppear - No existing user ID found in UserDefaults.")
            }
        }
//        .sheet(isPresented: $showingNotificationSettings) {
//            NotificationSettingsView()
//                .environmentObject(notificationManager)
//        }
    }
    
    private func loadRecommendedExercise(userId: String) {
        print("🎯 DEBUG: ContentView - Loading recommended exercise for user: \(userId)")
        
        APIService.getRecommendedExercise(userId: userId) { result in
            DispatchQueue.main.async {
                switch result {
                case .success(let exercise):
                    print("✅ DEBUG: ContentView - Successfully loaded exercise: \(exercise.name)")
                    appState.setCurrentExercise(exercise)
                case .failure(let error):
                    print("⚠️ DEBUG: ContentView - Error loading exercise: \(error)")
                    // appState.setCurrentExercise(Exercise.fallbackExercise)
                }
            }
        }
    }
}

// API Service class for network calls
class APIService {
    static func getRecommendedExercise(userId: String, completion: @escaping (Result<Exercise, Error>) -> Void) {
        print("🎯 DEBUG: APIService - Attempting to load exercises from UserDefaults for user: \(userId)")
        
        // Try to load exercises from UserDefaults first
        if let exercisesData = UserDefaults.standard.data(forKey: "UserExercises") {
            print("📱 DEBUG: APIService - Found exercises data in UserDefaults, size: \(exercisesData.count) bytes")
            
            do {
                if let exercisesArray = try JSONSerialization.jsonObject(with: exercisesData) as? [[String: Any]] {
                    print("✅ DEBUG: APIService - Successfully parsed exercises array, count: \(exercisesArray.count)")
                    
                    if let exerciseJson = exercisesArray.first {
                        print("📝 DEBUG: APIService - Exercise JSON structure:")
                        exerciseJson.forEach { key, value in
                            print("  - \(key): \(value)")
                        }
                        
                        // Convert JSON to Exercise object
                        let exercise = Exercise(
                            id: UUID(uuidString: exerciseJson["id"] as? String ?? UUID().uuidString) ?? UUID(),
                            name: exerciseJson["name"] as? String ?? "Unknown Exercise",
                            description: exerciseJson["description"] as? String ?? "No description available",
                            imageURLString: exerciseJson["imageURL"] as? String,
                            imageURLString1: exerciseJson["imageURL1"] as? String,
                            duration: TimeInterval(exerciseJson["duration"] as? Int ?? 180),
                            targetJoints: (exerciseJson["targetJoints"] as? [String])?.compactMap { BodyJointType(rawValue: $0) } ?? [],
                            instructions: exerciseJson["instructions"] as? [String] ?? [],
                            firestoreId: exerciseJson["firestoreId"] as? String,
                            videoURL: (exerciseJson["videoURL"] as? String).flatMap { URL(string: $0) }
                        )
                        
                        print("✅ DEBUG: APIService - Successfully created Exercise object:")
                        print("  - ID: \(exercise.id)")
                        print("  - Name: \(exercise.name)")
                        print("  - Description: \(exercise.description)")
                        print("  - Target Joints: \(exercise.targetJoints.map { $0.rawValue })")
                        print("  - Instructions count: \(exercise.instructions.count)")
                        
                        completion(.success(exercise))
                        return
                    } else {
                        print("⚠️ DEBUG: APIService - No exercises found in array")
                    }
                } else {
                    print("⚠️ DEBUG: APIService - Failed to parse exercises array")
                }
            } catch {
                print("⚠️ DEBUG: APIService - Error parsing exercises data: \(error)")
            }
        } else {
            print("⚠️ DEBUG: APIService - No exercises data found in UserDefaults")
        }
        
        print("ℹ️ DEBUG: APIService - Using fallback exercise")
        //completion(.success(Exercise.fallbackExercise))
        let error = NSError(domain: "APIService", code: 1001, userInfo: [NSLocalizedDescriptionKey: "No exercise data found"])
        completion(.failure(error))
    }
} 
