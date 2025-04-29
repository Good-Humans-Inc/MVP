import Foundation
import AVFoundation
import Combine
import ElevenLabsSDK
import Network
import SwiftUI

// Import UserManager
import MVP

// Define agent types
enum AgentType {
    case onboarding
    case exerciseCoach
    
    var agentId: String {
        switch self {
        case .onboarding:
            return "bQqjExJbbxuxqjC7WgFe"   // LX: Onboarding
        case .exerciseCoach:
            return "1VM89FzmrkLS4QUkx2gM"   // LX
        }
    }
    
    var displayName: String {
        switch self {
        case .onboarding:
            return "Onboarding Assistant"
        case .exerciseCoach:
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
    @Published var isListening = false
    @Published var transcribedText = ""
    @Published var hasCompletedOnboarding = false
    
    // Track session operations
    private var sessionOperationInProgress = false
    private var sessionOperationCompletionHandlers: [() -> Void] = []
    
    // Track session request flags separately for each agent type
    private var sessionRequestFlags: [AgentType: Bool] = [
        .onboarding: false,
        .exerciseCoach: false
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
    
    // Add PoseAnalysisManager dependency (Ensure this is initialized!)
    var poseAnalysisManager: PoseAnalysisManager!
    
    var isBluetoothConnected: Bool = false
    
    // Notification names
    static let userIdReceivedNotification = Notification.Name("UserIDReceived")
    static let exercisesGeneratedNotification = Notification.Name("ExercisesGenerated")
    static let exerciseCoachReadyNotification = Notification.Name("ExerciseCoachReady")
    static let reportGeneratedNotification = Notification.Name("ReportGenerated")
    
    override init() {
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
                var dynamicVars: [String: ElevenLabsSDK.DynamicVariableValue] = [:]
                
                // Debug print UserDefaults values
                print("🔍 Debug - UserDefaults values:")
                print("userId: \(UserDefaults.standard.string(forKey: "userId") ?? "nil")")
                
                // Add dynamic variables for exercise agents
                if agentType == .exerciseCoach {
                    if let exercisesData = UserDefaults.standard.data(forKey: "UserExercises"),
                       let exercises = try? JSONSerialization.jsonObject(with: exercisesData) as? [[String: Any]],
                       let exercise = exercises.first { exerciseDict in
                           // Add logic here to select the correct exercise if needed
                           // For now, just taking the first one found in UserDefaults
                           true // Placeholder condition
                       } { // Closing brace for the closure

                        print("🔍 Debug - Adding exercise and user information to dynamic variables for Exercise Coach")

                        // Add user info to dynamic variables
                        let userManager = UserManager.shared
                        print("🔍 Debug - user_name: \(userManager.userName)")
                        print("🔍 Debug - user_id: \(userManager.userId ?? "nil")")
                        dynamicVars["user_name"] = .string(userManager.userName)
                        // Add user ID safely
                        if let userId = userManager.userId {
                             dynamicVars["user_id"] = .string(userId)
                        }
                        dynamicVars["user_age"] = .int(userManager.userAge)
                        dynamicVars["exercise_routine"] = .string(userManager.exerciseRoutine) // Assuming UserManager has this
                        dynamicVars["user_goals"] = .string(userManager.userGoals) // Assuming UserManager has this
                        dynamicVars["pain_description"] = .string(userManager.painDescription)

                        // Add basic exercise info (example, adjust keys as needed)
                        if let name = exercise["name"] as? String {
                            dynamicVars["exercise_name"] = .string(name)
                        }
                        if let description = exercise["description"] as? String {
                            dynamicVars["exercise_description"] = .string(description)
                        }

                        // Add instructions as a formatted string
                        if let instructions = exercise["instructions"] as? [String] {
                            let numberedInstructions = instructions.enumerated()
                                .map { (index, instruction) in "\(index + 1). \(instruction)" }
                                .joined(separator: "\n")
                            dynamicVars["exercise_instructions"] = .string(numberedInstructions)
                        }

                        // Add variations as a formatted string
                        if let variations = exercise["variations"] as? [String] {
                            let formattedVariations = variations
                                .map { "• \($0)" }
                                .joined(separator: "\n")
                            dynamicVars["exercise_variations"] = .string(formattedVariations)
                        }

                        // Add target joints
                        if let targetJoints = exercise["target_joints"] as? [String] {
                            dynamicVars["target_joints"] = .string(targetJoints.joined(separator: ", "))
                        }

                        // Add exercise ID
                        if let firestoreId = exercise["firestoreId"] as? String {
                            dynamicVars["exercise_id"] = .string(firestoreId)
                            self.currentExerciseId = firestoreId // Store the current exercise ID
                        } else if let id = exercise["id"] as? String {
                            dynamicVars["exercise_id"] = .string(id.lowercased())
                            self.currentExerciseId = id.lowercased() // Store the current exercise ID
                        }

                        print("✅ Added exercise dynamic variables:")
                        dynamicVars.forEach { key, value in
                            print("- \(key): \(value)")
                        }
                    } else {
                        print("⚠️ Warning: Could not load exercise information from UserDefaults for Exercise Coach")
                    }
                }
                
                let config = ElevenLabsSDK.SessionConfig(
                    agentId: agentType.agentId,
                    dynamicVariables: dynamicVars
                )
                
                // Debug print final configuration
                print("🔍 Debug - Final configuration:")
                print("Agent ID: \(config.agentId)")
                print("Dynamic Variables: \(config.dynamicVariables)")
                
                // Register client tools - different tools based on agent type
                var clientTools = ElevenLabsSDK.ClientTools()
                
                switch agentType {
                case .onboarding:
                    registerOnboardingTools(clientTools: &clientTools)
                case .exerciseCoach:
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
                        self.isListening = (newMode == .listening)
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
                    
                    // Update transcribed text for user messages
                    DispatchQueue.main.async {
                        if role == .user {
                            self.transcribedText = message
                        } else {
                            self.lastSpokenText = message
                        }
                    }
                    
                    // Try to extract JSON from the message if in onboarding mode
                    if self.currentAgentType == .onboarding {
                        self.tryExtractJson(from: message)
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
        // Tool to capture user ID
        clientTools.register("saveUserId") { [weak self] parameters in
            guard let self = self else { return "Manager not available" }
            
            print("🔵 saveUserId tool called with parameters: \(parameters)")
            // Extract user ID from parameters
            guard let userId = parameters["user_id"] as? String else {
                print("❌ clientTools - saveUserId: No user_id parameter found")
                throw ElevenLabsSDK.ClientToolError.invalidParameters
            }
            
            // save user info to UserManager. UserManager already has a didSet observer on the userId property that handles saving to UserDefaults
            let userManager = UserManager.shared
            print("🔍 Debug - saveUserId: before userManager.userId: \(userManager.userId)")
            userManager.userId = userId
            print("🔍 Debug - saveUserId: after userManager.userId: \(userManager.userId)")
            // Update published property on main thread
            DispatchQueue.main.async {
                // Post notification for other parts of the app
                NotificationCenter.default.post(
                    name: VoiceManager.userIdReceivedNotification,
                    object: nil,
                    userInfo: ["user_id": userId]
                )
            }
            
            print("✅ Saved user ID: \(userId)")

            // Set onboarding as completed
            self.hasCompletedOnboarding = true
            // Generate exercises with the user ID
            self.generateExercises(userId: userId)

            return "User data saved successfully with ID: \(userId)"
        }
        print("⭐️ Registered onboarding client tools: saveUserId")
    }
    
    // Register tools specific to the regular exercise agent
    private func registerExerciseTools(clientTools: inout ElevenLabsSDK.ClientTools) {
        // Tool to log exercise progress
        clientTools.register("logExerciseProgress") { parameters in
            guard let progress = parameters["progress"] as? String else {
                throw ElevenLabsSDK.ClientToolError.invalidParameters
            }
            
            print("🔵 Exercise Progress: \(progress)")
            
            // Post notification with progress information
            DispatchQueue.main.async {
                NotificationCenter.default.post(
                    name: Notification.Name("ExerciseProgress"),
                    object: nil,
                    userInfo: ["progress": progress]
                )
            }
            
            return "Progress logged successfully"
        }
        print("⭐️ Registered exercise client tools: logExerciseProgress")
        
        // Tool to start pose analysis
        // clientTools.register("startPoseAnalysis") { [weak self] parameters in
        //     guard let self = self else {
        //         print("❌ startPoseAnalysis: VoiceManager instance is nil")
        //     }
            
        //     UserManager.shared.loadUserData()
        //     guard let userId = UserManager.shared.userId else {
        //         print("❌ startPoseAnalysis: User ID is missing")
        //         // Maybe inform the agent or just log? Let's inform.
        //         return "Can't start pose analysis because userId is missing."
        //     }
            
        //     guard let exerciseId = self.currentExerciseId else {
        //         print("❌ startPoseAnalysis: Current exercise ID is missing")
        //         return "Can't start pose analysis because the current exerciseId is missing."
        //     }
            
        //     print("🔵 Starting pose analysis for user: \(userId), exercise: \(exerciseId)")
            
        //     // Assuming startAnalysis takes exerciseId and userId.
        //     // Adjust if the actual method signature is different.
        //     // You might need to fetch the full Exercise object if required.
        //     // self.poseAnalysisManager.startAnalysis(exerciseId: exerciseId, userId: userId)
            
        //     return "Taking a look at the user's pose and movement now."
        // }
    }
    
    // Generate exercises for the user
    func generateExercises(userId: String) {
        // Call the cloud function
        guard let url = URL(string: "https://us-central1-pepmvp.cloudfunctions.net/generate_exercise") else {
            print("❌ Invalid generate exercises URL")
            return
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.addValue("application/json", forHTTPHeaderField: "Content-Type")
        
        // Create request body
        let requestBody: [String: Any] = [
            "user_id": userId,
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
                   let exerciseJson = json?["exercise"] as? [String: Any] {
                    
                    // Convert single exercise to array format for compatibility
                    let exercisesArray = [exerciseJson]
                    
                    // Store exercises in UserDefaults
                    if let exercisesData = try? JSONSerialization.data(withJSONObject: exercisesArray) {
                        UserDefaults.standard.set(exercisesData, forKey: "UserExercises")
                        
                        DispatchQueue.main.async {
                            // Post notification that exercises are ready
                            NotificationCenter.default.post(
                                name: VoiceManager.exercisesGeneratedNotification,
                                object: nil,
                                userInfo: ["exercises_count": 1]
                            )
                            
                            // Schedule notification for the exercise
                            if let exerciseId = exerciseJson["id"] as? String {
                                self.scheduleNotification(userId: userId, exerciseId: exerciseId)
                            }
                        }
                        
                        print("✅ Generated exercise and saved to UserDefaults")
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
    
    // Helper function to schedule notification
    private func scheduleNotification(userId: String, exerciseId: String) {
        guard let url = URL(string: "https://us-central1-pepmvp.cloudfunctions.net/schedule_notification") else {
            print("❌ Invalid schedule notification URL")
            return
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.addValue("application/json", forHTTPHeaderField: "Content-Type")
        
        // Create request body
        let requestBody: [String: Any] = [
            "user_id": userId,
            "exercise_id": exerciseId,
            "is_one_time": false  // This is a recurring notification
        ]
        
        // Convert to JSON data
        guard let httpBody = try? JSONSerialization.data(withJSONObject: requestBody) else {
            print("❌ Failed to serialize notification scheduling request")
            return
        }
        
        request.httpBody = httpBody
        
        // Make API call
        let task = URLSession.shared.dataTask(with: request) { data, response, error in
            if let error = error {
                print("❌ Notification scheduling error: \(error.localizedDescription)")
                return
            }
            
            // Log HTTP response for debugging
            if let httpResponse = response as? HTTPURLResponse {
                print("📊 Notification scheduling HTTP status: \(httpResponse.statusCode)")
            }
            
            if let data = data,
               let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                print("📊 Notification scheduling response: \(json)")
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
                        
                        // Check for user_id
                        if let userId = json["user_id"] as? String {
                            print("✅ Found user ID in JSON: \(userId)")
                            UserDefaults.standard.set(userId, forKey: "userId")
                            
                            DispatchQueue.main.async {
                                // Post notification
                                NotificationCenter.default.post(
                                    name: VoiceManager.userIdReceivedNotification,
                                    object: nil,
                                    userInfo: ["user_id": userId]
                                )
                                
                                // Set onboarding as completed
                                self.hasCompletedOnboarding = true
                                
                                // Automatically generate exercises
                                self.generateExercises(userId: userId)
                            }
                        }
                    }
                } catch {
                    print("❌ Failed to parse JSON: \(error)")
                }
            }
            
            // Alternative: Look for user_id specifically with regex
            if message.contains("user_id") {
                let pattern = "\"user_id\"\\s*:\\s*\"([^\"]+)\""
                if let regex = try? NSRegularExpression(pattern: pattern),
                   let match = regex.firstMatch(in: message, range: NSRange(message.startIndex..., in: message)) {
                    
                    let idRange = Range(match.range(at: 1), in: message)!
                    let userId = String(message[idRange])
                    
                    print("✅ Found user ID using regex: \(userId)")
                    UserDefaults.standard.set(userId, forKey: "userId")
                    
                    DispatchQueue.main.async {
                        // Post notification
                        NotificationCenter.default.post(
                            name: VoiceManager.userIdReceivedNotification,
                            object: nil,
                            userInfo: ["user_id": userId]
                        )
                        
                        // Set onboarding as completed
                        self.hasCompletedOnboarding = true
                        
                        // Automatically generate exercises
                        self.generateExercises(userId: userId)
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
                    for agentType in [AgentType.onboarding, AgentType.exerciseCoach] {
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
                    for agentType in [AgentType.onboarding, AgentType.exerciseCoach] {
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
        if currentAgentType == .exerciseCoach {
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
            for agentType in [AgentType.onboarding, AgentType.exerciseCoach] {
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
    
    // MARK: - Onboarding Management
    func startOnboardingAgent() {
        print("🔍 startOnboardingAgent called")
        startElevenLabsSession(agentType: .onboarding)
    }
    
    func resetOnboarding() {
        print("🔄 Resetting onboarding state")
        
        // End current session if any
        endElevenLabsSession()
        
        // Reset all relevant state
        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return }
            self.hasCompletedOnboarding = false
            self.lastSpokenText = ""
            self.transcribedText = ""
            self.isListening = false
            self.isSpeaking = false
            
            // Reset conversation history
            self.clearConversationHistory()
            
            // Remove stored user data
            UserDefaults.standard.removeObject(forKey: "userId")
            UserDefaults.standard.removeObject(forKey: "UserExercises")
        }
    }
    
    // Start the exercise coach agent
    func startExerciseAgent(completion: (() -> Void)? = nil) {
        print("🔍 startExerciseAgent called (Unified Exercise Coach)")
        // Start session with the unified .exerciseCoach type
        startElevenLabsSession(agentType: .exerciseCoach, completion: completion)
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
           let userId = UserDefaults.standard.string(forKey: "userId") {
            
            // Call the server API to generate report in the background
            generatePTReport(
                userId: userId,
                exerciseId: exerciseId,
                conversationHistory: conversationMessages
            ) { _ in
                // Report generation handled separately by ReportView
                print("✅ Background report generation initiated")
            }
        }
        
        // End ElevenLabs session
        endElevenLabsSession()
        
        // Don't clear conversation history here - it will be cleared after report generation
    }
    
    // Method to set current exercise
    func setCurrentExercise(id: String) {
        currentExerciseId = id
        print("🎯 Set current exercise ID: \(id)")
    }
    
    // Helper method to generate PT report without blocking UI
    private func generatePTReport(userId: String, exerciseId: String,
                                 conversationHistory: [[String: Any]],
                                 completion: @escaping (Result<[String: Any], Error>) -> Void) {
        
        // Create URL for cloud function
        guard let url = URL(string: "https://us-central1-pepmvp.cloudfunctions.net/generate_report") else {
            completion(.failure(NSError(domain: "VoiceManager", code: 1, userInfo: [NSLocalizedDescriptionKey: "Invalid URL"])))
            return
        }
        
        // Create request
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        // Create request body
        let requestBody: [String: Any] = [
            "user_id": userId,
            "exercise_id": exerciseId,
            "conversation_history": conversationHistory
        ]
        
        // Debug print the request body
        if let jsonData = try? JSONSerialization.data(withJSONObject: requestBody, options: .prettyPrinted),
           let jsonString = String(data: jsonData, encoding: .utf8) {
            print("Request body for report generation:")
            print(jsonString)
        }
        
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
            
            // Debug print the response
            if let jsonString = String(data: data, encoding: .utf8) {
                print("Response from report generation:")
                print(jsonString)
            }
            
            do {
                // Parse response
                if let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] {
                    // Store report in UserDefaults
                    if let reportData = try? JSONSerialization.data(withJSONObject: json) {
                        UserDefaults.standard.set(reportData, forKey: "UserReport")
                        
                        DispatchQueue.main.async {
                            // Post notification that report is ready
                            NotificationCenter.default.post(
                                name: VoiceManager.reportGeneratedNotification,
                                object: nil
                            )
                            
                            // Schedule notification for the report
                            if let userId = UserDefaults.standard.string(forKey: "UserId") {
                                self.scheduleNotification(userId: userId, exerciseId: "report")
                            }
                        }
                        
                        print("✅ Generated report and saved to UserDefaults")
                    }
                } else {
                    print("❌ Invalid report generation response format")
                }
            } catch {
                print("❌ Failed to parse report generation response: \(error)")
            }
        }.resume()
    }
}
