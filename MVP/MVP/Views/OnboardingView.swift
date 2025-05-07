import SwiftUI
import AVFoundation

struct OnboardingView: View {
    // State for animation and conversation
    @State private var animationState: AnimationState = .idle
    @State private var messages: [ConversationMessage] = []
    @State private var isLoading = false
    @State private var hasStartedAgent = false
    
    // Environment objects
    @EnvironmentObject var appState: AppState
    @EnvironmentObject private var voiceManager: VoiceManager
    @EnvironmentObject private var resourceCoordinator: ResourceCoordinator
    @EnvironmentObject private var cameraManager: CameraManager
    @EnvironmentObject private var visionManager: VisionManager
    @EnvironmentObject private var notificationManager: NotificationManager
    @EnvironmentObject private var userManager: UserManager
    
    enum AnimationState {
        case idle, listening, speaking, thinking
    }
    
    struct ConversationMessage: Identifiable, Equatable {
        let id = UUID()
        let text: String
        let isUser: Bool
        let timestamp = Date()
    }
    
    var body: some View {
        ZStack {
            // Background
            Color(UIColor.systemBackground)
                .edgesIgnoringSafeArea(.all)
            
            VStack(spacing: 20) {
                // Debug info for NotificationManager
//                Text("NotificationManager Status: \(notificationManager.isAuthorized ? "Available" : "Not Available")")
//                    .font(.caption)
//                    .foregroundColor(.secondary)
//                    .padding(.top)
//                
//                // Reset button
//                HStack {
//                    Spacer()
//                    Button(action: resetOnboarding) {
//                        Image(systemName: "arrow.counterclockwise.circle.fill")
//                            .font(.title2)
//                            .foregroundColor(.blue)
//                    }
//                    .padding(.trailing)
//                }
                
                // Pep animation (renamed from Dog animation)
                PepAnimation(state: $animationState)
                    .frame(width: 200, height: 200)
                
                // Conversation messages
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(spacing: 12) {
                            ForEach(messages) { message in
                                ConversationBubble(message: message)
                                    .id(message.id)
                            }
                        }
                        .padding(.horizontal)
                    }
                    .frame(maxWidth: .infinity)
                    .background(Color(.systemBackground))
                    .onChange(of: messages) { newMessages in
                        if let lastMessage = newMessages.last {
                            withAnimation {
                                proxy.scrollTo(lastMessage.id, anchor: .bottom)
                            }
                        }
                    }
                }
                
                // Voice activity indicator
                HStack {
                    Circle()
                        .fill(animationState == .listening ? Color.green : Color.gray)
                        .frame(width: 10, height: 10)
                    
                    Text(animationState == .listening ? "Listening..." :
                         (animationState == .speaking ? "Speaking..." : "Tap to start"))
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .padding(.top, 5)
                .padding(.bottom, 10)
                
                // Loading indicator
                if isLoading {
                    ProgressView("Processing...")
                        .padding()
                }
            }
            .padding()
        }
        .onAppear {
            // Set up notification observers
            setupNotificationObservers()
            
            // Configure audio session to use speaker
            configureAudioSession()
            
            // Start the ElevenLabs onboarding agent
            if !hasStartedAgent {
                hasStartedAgent = true
                voiceManager.startOnboardingAgent()
                appState.currentAgentType = .onboarding
                print("Called voiceManager.startOnboardingAgent()")
            }
            
            // Start with initial greeting
            DispatchQueue.main.asyncAfter(deadline: .now() + 1) {
                animationState = .speaking
            }
        }
        .onDisappear {
            // Clean up notification observers
            removeNotificationObservers()
        }
        // Handle voiceManager.isSpeaking changes
        .onChange(of: voiceManager.isSpeaking) { isSpeaking in
            animationState = isSpeaking ? .speaking : .listening
        }
        // Handle voiceManager.isListening changes
        .onChange(of: voiceManager.isListening) { isListening in
            if isListening && !voiceManager.isSpeaking {
                animationState = .listening
            }
        }
        // Handle voiceManager.lastSpokenText changes (AI messages)
        .onChange(of: voiceManager.lastSpokenText) { newText in
            if !newText.isEmpty {
                addMessage(text: newText, isUser: false)
            }
        }
        // Handle voiceManager.transcribedText changes (user messages)
        .onChange(of: voiceManager.transcribedText) { newText in
            if !newText.isEmpty {
                addMessage(text: newText, isUser: true)
            }
        }
        // Handle voiceManager.hasCompletedOnboarding changes
        .onChange(of: voiceManager.hasCompletedOnboarding) { completed in
            if completed && !appState.isOnboardingComplete {
                handleOnboardingComplete()
            }
        }
    }
    
    // MARK: - Helper Methods
    
    private func setupNotificationObservers() {
        // Listen for when user ID is received
        NotificationCenter.default.addObserver(
            forName: VoiceManager.userIdReceivedNotification,
            object: nil,
            queue: .main
        ) { notification in
            if let userId = notification.userInfo?["user_id"] as? String {
                self.appState.updateUserId(userId)
                self.animationState = .thinking
                self.addMessage(text: "Thanks for sharing that information. I'm generating personalized exercises for you now...", isUser: false)
                
                // Update timezone information first
                print("🕒 OnboardingView: Checking and updating timezone information")
                let userManager = UserManager.shared
                print("🕒 OnboardingView: User ID for timezone update: \(userId)")
                userManager.checkAndUpdateTimezoneIfNeeded()
                
                // Force an immediate timezone update regardless of cache
                let currentOffset = TimeZone.current.secondsFromGMT() / 3600
                let currentOffsetString = String(currentOffset)
                print("🕒 OnboardingView: Forcing timezone update with offset: \(currentOffsetString)")
                // Call the public method directly now
                userManager.updateTimezoneOnServer(userId: userId, timezone: currentOffsetString)
                
                // Update FCM token with the new user ID
                self.notificationManager.getFCMToken { token in
                    if let token = token {
                        print("✅ Re-syncing FCM token after user ID received: \(token)")
                        self.notificationManager.updateFCMTokenInBackend(token: token)
                    }
                }
            }
        }
        
        // Listen for when exercises are generated
        NotificationCenter.default.addObserver(
            forName: VoiceManager.exercisesGeneratedNotification,
            object: nil,
            queue: .main
        ) { notification in
            print("🎯 DEBUG: OnboardingView - exercisesGeneratedNotification received")
            
            // --- DETAILED LOGGING FOR USERINFO ---
            print("🔍 RAW UserInfo from notification: \(notification.userInfo ?? [:])")
            if let rawExerciseData = notification.userInfo?["exerciseJson"] {
                print("🔍 Type of object for key 'exerciseJson': \(type(of: rawExerciseData))")
            } else {
                print("🔍 Key 'exerciseJson' not found in userInfo.")
            }
            // --- END DETAILED LOGGING ---

            // 1. Extract the exerciseJson from the notification
            guard let exerciseJson = notification.userInfo?["exerciseJson"] as? [String: Any] else {
                print("⚠️ DEBUG: OnboardingView - exercisesGeneratedNotification did not contain valid exerciseJson. UserInfo dump above should clarify.")
                // Handle this error appropriately
                self.isLoading = false // Use self directly
                self.addMessage(text: "Sorry, I couldn't prepare your exercise. Please try restarting.", isUser: false) // Use self directly
                return
            }

            // --- PRINT PARSED EXERCISEJSON ---
            print("✅ PROCESSED exerciseJson: \(exerciseJson)")
            // --- END PRINT ---

            // 2. Convert exerciseJson to an Exercise object
            //    (Ensure keys like imageURL, videoURL, targetJoints match your backend's JSON structure)
            let newExercise = Exercise(
                id: UUID(uuidString: exerciseJson["id"] as? String ?? UUID().uuidString) ?? UUID(),
                name: exerciseJson["name"] as? String ?? "Unknown Exercise",
                description: exerciseJson["description"] as? String ?? "No description available",
                imageURLString: exerciseJson["imageURL"] as? String, // Or "image_url" etc.
                imageURLString1: exerciseJson["imageURL1"] as? String, // Or "image_url1" etc.
                duration: TimeInterval(exerciseJson["duration"] as? Int ?? 180),
                targetJoints: (exerciseJson["targetJoints"] as? [String])?.compactMap { BodyJointType(rawValue: $0) } ?? [],
                instructions: exerciseJson["instructions"] as? [String] ?? [],
                firestoreId: exerciseJson["firestoreId"] as? String ?? exerciseJson["id"] as? String, // Prefer firestoreId, fallback to id
                videoURL: (exerciseJson["videoURL"] as? String).flatMap { URL(string: $0) } // Or "video_url" etc.
            )

            print("✅ DEBUG: OnboardingView - Successfully parsed new exercise: \(newExercise.name)")

            // 3. Set this new exercise in AppState
            self.appState.setCurrentExercise(newExercise) // Use self directly

            // 4. IMPORTANT: Save this new exercise (original JSON) to UserDefaults
            //    The structure must match what APIService.getRecommendedExercise expects (an array of exercises).
            let exercisesArrayToSave = [exerciseJson]
            if let dataToSave = try? JSONSerialization.data(withJSONObject: exercisesArrayToSave) {
                UserDefaults.standard.set(dataToSave, forKey: "UserExercises")
                print("✅ DEBUG: OnboardingView - New exercise (JSON) saved to UserDefaults for APIService compatibility.")
            } else {
                print("⚠️ DEBUG: OnboardingView - Failed to serialize new exercise JSON for UserDefaults.")
                // Consider how to handle this; if UserDefaults saving fails, subsequent cold starts
                // might not pick up the exercise until a new one is generated or fetched.
                // For now, we'll proceed as appState.currentExercise is set.
            }

            // 5. Now call your existing handleExercisesGenerated() or similar logic
            self.handleExercisesGenerated() // Use self directly
        }
    }
    
    private func removeNotificationObservers() {
        NotificationCenter.default.removeObserver(self, name: VoiceManager.userIdReceivedNotification, object: nil)
        NotificationCenter.default.removeObserver(self, name: VoiceManager.exercisesGeneratedNotification, object: nil)
    }
    
    private func configureAudioSession() {
        do {
            try AVAudioSession.sharedInstance().setCategory(.playAndRecord, options: [.defaultToSpeaker, .allowBluetooth])
            try AVAudioSession.sharedInstance().setActive(true, options: .notifyOthersOnDeactivation)
        } catch {
            print("Failed to configure audio session: \(error)")
        }
    }
    
    private func addMessage(text: String, isUser: Bool) {
        print("Adding message: \(text), isUser: \(isUser)")
        let message = ConversationMessage(text: text, isUser: isUser)
        messages.append(message)
        
        // Set audio to speaker
        do {
            if !voiceManager.isBluetoothConnected {
                try AVAudioSession.sharedInstance().overrideOutputAudioPort(.speaker)
            } else {
                try AVAudioSession.sharedInstance().setCategory(.playAndRecord,
                                          mode: .spokenAudio,
                                          options: [.allowBluetooth])
                try AVAudioSession.sharedInstance().overrideOutputAudioPort(.none)
            }
        } catch {
            print("Audio session error: \(error)")
        }
    }
    
    private func handleExercisesGenerated() {
        print("🎯 DEBUG: OnboardingView - Exercises generated notification received")
        isLoading = false
        addMessage(text: "Your personalized exercise is ready! Let's get started with your recovery journey.", isUser: false)
        
        // Wait a moment to show the message before proceeding
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) {
            handleOnboardingComplete()
        }
    }
    
    private func handleOnboardingComplete() {
        print("🎯 DEBUG: OnboardingView - Handling onboarding completion")
        print("📱 DEBUG: NotificationManager availability check:")
        print("- Is NotificationManager initialized: \(notificationManager != nil)")
        print("- Is NotificationManager authorized: \(notificationManager.isAuthorized)")
        
        // Get FCM token
        notificationManager.getFCMToken { token in
            if let token = token {
                print("✅ FCM Token obtained after onboarding: \(token)")
            } else {
                print("⚠️ Failed to get FCM token after onboarding")
            }
        }
        
        // End the onboarding session
        voiceManager.endElevenLabsSession()
        
        // Small delay to allow session to properly end and cleanup
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
                    print("🎯 DEBUG: OnboardingView - Setting completion states")
                    
                    // Set completion state in AppState
                    self.appState.isOnboardingComplete = true
                    
                    // Additional cleanup
                    self.animationState = .idle
                    
                    print("📊 DEBUG: OnboardingView - Post-completion state:")
                    print("- appState.isOnboardingComplete: \(self.appState.isOnboardingComplete)")
                    print("- appState.hasUserId: \(self.appState.hasUserId)")
                    
                    // Ensure we have an exercise before transitioning
                    if let exercise = self.appState.currentExercise {
                        print("✅ DEBUG: OnboardingView - Transitioning to ExerciseDetailView with exercise: \(exercise.name)")
                        
                        // Transition to ExerciseDetailView with all required environment objects
                        if let window = UIApplication.shared.windows.first {
                            window.rootViewController = UIHostingController(rootView:
                                ExerciseDetailView(exercise: exercise)
                                    .environmentObject(self.appState)
                                    .environmentObject(self.voiceManager)
                                    .environmentObject(self.resourceCoordinator)
                                    .environmentObject(self.cameraManager)
                                    .environmentObject(self.visionManager)
                                    .environmentObject(self.userManager)
                            )
                        }
                    } else {
                        print("⚠️ DEBUG: OnboardingView - No exercise available for transition")
                    }
                    
                    print("✅ DEBUG: OnboardingView - Onboarding completion process finished")
                }
            }
    
    private func resetOnboarding() {
        print("🎯 DEBUG: OnboardingView - Resetting onboarding")
        
        // Pre-reset state:
        print("- appState.hasUserId: \(appState.hasUserId)")
        print("- appState.isOnboardingComplete: \(appState.isOnboardingComplete)")
        
        // Resetting onboarding state
        print("Resetting onboarding state")
        
        // First check if we have an active session to end 
        if !voiceManager.isSessionActive {
            print("No active ElevenLabs session to end")
        } else {
            voiceManager.endElevenLabsSession()
        }
        
        // Reset local state
        self.hasStartedAgent = false
        self.messages = []
        self.animationState = .idle
        
        // Reset the AppState (this ensures we don't create a retain cycle)
        DispatchQueue.main.async {
            // Update AppState properties safely
            self.appState.hasUserId = false
            self.appState.userId = nil
            self.appState.isOnboardingComplete = false
            
            // Clear notification badge (safely)
            if self.notificationManager.isAuthorized {
                self.notificationManager.clearBadge()
                print("Notification badge cleared during reset")
            } else {
                print("Notification manager not authorized - skipping badge clear")
            }
            
            // Clear any user defaults related to onboarding
            UserDefaults.standard.removeObject(forKey: "UserId")
            UserDefaults.standard.removeObject(forKey: "OnboardingComplete")
            
            // IMPORTANT: DO NOT RECREATE THE VIEW HIERARCHY - instead restart the agent
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                // Start fresh with onboarding agent
                self.voiceManager.startOnboardingAgent()
                self.appState.currentAgentType = .onboarding
                self.hasStartedAgent = true
                print("Restarted onboarding agent")
            }
        }
    }
}

// MARK: - Conversation Bubble Component

struct ConversationBubble: View {
    let message: OnboardingView.ConversationMessage
    
    var body: some View {
        HStack {
            if message.isUser {
                Spacer()
            }
            
            VStack(alignment: message.isUser ? .trailing : .leading, spacing: 4) {
                Text(message.text)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                    .background(message.isUser ? Color.blue : Color(.systemGray5))
                    .foregroundColor(message.isUser ? .white : .primary)
                    .cornerRadius(18)
                    .multilineTextAlignment(message.isUser ? .trailing : .leading)
                
                Text(timeString(from: message.timestamp))
                    .font(.caption2)
                    .foregroundColor(.secondary)
                    .padding(.horizontal, 8)
            }
            
            if !message.isUser {
                Spacer()
            }
        }
        .padding(.horizontal, 4)
    }
    
    private func timeString(from date: Date) -> String {
        let formatter = DateFormatter()
        formatter.timeStyle = .short
        return formatter.string(from: date)
    }
}
