import SwiftUI
import AVFoundation

struct OnboardingView: View {
    // State for animation and conversation
    @State private var animationState: AnimationState = .idle
    @State private var messages: [ConversationMessage] = []
    @State private var isOnboardingComplete = false
    @State private var isLoading = false
    @State private var hasStartedAgent = false
    
    // Environment objects
    @EnvironmentObject var appState: AppState
    @EnvironmentObject private var voiceManager: VoiceManager
    @EnvironmentObject private var resourceCoordinator: ResourceCoordinator
    
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
                // Reset button
                HStack {
                    Spacer()
                    Button(action: resetOnboarding) {
                        Image(systemName: "arrow.counterclockwise.circle.fill")
                            .font(.title2)
                            .foregroundColor(.blue)
                    }
                    .padding(.trailing)
                }
                
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
            if completed && !isOnboardingComplete {
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
                animationState = .thinking
                addMessage(text: "Thanks for sharing that information. I'm generating personalized exercises for you now...", isUser: false)
            }
        }
        
        // Listen for when exercises are generated
        NotificationCenter.default.addObserver(
            forName: VoiceManager.exercisesGeneratedNotification,
            object: nil,
            queue: .main
        ) { notification in
            handleExercisesGenerated()
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
        guard !isOnboardingComplete else { 
            print("⚠️ DEBUG: OnboardingView - handleOnboardingComplete called but isOnboardingComplete is already true")
            return 
        }
        
        print("🎯 DEBUG: OnboardingView - Starting onboarding completion process")
        
        // End the ElevenLabs session
        voiceManager.endElevenLabsSession()
        
        // Small delay to allow session to properly end and cleanup
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
            print("🎯 DEBUG: OnboardingView - Setting completion states")
            self.isOnboardingComplete = true
            self.appState.isOnboardingComplete = true
            
            // Additional cleanup
            self.animationState = .idle
            self.voiceManager.hasCompletedOnboarding = true
            
            print("✅ DEBUG: OnboardingView - Onboarding completion process finished")
        }
    }
    
    private func resetOnboarding() {
        print("🔄 DEBUG: OnboardingView - Resetting onboarding")
        
        // Reset VoiceManager state
        voiceManager.resetOnboarding()
        
        // Reset AppState
        appState.hasUserId = false
        appState.userId = nil
        appState.isOnboardingComplete = false
        appState.currentExercise = nil
        
        // Reset local view state
        isOnboardingComplete = false
        hasStartedAgent = false
        messages.removeAll()
        animationState = .idle
        
        // Restart onboarding agent after a short delay
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
            voiceManager.startOnboardingAgent()
            appState.currentAgentType = .onboarding
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
