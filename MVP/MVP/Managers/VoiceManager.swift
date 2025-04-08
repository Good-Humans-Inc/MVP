import Foundation
import AVFoundation
import Combine
import ElevenLabsSDK
import Network

// Define agent types
enum AgentType {
    case onboarding
    case firstExercise
    case exercise
    
    var agentId: String {
        switch self {
        case .onboarding:
            return "lpwQ9rz6CHbfexAY8kU3"   // Onboarding agent ID
        case .firstExercise:
            return "aBC123DEf456gHI789jK"   // First exercise agent ID (replace with actual ID)
        case .exercise:
            return "GEXRBIHrq3oa2fB0TO1v"   // Exercise coach agent ID
        }
    }
    
    var displayName: String {
        switch self {
        case .onboarding:
            return "Onboarding Assistant"
        case .firstExercise:
            return "First Exercise Coach"
        case .exercise:
            return "Exercise Coach"
        }
    }
}

class VoiceManager: NSObject, ObservableObject {
    // Published properties for UI updates
    @Published var isSpeaking = false
    @Published var lastSpokenText: String = ""
    @Published var voiceError: String?
    @Published var status: ElevenLabsSDK.Status = .disconnected
    @Published var mode: ElevenLabsSDK.Mode = .listening
    @Published var isSessionActive = false  // Track if the session is active
    @Published var currentAgentType: AgentType? = nil
    
    // Track session operations
    private var sessionOperationInProgress = false
    private var sessionOperationCompletionHandlers: [() -> Void] = []
    
    // Track session request flags separately for each agent type
    private var sessionRequestFlags: [AgentType: Bool] = [
        .onboarding: false,
        .firstExercise: false,
        .exercise: false
    ]
    
    // Network monitoring
    private let networkMonitor = NWPathMonitor()
    @Published var isNetworkConnected = false
    
    // ElevenLabs conversation
    private var conversation: ElevenLabsSDK.Conversation?
    
    // Audio session
    private let audioSession = AVAudioSession.sharedInstance()
    
    // Completion handler for speech
    private var completionHandler: (() -> Void)?
    
    // Observer for status changes
    private var statusObserver: AnyCancellable?
    
    // NSlock for thread safety
    private let sessionLock = NSLock()
    
    // Flag to track if audio session is being configured
    private var isConfiguringAudio = false
    
    // Cleanup flag to prevent race conditions during cleanup
    private var isPerformingCleanup = false
    
    // Add conversation history tracking
    private var conversationMessages: [[String: Any]] = []
    
    // Add property to track current exercise
    private var currentExerciseId: String?
    
    var isBluetoothConnected: Bool = false
    
    // Notification names
    static let patientIdReceivedNotification = Notification.Name("PatientIDReceived")
    static let exercisesGeneratedNotification = Notification.Name("ExercisesGenerated")
    static let exerciseCoachReadyNotification = Notification.Name("ExerciseCoachReady")
    
