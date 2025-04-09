import SwiftUI
import AVFoundation

struct OnboardingView: View {
    // State for animation and conversation
    @State private var animationState: AnimationState = .idle
    @State private var messages: [ConversationMessage] = []
    @State private var isOnboardingComplete = false
    @State private var isLoading = false
    @State private var hasStartedAgent = false
    
    // Scroll view reader
    @State private var scrollToBottom = false
    
    // Environment objects
    @EnvironmentObject private var appState: AppState
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
            
            // Main content
            VStack(spacing: 20) {
                // Pep animation
                animationView
                
                // Conversation messages
                messagesView
                
                // Voice activity indicator
                indicatorView
                
                // Loading indicator
                if isLoading {
                    ProgressView("Processing...")
                        .padding()
                }
            }
            .padding()
        }
        .onAppear {
            setup()
        }
        .onDisappear {
            cleanup()
        }
    }
    
    // MARK: - View Components
    
    private var animationView: some View {
        // Using custom component (assumed to be defined elsewhere)
        PepAnimation(state: $animationState)
            .frame(width: 200, height: 200)
    }
    
    private var messagesView: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 12) {
                    ForEach(messages) { message in
                        ConversationBubble(message: message)
                            .id(message.id)
                    }
                    // Invisible view at bottom for scrolling
                    Color.clear.frame(height: 1).id("bottom")
                }
                .padding(.horizontal)
                .onChange(of: messages.count) { _ in
                    // Scroll to bottom when messages change
                    withAnimation {
                        proxy.scrollTo("bottom", anchor: .bottom)
                    }
                }
            }
            .frame(maxWidth: .infinity)
            .background(Color(.systemBackground))
        }
    }
    
    private var indicatorView: some View {
        HStack {
            Circle()
                .fill(animationState == .listening ? Color.green : Color.gray)
                .frame(width: 10, height: 10)
            
            Text(statusText)
                .font(.caption)
                .foregroundColor(.secondary)
        }
        .padding(.top, 5)
        .padding(.bottom, 10)
    }
    
    private var statusText: String {
        switch animationState {
        case .listening: return "Listening..."
        case .speaking: return "Speaking..."
        case .thinking: return "Thinking..."
        default: return "Tap to start"
        }
    }
    
    // MARK: - Setup and Lifecycle
    
    private func setup() {
        setupNotifications()
        configureAudio()
        startAgent()
        
        // Start timer to update state
        Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { _ in
            updateState()
        }
    }
    
    private func startAgent() {
        if !hasStartedAgent {
            hasStartedAgent = true
            
            // Start the agent
            DispatchQueue.main.async {
                self.voiceManager.startOnboardingAgent()
                self.appState.currentAgentType = .onboarding
                
                // Initial animation after a delay
                DispatchQueue.main.asyncAfter(deadline: .now() + 1) {
                    self.animationState = .speaking
                }
            }
        }
    }
    
    private func updateState() {
        // Get states safely
        let isSpeaking = voiceManager.isSpeaking
        let isListening = voiceManager.isListening
        let lastSpokenText = voiceManager.lastSpokenText
        let transcribedText = voiceManager.transcribedText
        
        // Update animation state
        DispatchQueue.main.async {
            // Set animation state based on voice manager state
            if isSpeaking {
                self.animationState = .speaking
            } else if isListening && !isSpeaking {
                self.animationState = .listening
            }
            
            // Add AI message if new
            if !lastSpokenText.isEmpty {
                if !self.messages.contains(where: { $0.text == lastSpokenText && !$0.isUser }) {
                    self.addMessage(text: lastSpokenText, isUser: false)
                }
            }
            
            // Add user message if new
            if !transcribedText.isEmpty {
                if !self.messages.contains(where: { $0.text == transcribedText && $0.isUser }) {
                    self.addMessage(text: transcribedText, isUser: true)
                }
            }
            
            // Check for onboarding completion
            if self.appState.userId != nil && !self.isOnboardingComplete {
                self.handleOnboardingComplete()
            }
        }
    }
    
    private func cleanup() {
        // Remove notifications
        NotificationCenter.default.removeObserver(self)
    }
    
    // MARK: - Notifications
    
    private func setupNotifications() {
        // Patient ID notification
        NotificationCenter.default.addObserver(
            forName: VoiceManager.patientIdReceivedNotification,
            object: nil,
            queue: .main
        ) { [weak self] notification in
            guard let self = self else { return }
            if let patientId = notification.userInfo?["patient_id"] as? String {
                self.appState.updateUserId(patientId)
                self.animationState = .thinking
                self.addMessage(text: "Thanks for sharing that information. I'm generating personalized exercises for you now...", isUser: false)
            }
        }
        
        // Exercises notification
        NotificationCenter.default.addObserver(
            forName: VoiceManager.exercisesGeneratedNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            guard let self = self else { return }
            self.handleExercisesGenerated()
        }
    }
    
    // MARK: - Audio
    
    private func configureAudio() {
        do {
            try AVAudioSession.sharedInstance().setCategory(.playAndRecord, options: [.defaultToSpeaker, .allowBluetooth])
            try AVAudioSession.sharedInstance().setActive(true, options: .notifyOthersOnDeactivation)
        } catch {
            print("Failed to configure audio: \(error)")
        }
    }
    
    // MARK: - Helper Methods
    
    private func addMessage(text: String, isUser: Bool) {
        let message = ConversationMessage(text: text, isUser: isUser)
        messages.append(message)
        
        // Configure audio output
        configureSpeakerOutput()
    }
    
    private func configureSpeakerOutput() {
        do {
            if !(voiceManager.isBluetoothConnected) {
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
        isLoading = false
        addMessage(text: "Your personalized exercise is ready! Let's get started with your recovery journey.", isUser: false)
        
        // Wait before completing
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) {
            self.handleOnboardingComplete()
        }
    }
    
    private func handleOnboardingComplete() {
        guard !isOnboardingComplete else { return }
        
        print("Onboarding complete, ending session")
        
        // End the session
        voiceManager.endElevenLabsSession()
        
        // Small delay to allow session to properly end
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
            self.isOnboardingComplete = true
        }
    }
}

// MARK: - Bubble Component

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
