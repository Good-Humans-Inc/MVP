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
            // Simplify the decision tree to reduce potential race conditions
            if let exercise = appState.currentExercise {
                ExerciseDetailView(exercise: exercise)
                    .environmentObject(appState)
                    .environmentObject(voiceManager)
                    .environmentObject(cameraManager)
                    .environmentObject(resourceCoordinator)
                    .environmentObject(visionManager)
                    .environmentObject(notificationManager)
                    .environmentObject(userManager)
                    .transition(.opacity)
            } else if appState.isOnboardingComplete || appState.hasUserId {
                // If onboarding is complete or we have a user ID, show loading with exercise fetch
                ProgressView("Generating your exercise...")
                    .onAppear {
                        if let userId = appState.userId {
                            loadRecommendedExercise(userId: userId)
                        }
                    }
            } else {
                // Otherwise show onboarding
                OnboardingView()
                    .environmentObject(appState)
                    .environmentObject(voiceManager)
                    .environmentObject(cameraManager)
                    .environmentObject(resourceCoordinator)
                    .environmentObject(visionManager)
                    .environmentObject(notificationManager)
            }
        }
        .onChange(of: appState.currentExercise) { exercise in
            if exercise != nil {
                print("🔄 DEBUG: ContentView - Exercise loaded, setting shouldShowExerciseDetail to true")
                shouldShowExerciseDetail = true
            }
        }
        .onChange(of: appState.isOnboardingComplete) { complete in
            if complete && appState.userId != nil {
                print("🔄 DEBUG: ContentView - Onboarding complete with userId, loading exercise")
                loadRecommendedExercise(userId: appState.userId!)
            }
        }
        .onAppear {
            // Check for existing user on appear
            if let userId = UserDefaults.standard.string(forKey: "UserId") {
                appState.userId = userId
                appState.hasUserId = true
                
                // If we already have an exercise, show it
                if appState.currentExercise != nil {
                    shouldShowExerciseDetail = true
                } else {
                    // Otherwise load it
                    loadRecommendedExercise(userId: userId)
                }
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

// Add fallback exercise to Exercise model
extension Exercise {
    static var fallbackExercise: Exercise {
        return Exercise(
            id: UUID(),
            name: "Wrist Rotation",
            description: "Gentle wrist rotations to improve flexibility and mobility",
            imageURLString: nil,
            imageURLString1: nil,
            duration: 180,
            targetJoints: [.leftWrist,.rightWrist],
            instructions: [
                "Start with your arm extended forward",
                "Rotate your wrist clockwise slowly 5 times",
                "Then rotate counterclockwise 5 times",
                "Keep movements smooth and controlled",
                "Repeat with the other wrist"
            ],
            videoURL: URL(string: "https://storage.googleapis.com/mvp-vids/wrist_rotation.mp4")
        )
    }
} 