    init() {
        super.init()
        print("VoiceManager initialized with ElevenLabsSDK \(ElevenLabsSDK.version)")
        startNetworkMonitoring()
        
        // Add observer for audio route changes (Bluetooth detection)
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleRouteChange(_:)),
            name: AVAudioSession.routeChangeNotification,
            object: nil
        )
    }
    
    private func startNetworkMonitoring() {
        networkMonitor.pathUpdateHandler = { [weak self] path in
            DispatchQueue.main.async {
                self?.isNetworkConnected = path.status == .satisfied
                print("📶 Network status changed: \(path.status == .satisfied ? "Connected" : "Disconnected")")
            }
        }
        networkMonitor.start(queue: DispatchQueue.global())
    }
    
    // Method to wait for session operations to complete
    private func waitForSessionOperations(completion: @escaping () -> Void) {
        if sessionOperationInProgress {
            // Add to queue of completion handlers
            sessionOperationCompletionHandlers.append(completion)
        } else {
            // Execute immediately
            completion()
        }
    }

    // Method to complete current operation and process queue
    private func completeSessionOperation() {
        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return }
            
            self.sessionOperationInProgress = false
            
            // Process any queued operations
            if !self.sessionOperationCompletionHandlers.isEmpty {
                let nextOperation = self.sessionOperationCompletionHandlers.removeFirst()
                nextOperation()
            }
        }
    }
    
    // Main method to start an ElevenLabs session with specified agent type
    func startElevenLabsSession(agentType: AgentType, completion: (() -> Void)? = nil) {
        // Use a lock to prevent concurrent session starts
        sessionLock.lock()
        
        // Early check for conditions that would prevent start
        if isPerformingCleanup {
            print("⚠️ Cannot start session during cleanup")
            sessionLock.unlock()
            DispatchQueue.main.async {
                completion?()
            }
            return
        }
        
        // Check if this agent type is already being requested
        if sessionRequestFlags[agentType] == true {
            print("⚠️ \(agentType.displayName) session already requested, skipping duplicate start")
            sessionLock.unlock()
            DispatchQueue.main.async {
                completion?()
            }
            return
        }
        
        // Check if we already have an active session
        if isSessionActive {
            print("⚠️ A session is already active (\(currentAgentType?.displayName ?? "unknown")). Ending it before starting a new one.")
            
            // Mark this session as requested to prevent multiple starts during cleanup
            sessionRequestFlags[agentType] = true
            
            // Release the lock
            sessionLock.unlock()
            
            // End current session and then start the new one
            endElevenLabsSession { [weak self] in
                guard let self = self else { return }
                // Add delay to ensure cleanup is complete
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                    self.startElevenLabsSession(agentType: agentType, completion: completion)
                }
            }
            return
        }
        
        // Mark this session as requested
        sessionRequestFlags[agentType] = true
        currentAgentType = agentType
        
        // Track this operation
        sessionOperationInProgress = true
        
        print("🔒 Marked \(agentType.displayName) session as requested")
        
        // Release the lock now that we've updated our state
        sessionLock.unlock()
        
        // Start the actual session
        doStartElevenLabsSession(agentType: agentType) {
            DispatchQueue.main.async {
                completion?()
            }
        }
    }
    
    private func doStartElevenLabsSession(agentType: AgentType, completion: @escaping () -> Void) {
        Task {
            do {
                print("⭐️ Starting ElevenLabs session with agent type: \(agentType.displayName) (ID: \(agentType.agentId))")
                
                // Configure audio session - with proper async/await
                await configureAudioSessionForElevenLabs()
                
                // Network check
                if !isNetworkConnected {
                    print("⚠️ Warning: Network appears to be disconnected")
                }
                
                // Set up initial configuration
                let config = ElevenLabsSDK.SessionConfig(agentId: agentType.agentId)
                
                // Register client tools - different tools based on agent type
                var clientTools = ElevenLabsSDK.ClientTools()
                
                switch agentType {
                case .onboarding:
                    registerOnboardingTools(clientTools: &clientTools)
                case .firstExercise:
                    registerFirstExerciseTools(clientTools: &clientTools)
                case .exercise:
                    registerExerciseTools(clientTools: &clientTools)
                }
                
                // Configure callbacks for ElevenLabs events
                var callbacks = ElevenLabsSDK.Callbacks()
                
                // Connection status callbacks
                callbacks.onConnect = { [weak self] conversationId in
                    guard let self = self else { return }
                    print("🟢 ElevenLabs connected with \(agentType.displayName) - conversation ID: \(conversationId)")
                    DispatchQueue.main.async {
                        self.status = .connected
                        self.isSessionActive = true
                    }
                }
                
                callbacks.onDisconnect = { [weak self] in
                    guard let self = self else { return }
                    print("🔴 ElevenLabs \(agentType.displayName) disconnected")
                    DispatchQueue.main.async {
                        self.status = .disconnected
                        self.isSessionActive = false
                        // Reset the flag when disconnected
                        self.sessionRequestFlags[agentType] = false
                    }
                }
                
                // Mode change callback (speaking/listening)
                callbacks.onModeChange = { [weak self] newMode in
                    guard let self = self else { return }
                    print("🔄 ElevenLabs \(agentType.displayName) mode changed to: \(newMode)")
                    DispatchQueue.main.async {
                        self.mode = newMode
                        self.isSpeaking = (newMode == .speaking)
                    }
                }
                
                // Message transcripts
                callbacks.onMessage = { [weak self] message, role in
                    guard let self = self else { return }
                    print("📝 ElevenLabs \(self.currentAgentType?.displayName ?? "Unknown") message (\(role.rawValue)): \(message)")
                    
                    // Record all messages for both onboarding and exercise coach
                    self.conversationMessages.append([
                        "role": role == .user ? "user" : "ai",
                        "content": message
                    ])
                    
                    // Try to extract JSON from the message if in onboarding mode
                    if self.currentAgentType == .onboarding {
                        self.tryExtractJson(from: message)
                    }
                    
                    DispatchQueue.main.async {
                        if role == .ai {
                            self.lastSpokenText = message
                        }
                    }
                }
                
                // Error handling
                callbacks.onError = { [weak self] error, details in
                    guard let self = self else { return }
                    print("⚠️ ElevenLabs \(agentType.displayName) error: \(error)")
                    print("⚠️ Error details: \(String(describing: details))")
                    
                    DispatchQueue.main.async {
                        self.voiceError = "ElevenLabs error: \(error)"
                        self.isSessionActive = false
                        
                        // Reset the session flag for definitive errors
                        if error != "WebSocket error" {
                            self.sessionRequestFlags[agentType] = false
                        }
                    }
                }
                
                // Set status to connecting
                DispatchQueue.main.async {
                    self.status = .connecting
                }
                
                // Start the conversation session
                print("🚀 Attempting to start ElevenLabs \(agentType.displayName) session...")
                
                // Check if we should abort
                if sessionRequestFlags[agentType] != true {
                    print("⚠️ Session start was canceled before initialization")
                    throw NSError(domain: "VoiceManager", code: -1, userInfo: [NSLocalizedDescriptionKey: "Session start canceled"])
                }
                
                conversation = try await ElevenLabsSDK.Conversation.startSession(
                    config: config,
                    callbacks: callbacks,
                    clientTools: clientTools
                )
                
                DispatchQueue.main.async {
                    self.isSessionActive = true
                    
                    print("✅ ElevenLabs \(agentType.displayName) session started successfully")
                    
                    // Mark operation as complete
                    self.sessionOperationInProgress = false
                    completion()
                    self.completeSessionOperation()
                }
                
            } catch {
                print("❌ Failed to start ElevenLabs \(agentType.displayName) conversation: \(error)")
                
                DispatchQueue.main.async {
                    self.voiceError = "Failed to start ElevenLabs: \(error.localizedDescription)"
                    self.status = .disconnected
                    self.isSessionActive = false
                    self.sessionRequestFlags[agentType] = false
                    
                    // Mark operation as complete
                    self.sessionOperationInProgress = false
                    completion()
                    self.completeSessionOperation()
                }
            }
        }
    }

    // Properly configure audio session for ElevenLabs with critical section protection
    private func configureAudioSessionForElevenLabs() async {
        // Use a critical section approach for audio configuration
        await withCheckedContinuation { continuation in
            sessionLock.lock()
            
            // Check if audio is already being configured
            if isConfiguringAudio {
                print("⚠️ Audio session already being configured, waiting...")
                sessionLock.unlock()
                
                // Poll until configuration is complete
                DispatchQueue.global().asyncAfter(deadline: .now() + 0.2) { [weak self] in
                    Task { [weak self] in
                        await self?.configureAudioSessionForElevenLabs()
                        continuation.resume()
                    }
                }
                return
            }
            
            // Mark as configuring
            isConfiguringAudio = true
            sessionLock.unlock()
            
            // First try to deactivate any existing audio session
            do {
                try audioSession.setActive(false, options: .notifyOthersOnDeactivation)
                print("✅ Successfully deactivated previous audio session")
            } catch {
                print("⚠️ Error deactivating previous audio session: \(error). Continuing anyway.")
            }
            
            // Configure audio session
            do {
                // Configure with appropriate settings for ElevenLabs
                try audioSession.setCategory(.playAndRecord,
                                          mode: .spokenAudio,
                                          options: [.allowBluetooth, .defaultToSpeaker, .mixWithOthers])
                
                // Set preferred audio session configuration
                try audioSession.setPreferredSampleRate(48000.0)
                try audioSession.setPreferredIOBufferDuration(0.005) // 5ms buffer
                
                // Activate the session
                try audioSession.setActive(true, options: .notifyOthersOnDeactivation)
                
                print("✅ Audio session configured for ElevenLabs")
            } catch {
                print("❌ Audio session setup error: \(error)")
            }
            
            // Mark configuration as complete
            sessionLock.lock()
            isConfiguringAudio = false
            sessionLock.unlock()
            
            continuation.resume()
        }
    }
    
    // Register tools specific to the onboarding agent
    private func registerOnboardingTools(clientTools: inout ElevenLabsSDK.ClientTools) {
        // Tool to capture patient ID
        clientTools.register("savePatientData") { [weak self] parameters in
            guard let self = self else { return "Manager not available" }
            
            print("🔵 savePatientData tool called with parameters: \(parameters)")
            
            // Extract patient ID from parameters
            guard let patientId = parameters["patient_id"] as? String else {
                print("❌ No patient_id parameter found")
                throw ElevenLabsSDK.ClientToolError.invalidParameters
            }
            
            // Save patient ID to UserDefaults
            UserDefaults.standard.set(patientId, forKey: "PatientID")
            
            // Update published property on main thread
            DispatchQueue.main.async {
                // Post notification for other parts of the app
                NotificationCenter.default.post(
                    name: VoiceManager.patientIdReceivedNotification,
                    object: nil,
                    userInfo: ["patient_id": patientId]
                )
            }
            
            print("✅ Saved patient ID: \(patientId)")
            return "Patient data saved successfully with ID: \(patientId)"
        }
        
        // Debug tool to log any message
        clientTools.register("logMessage") { parameters in
            guard let message = parameters["message"] as? String else {
                throw ElevenLabsSDK.ClientToolError.invalidParameters
            }
            
            print("🔵 ElevenLabs onboarding logMessage: \(message)")
            return "Logged: \(message)"
        }
        
        // Tool to extract and save JSON data
        clientTools.register("saveJsonData") { [weak self] parameters in
            guard let self = self else { return "Manager not available" }
            
            print("🔵 saveJsonData tool called with parameters: \(parameters)")
            
            // Process each key-value pair and save to UserDefaults if needed
            for (key, value) in parameters {
                print("📝 Key: \(key), Value: \(value)")
                
                // Special handling for patient_id
                if key == "patient_id", let patientId = value as? String {
                    UserDefaults.standard.set(patientId, forKey: "PatientID")
                    
                    DispatchQueue.main.async {
                        // Post notification
                        NotificationCenter.default.post(
                            name: VoiceManager.patientIdReceivedNotification,
                            object: nil,
                            userInfo: ["patient_id": patientId]
                        )
                        
                        // Generate exercises with the patient ID
                        self.generateExercises(patientId: patientId)
                    }
                    
                    print("✅ Saved patient ID: \(patientId)")
                }
                
                // Save other data to UserDefaults
                if let stringValue = value as? String {
                    UserDefaults.standard.set(stringValue, forKey: key)
                }
            }
            
            return "JSON data processed successfully"
        }
        
        print("⭐️ Registered onboarding client tools: savePatientData, logMessage, saveJsonData")
    }
    
    // Register tools specific to the first exercise agent
    private func registerFirstExerciseTools(clientTools: inout ElevenLabsSDK.ClientTools) {
        // Tool to save user demographic info
        clientTools.register("saveUserDemographics") { parameters in
            guard let age = parameters["age"] as? Int,
                  let exerciseHabits = parameters["exercise_habits"] as? String,
                  let goals = parameters["goals"] as? String else {
                throw ElevenLabsSDK.ClientToolError.invalidParameters
            }
            
            print("🔵 saveUserDemographics called with age: \(age), exercise habits: \(exerciseHabits), goals: \(goals)")
            
            // Save to UserDefaults
            UserDefaults.standard.set(age, forKey: "UserAge")
            UserDefaults.standard.set(exerciseHabits, forKey: "UserExerciseHabits")
            UserDefaults.standard.set(goals, forKey: "UserGoals")
            
            return "User demographics saved successfully"
        }
        
        // Add exercise feedback tool
        clientTools.register("provideExerciseFeedback") { parameters in
            guard let feedbackType = parameters["type"] as? String,
                  let message = parameters["message"] as? String else {
                throw ElevenLabsSDK.ClientToolError.invalidParameters
            }
            
            print("🔵 Exercise Feedback (\(feedbackType)): \(message)")
            
            // Post notification with feedback information
            DispatchQueue.main.async {
                NotificationCenter.default.post(
                    name: Notification.Name("ExerciseFeedback"),
                    object: nil,
                    userInfo: [
                        "type": feedbackType,
                        "message": message
                    ]
                )
            }
            
            return "Feedback provided successfully"
        }
        
        // Debug tool to log any message
        clientTools.register("logMessage") { parameters in
            guard let message = parameters["message"] as? String else {
                throw ElevenLabsSDK.ClientToolError.invalidParameters
            }
            
            print("🔵 ElevenLabs first exercise logMessage: \(message)")
            return "Logged: \(message)"
        }
        
        print("⭐️ Registered first exercise client tools: saveUserDemographics, provideExerciseFeedback, logMessage")
    }
    
    // Register tools specific to the regular exercise agent
    private func registerExerciseTools(clientTools: inout ElevenLabsSDK.ClientTools) {
        // Tool to log exercise progress
        clientTools.register("logExerciseProgress") { [weak self] parameters in
            guard let self = self else { return "Manager not available" }
            
            print("🔵 logExerciseProgress tool called with parameters: \(parameters)")
            
            guard let exerciseId = parameters["exercise_id"] as? String,
                  let progress = parameters["progress"] as? Double else {
                throw ElevenLabsSDK.ClientToolError.invalidParameters
            }
            
            // Here you would log this to your backend or local storage
            print("📊 Exercise Progress: \(exerciseId) - \(progress)%")
            
            return "Exercise progress logged successfully"
        }
        
        // Tool to provide exercise feedback
        clientTools.register("provideExerciseFeedback") { parameters in
            guard let feedbackType = parameters["type"] as? String,
                  let message = parameters["message"] as? String else {
                throw ElevenLabsSDK.ClientToolError.invalidParameters
            }
            
            print("🔵 Exercise Feedback (\(feedbackType)): \(message)")
            
            // Post notification with feedback information
            DispatchQueue.main.async {
                NotificationCenter.default.post(
                    name: Notification.Name("ExerciseFeedback"),
                    object: nil,
                    userInfo: [
                        "type": feedbackType,
                        "message": message
                    ]
                )
            }
            
            return "Feedback provided successfully"
        }
        
        // Debug tool to log any message
        clientTools.register("logMessage") { parameters in
            guard let message = parameters["message"] as? String else {
                throw ElevenLabsSDK.ClientToolError.invalidParameters
            }
            
            print("🔵 ElevenLabs exercise coach logMessage: \(message)")
            return "Logged: \(message)"
        }
        
        print("⭐️ Registered exercise client tools: logExerciseProgress, provideExerciseFeedback, logMessage")
    }
    
    // Generate exercises for the patient
    func generateExercises(patientId: String) {
        // Call the cloud function
        guard let url = URL(string: "https://us-central1-duoligo-pt-app.cloudfunctions.net/generate_exercises") else {
            print("❌ Invalid generate exercises URL")
            return
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.addValue("application/json", forHTTPHeaderField: "Content-Type")
        
        // Create request body
        let requestBody: [String: Any] = [
            "patient_id": patientId,
            "llm_provider": "openai"  // Can also use Claude
        ]
        
        // Convert to JSON data
        guard let httpBody = try? JSONSerialization.data(withJSONObject: requestBody) else {
            print("❌ Failed to serialize exercise generation request")
            return
        }
        
        request.httpBody = httpBody
        
        // Make API call
        let task = URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            guard let self = self else { return }
            
            if let error = error {
                print("❌ Exercise generation error: \(error.localizedDescription)")
                return
            }
            
            // Log HTTP response for debugging
            if let httpResponse = response as? HTTPURLResponse {
                print("📊 Exercise generation HTTP status: \(httpResponse.statusCode)")
            }
            
            guard let data = data else {
                print("❌ No data received from exercise generation API")
                return
            }
            
            // Log raw response for debugging
            print("📊 Exercise generation raw response: \(String(data: data, encoding: .utf8) ?? "unable to decode")")
            
            do {
                // Parse response
                let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
                print("📊 Exercise generation response: \(json ?? [:])")
                
                if let status = json?["status"] as? String, status == "success",
                   let exercisesJson = json?["exercises"] as? [[String: Any]] {
                    
                    // Store exercises in UserDefaults
                    if let exercisesData = try? JSONSerialization.data(withJSONObject: exercisesJson) {
                        UserDefaults.standard.set(exercisesData, forKey: "PatientExercises")
                        
                        DispatchQueue.main.async {
                            // Post notification that exercises are ready
                            NotificationCenter.default.post(
                                name: VoiceManager.exercisesGeneratedNotification,
                                object: nil,
                                userInfo: ["exercises_count": exercisesJson.count]
                            )
                        }
                        
                        print("✅ Generated \(exercisesJson.count) exercises and saved to UserDefaults")
                    }
                } else {
                    print("❌ Invalid exercise generation response format")
                }
            } catch {
                print("❌ Failed to parse exercise generation response: \(error)")
            }
        }
        
        task.resume()
    }
    
    // Try to extract JSON from messages
    private func tryExtractJson(from message: String) {
        // Check if message might contain JSON
        if message.contains("{") && message.contains("}") {
            // Try to extract JSON using a simple approach first
            if let jsonStart = message.range(of: "{"),
               let jsonEnd = message.range(of: "}", options: .backwards) {
                
                let jsonStartIndex = jsonStart.lowerBound
                let jsonEndIndex = jsonEnd.upperBound
                let potentialJson = String(message[jsonStartIndex..<jsonEndIndex])
                
                do {
                    if let jsonData = potentialJson.data(using: .utf8),
                       let json = try JSONSerialization.jsonObject(with: jsonData) as? [String: Any] {
                        
                        print("📊 Extracted JSON: \(json)")
                        
                        // Check for patient_id
                        if let patientId = json["patient_id"] as? String {
                            print("✅ Found patient ID in JSON: \(patientId)")
                            UserDefaults.standard.set(patientId, forKey: "PatientID")
                            
                            DispatchQueue.main.async {
                                // Post notification
                                NotificationCenter.default.post(
                                    name: VoiceManager.patientIdReceivedNotification,
                                    object: nil,
                                    userInfo: ["patient_id": patientId]
                                )
                                
                                // Automatically generate exercises
                                self.generateExercises(patientId: patientId)
                            }
                        }
                    }
                } catch {
                    print("❌ Failed to parse JSON: \(error)")
                }
            }
            
            // Alternative: Look for patient_id specifically with regex
            if message.contains("patient_id") {
                let pattern = "\"patient_id\"\\s*:\\s*\"([^\"]+)\""
                if let regex = try? NSRegularExpression(pattern: pattern),
                   let match = regex.firstMatch(in: message, range: NSRange(message.startIndex..., in: message)) {
                    
                    let idRange = Range(match.range(at: 1), in: message)!
                    let patientId = String(message[idRange])
                    
                    print("✅ Found patient ID using regex: \(patientId)")
                    UserDefaults.standard.set(patientId, forKey: "PatientID")
                    
                    DispatchQueue.main.async {
                        // Post notification
                        NotificationCenter.default.post(
                            name: VoiceManager.patientIdReceivedNotification,
                            object: nil,
                            userInfo: ["patient_id": patientId]
                        )
                        
                        // Automatically generate exercises
                        self.generateExercises(patientId: patientId)
                    }
                }
            }
        }
    }
    
    // End the ElevenLabs conversation session with proper cleanup
    func endElevenLabsSession(completion: (() -> Void)? = nil) {
        sessionLock.lock()
        
        // Check if we're already cleaning up
        if isPerformingCleanup {
            print("⚠️ Already performing session cleanup - aborting duplicate request")
            sessionLock.unlock()
            DispatchQueue.main.async {
                completion?()
            }
            return
        }
        
        // Check if there's an active session
        guard isSessionActive || conversation != nil else {
            print("No active ElevenLabs session to end")
            sessionLock.unlock()
            DispatchQueue.main.async {
                completion?()
            }
            return
        }
        
        // Mark cleanup as in progress
        isPerformingCleanup = true
        sessionOperationInProgress = true
        
        // Store the current agent type for logging
        let currentAgentTypeForLog = currentAgentType
        sessionLock.unlock()
        
        print("Ending ElevenLabs \(currentAgentTypeForLog?.displayName ?? "Unknown") session")
        
        Task {
            do {
                // End the conversation session if it exists
                if let conversation = self.conversation {
                    try await conversation.endSession()
                    print("✅ ElevenLabs conversation ended successfully")
                }
                
                // Add a delay to ensure session cleanup is complete
                try await Task.sleep(nanoseconds: 500_000_000) // 0.5 seconds
                
                // Deactivate audio session with delay to avoid conflicts
                try? await Task.sleep(nanoseconds: 200_000_000) // 0.2 second additional delay
                do {
                    try self.audioSession.setActive(false, options: .notifyOthersOnDeactivation)
                    print("Audio session deactivated successfully")
                } catch {
                    print("Failed to deactivate audio session: \(error)")
                }
                
                // Update state on main thread
                DispatchQueue.main.async { [weak self] in
                    guard let self = self else { return }
                    
                    // Reset all relevant state
                    self.conversation = nil
                    self.status = .disconnected
                    self.isSpeaking = false
                    self.isSessionActive = false
                    
                    // Reset all session flags to ensure clean state
                    for agentType in [AgentType.onboarding, AgentType.firstExercise, AgentType.exercise] {
                        self.sessionRequestFlags[agentType] = false
                    }
                    
                    print("ElevenLabs \(currentAgentTypeForLog?.displayName ?? "Unknown") session ended")
                    
                    // Mark cleanup as complete
                    self.isPerformingCleanup = false
                    self.sessionOperationInProgress = false
                    
                    // Execute completion handler
                    completion?()
                    
                    // Process any queued operations
                    self.completeSessionOperation()
                }
                
            } catch {
                print("Error ending ElevenLabs session: \(error)")
                
                // Still need to clean up state even after error
                DispatchQueue.main.async { [weak self] in
                    guard let self = self else { return }
                    
                    // Reset all state after failure
                    self.conversation = nil
                    self.status = .disconnected
                    self.isSpeaking = false
                    self.isSessionActive = false
                    
                    // Reset all flags
                    for agentType in [AgentType.onboarding, AgentType.firstExercise, AgentType.exercise] {
                        self.sessionRequestFlags[agentType] = false
                    }
                    
                    // Mark cleanup as complete
                    self.isPerformingCleanup = false
                    self.sessionOperationInProgress = false
                    
                    // Execute completion handler
                    completion?()
                    
                    // Process any queued operations
                    self.completeSessionOperation()
                }
            }
        }
    }
    
    // Interrupt speech if the agent is currently speaking
    func stopSpeaking() {
        // First try to interrupt ElevenLabs speech if active
        if let conversation = conversation, status == .connected, mode == .speaking {
            Task {
                do {
                    print("Interrupting ElevenLabs speech")
                    try await conversation.endSession()
                } catch {
                    print("Failed to interrupt ElevenLabs speech: \(error)")
                }
            }
        }
    }
    
    // Clean up all resources
    func cleanUp() {
        print("Cleaning up VoiceManager resources")
        
        // End exercise session if active
        if currentAgentType == .exercise || currentAgentType == .firstExercise {
            endExerciseSession()
        }
        
        // Stop speaking and end session
        stopSpeaking()
        endElevenLabsSession()
        
        // Reset state
        DispatchQueue.main.async {
            self.lastSpokenText = ""
            self.clearConversationHistory()
            
            // Reset all session request flags
            for agentType in [AgentType.onboarding, AgentType.firstExercise, AgentType.exercise] {
                self.sessionRequestFlags[agentType] = false
            }
        }
        
        // Deactivate audio session
        do {
            try audioSession.setActive(false, options: .notifyOthersOnDeactivation)
            print("Audio session deactivated")
        } catch {
            print("Failed to deactivate audio session: \(error.localizedDescription)")
        }
    }
    
    // Start the onboarding agent
    func startOnboardingAgent() {
        print("🔍 startOnboardingAgent called")
        startElevenLabsSession(agentType: .onboarding)
    }
    
    // Start the first exercise agent
    func startFirstExerciseAgent(completion: (() -> Void)? = nil) {
        print("🔍 startFirstExerciseAgent called")
        startElevenLabsSession(agentType: .firstExercise, completion: completion)
    }
    
    // Start the exercise coach agent
    func startExerciseAgent(completion: (() -> Void)? = nil) {
        print("🔍 startExerciseAgent called")
        startElevenLabsSession(agentType: .exercise, completion: completion)
    }
    
    // MARK: -BLE
    @objc func handleRouteChange(_ notification: Notification) {
        guard let userInfo = notification.userInfo,
              let reasonValue = userInfo[AVAudioSessionRouteChangeReasonKey] as? UInt,
              let reason = AVAudioSession.RouteChangeReason(rawValue: reasonValue) else {
            return
        }
        
        switch reason {
        case .newDeviceAvailable, .oldDeviceUnavailable:
            let audioSession = AVAudioSession.sharedInstance()
            let currentRoute = audioSession.currentRoute
            
            for output in currentRoute.outputs {
                let portType = output.portType
                if portType == .bluetoothA2DP || portType == .bluetoothHFP || portType == .bluetoothLE {
                    print("Bluetooth headphone status change: Connected")
                    self.isBluetoothConnected = true
                    return
                }
            }
            print("Bluetooth headphone status change: Disconnected")
            self.isBluetoothConnected = false
            
        default:
            break
        }
    }
    
    // MARK: - Conversation History Management
    func getConversationHistory() -> [[String: Any]] {
        return conversationMessages
    }
    
    func clearConversationHistory() {
        conversationMessages.removeAll()
        print("🧹 Cleared conversation history")
    }
    
    // MARK: - Exercise Session Management
    func startExerciseSession() {
        clearConversationHistory() // Clear previous history
        print("🎯 Starting new exercise session")
    }
    
    func endExerciseSession() {
        print("🏁 Ending exercise session with \(conversationMessages.count) messages")
        
        // Generate report using conversation history if we have exercise ID
        if let exerciseId = self.currentExerciseId,
           let patientId = UserDefaults.standard.string(forKey: "PatientID") {
            
            // Call the server API to generate report in the background
            generatePTReport(
                patientId: patientId,
                exerciseId: exerciseId,
                conversationHistory: conversationMessages
            ) { _ in
                // Report generation handled separately by ReportView
                print("✅ Background report generation initiated")
            }
        }
        
        // End ElevenLabs session
        endElevenLabsSession()
        
        // Clear conversation history after sending for report
        clearConversationHistory()
    }
    
    // Method to set current exercise
    func setCurrentExercise(id: String) {
        currentExerciseId = id
        print("🎯 Set current exercise ID: \(id)")
    }
    
    // Helper method to generate PT report without blocking UI
    private func generatePTReport(patientId: String, exerciseId: String,
                                 conversationHistory: [[String: Any]],
                                 completion: @escaping (Result<[String: Any], Error>) -> Void) {
        
        // Create URL for cloud function
        guard let url = URL(string: "https://us-central1-duoligo-pt-app.cloudfunctions.net/generate_pt_report") else {
            completion(.failure(NSError(domain: "VoiceManager", code: 1, userInfo: [NSLocalizedDescriptionKey: "Invalid URL"])))
            return
        }
        
        // Create request
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        // Create request body
        let requestBody: [String: Any] = [
            "patient_id": patientId,
            "exercise_id": exerciseId,
            "conversation_history": conversationHistory
        ]
        
        // Serialize request body
        do {
            request.httpBody = try JSONSerialization.data(withJSONObject: requestBody)
        } catch {
            completion(.failure(error))
            return
        }
        
        // Make API call
        URLSession.shared.dataTask(with: request) { data, response, error in
            if let error = error {
                completion(.failure(error))
                return
            }
            
            guard let data = data else {
                completion(.failure(NSError(domain: "VoiceManager", code: 2, userInfo: [NSLocalizedDescriptionKey: "No data received"])))
                return
            }
            
            do {
                // Parse response
                if let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] {
                    completion(.success(json))
                } else {
                    completion(.failure(NSError(domain: "VoiceManager", code: 3, userInfo: [NSLocalizedDescriptionKey: "Invalid response format"])))
                }
            } catch {
                completion(.failure(error))
            }
        }.resume()
    }
}
