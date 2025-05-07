import SwiftUI
import AVKit
import AVFoundation

struct ExerciseDetailView: View {
    let exercise: Exercise
    
    // State variables
    @State private var isStartingExercise = false
    @State private var showingExerciseView = false
    @State private var mediaLoadError: Error?
    @State private var showErrorAlert = false
    @State private var isVideoLoading = true
    @State private var videoAsset: AVAsset?
    
    // Environment objects
    @EnvironmentObject private var appState: AppState
    @EnvironmentObject private var voiceManager: VoiceManager
    @EnvironmentObject private var resourceCoordinator: ResourceCoordinator
    @EnvironmentObject private var cameraManager: CameraManager
    @EnvironmentObject private var visionManager: VisionManager
    @EnvironmentObject private var notificationManager: NotificationManager
    @EnvironmentObject private var userManager: UserManager
    
    var body: some View {
        ZStack {
            VStack(spacing: 20) {
                // Exercise video or image
                videoPreviewSection
                    .alert(isPresented: $showErrorAlert) {
                        Alert(
                            title: Text("Media Loading Error"),
                            message: Text(mediaLoadError?.localizedDescription ?? "Failed to load media"),
                            dismissButton: .default(Text("OK"))
                        )
                    }
                
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        // Exercise title and description
                        Text(exercise.name)
                            .font(.title)
                            .fontWeight(.bold)
                        
                        Text(exercise.description)
                            .foregroundColor(.secondary)
                        
                        // Target joints section
                        targetJointsSection
                        
                        // Instructions section
                        instructionsSection
                        
                        // Start button
                        Button {
                            Task {
                                await startExercise()
                            }
                        } label: {
                            HStack {
                                if isStartingExercise {
                                    ProgressView()
                                        .progressViewStyle(CircularProgressViewStyle(tint: .white))
                                } else {
                                    Image(systemName: "play.circle.fill")
                                }
                                Text(isStartingExercise ? "Starting..." : "Start Exercise")
                            }
                            .padding()
                            .frame(maxWidth: .infinity)
                            .background(userManager.isDataLoaded ? Color.blue : Color.gray)
                            .foregroundColor(.white)
                            .cornerRadius(10)
                        }
                        .padding(.horizontal)
                        .padding(.bottom)
                        .disabled(isStartingExercise || !userManager.isDataLoaded)
                    }
                    .padding()
                }
            }
            
            if isStartingExercise {
                // Loading overlay
                Color.black.opacity(0.7)
                    .edgesIgnoringSafeArea(.all)
                    .overlay(
                        VStack {
                            ProgressView()
                                .scaleEffect(1.5)
                                .tint(.white)
                            
                            Text("Setting up exercise...")
                                .foregroundColor(.white)
                                .padding(.top, 20)
                                
                            // Camera positioning guide
                            cameraPositioningGuide
                        }
                    )
            }
        }
        .fullScreenCover(isPresented: $showingExerciseView) {
            ExerciseView(exercise: exercise, cameraManager: cameraManager, appState: appState)
                .environmentObject(appState)
                .environmentObject(voiceManager)
                .environmentObject(resourceCoordinator)
                .environmentObject(cameraManager)
                .environmentObject(visionManager)
                .environmentObject(userManager)
        }
        .onAppear {
            // Reset camera manager to ensure clean state
            cameraManager.resetSession()
            appState.currentExercise = exercise
            
            // Preload video asset if available
            if let videoURL = exercise.videoURL {
                preloadVideoAsset(from: videoURL)
            }
            
            // Trigger initial data load if needed (fire and forget)
            if !userManager.isDataLoaded {
                 Task { 
                     print("🔄 ExerciseDetailView.onAppear: Triggering initial user data load.")
                     await userManager.loadUserData()
                 }
            }
        }
    }
    
    // MARK: - UI Sections
    
    private var videoPreviewSection: some View {
        Group {
            if let videoURL = exercise.videoURL {
                if isVideoLoading {
                    ProgressView("Loading video...")
                        .frame(maxWidth: .infinity)
                        .aspectRatio(1, contentMode: .fit)  // Use 1:1 for loading state
                        .background(Color.black.opacity(0.1))
                } else if let asset = videoAsset {
                    VideoPlayerView(asset: asset)
                        .aspectRatio(contentMode: .fit)
                        .frame(maxWidth: .infinity)
                        .background(Color.black.opacity(0.1))
                        .cornerRadius(12)
                        .padding(.horizontal)
                } else {
                    // Fallback if video loading failed
                    Rectangle()
                        .fill(Color.gray.opacity(0.2))
                        .aspectRatio(1, contentMode: .fit)
                        .frame(maxWidth: .infinity)
                        .overlay(
                            VStack {
                                Image(systemName: "video.slash")
                                Text("Failed to load video")
                            }
                        )
                }
            } else if let imageURL = exercise.primaryMediaURL {
                AsyncImage(url: imageURL) { phase in
                    switch phase {
                    case .empty:
                        Rectangle()
                            .fill(Color.gray.opacity(0.2))
                            .aspectRatio(1, contentMode: .fit)
                            .frame(maxWidth: .infinity)
                            .overlay(ProgressView())
                    case .success(let image):
                        image
                            .resizable()
                            .aspectRatio(contentMode: .fit)
                            .frame(maxWidth: .infinity)
                    case .failure(let error):
                        Rectangle()
                            .fill(Color.gray.opacity(0.2))
                            .aspectRatio(1, contentMode: .fit)
                            .frame(maxWidth: .infinity)
                            .overlay(
                                VStack {
                                    Image(systemName: "photo")
                                        .font(.largeTitle)
                                    Text("Failed to load image")
                                        .font(.caption)
                                }
                            )
                            .onAppear {
                                mediaLoadError = error
                                showErrorAlert = true
                            }
                    @unknown default:
                        EmptyView()
                    }
                }
                .cornerRadius(12)
                .padding(.horizontal)
            } else {
                // Fallback if no media is available
                Rectangle()
                    .fill(Color.gray.opacity(0.2))
                    .aspectRatio(1, contentMode: .fit)
                    .frame(maxWidth: .infinity)
                    .overlay(
                        Image(systemName: "figure.walk")
                            .font(.system(size: 50))
                    )
                    .cornerRadius(12)
                    .padding(.horizontal)
            }
        }
    }
    
    private var targetJointsSection: some View {
        VStack(alignment: .leading) {
            Text("Target Areas")
                .font(.headline)
            
            HStack {
                ForEach(exercise.targetJoints, id: \.self) { joint in
                    Text(joint.rawValue)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 5)
                        .background(Color.blue.opacity(0.2))
                        .cornerRadius(8)
                }
            }
        }
    }
    
    private var instructionsSection: some View {
        VStack(alignment: .leading) {
            Text("Instructions")
                .font(.headline)
            
            ForEach(Array(exercise.instructions.enumerated()), id: \.offset) { index, instruction in
                HStack(alignment: .top) {
                    Text("\(index + 1).")
                        .fontWeight(.bold)
                    Text(instruction)
                }
                .padding(.vertical, 4)
            }
        }
    }
    
    private var cameraPositioningGuide: some View {
        VStack {
            Text("Position your camera as shown")
                .foregroundColor(.white)
                .padding(.top, 30)
            
            ZStack {
                RoundedRectangle(cornerRadius: 12)
                    .stroke(Color.white, lineWidth: 2)
                    .frame(width: 240, height: 320)
                
                Image(systemName: "person.fill")
                    .font(.system(size: 150))
                    .foregroundColor(.white.opacity(0.6))
                
                // Guide for hand positioning
                VStack {
                    Spacer()
                    
                    Image(systemName: "iphone")
                        .font(.system(size: 40))
                        .foregroundColor(.white)
                        .rotationEffect(.degrees(90))
                    
                    Text("Make sure Pep can see targeted body part!")
                        .foregroundColor(.white)
                        .padding(.top, 8)
                }
                .padding(.bottom, 40)
            }
            .padding(30)
        }
    }
    
    // MARK: - Helper Methods
    
    private func preloadVideoAsset(from url: URL) {
        let options = [AVURLAssetPreferPreciseDurationAndTimingKey: true]
        let asset = AVURLAsset(url: url, options: options)
        
        Task {
            do {
                // Load essential properties asynchronously
                try await asset.load(.duration, .tracks)
                
                // Update UI on main thread
                await MainActor.run {
                    self.videoAsset = asset
                    self.isVideoLoading = false
                }
            } catch {
                await MainActor.run {
                    print("❌ Error loading video asset: \(error)")
                    self.mediaLoadError = error
                    self.showErrorAlert = true
                    self.isVideoLoading = false
                }
            }
        }
    }
    
    // MARK: - Actions
    
    private func resetOnboarding() {
        print("🔄 DEBUG: ExerciseDetailView - Resetting onboarding")
        print("📊 DEBUG: ExerciseDetailView - Pre-reset state:")
        print("- appState.hasUserId: \(appState.hasUserId)")
        print("- appState.isOnboardingComplete: \(appState.isOnboardingComplete)")

        // Reset VoiceManager state
        voiceManager.resetOnboarding()
        
        // Reset AppState
        appState.hasUserId = false
        appState.userId = nil
        appState.isOnboardingComplete = false
        appState.currentAgentType = nil
        
        print("📊 DEBUG: ExerciseDetailView - Post-reset state:")
        print("- appState.hasUserId: \(appState.hasUserId)")
        print("- appState.isOnboardingComplete: \(appState.isOnboardingComplete)")

        // Dismiss this view and return to onboarding
        if let window = UIApplication.shared.windows.first {
            let onboardingView = OnboardingView()
                .environmentObject(appState)
                .environmentObject(voiceManager)
                .environmentObject(resourceCoordinator)
                .environmentObject(cameraManager)
                .environmentObject(visionManager)
                .environmentObject(notificationManager)
                .environmentObject(userManager)
                
            window.rootViewController = UIHostingController(rootView: onboardingView)
            print("✅ Created new root view controller with all environment objects")
        }
    }
    
    private func startExercise() async {
        // Indicate loading/refreshing immediately
        isStartingExercise = true
        
        // --- Explicitly refresh user data and wait --- 
        print("🔄 ExerciseDetailView.startExercise: Refreshing user data...")
        let refreshSuccess = await userManager.loadUserData()
        
        guard refreshSuccess else {
            print("❌ ExerciseDetailView.startExercise: Failed to refresh user data.")
            // Handle refresh failure
            isStartingExercise = false
            mediaLoadError = NSError(domain: "ExerciseDetailView", 
                                   code: 2, 
                                   userInfo: [NSLocalizedDescriptionKey: "Failed to refresh user data before starting exercise."])
            showErrorAlert = true
            return // Stop execution
        }
        print("✅ ExerciseDetailView.startExercise: User data refreshed successfully.")
        // --- End data refresh --- 
        
        // Data is now fresh, proceed with resource configuration
        // Configure needed resources
        // Note: resourceCoordinator.startExerciseSession might need to be async or run on background thread
        resourceCoordinator.startExerciseSession { success in
            guard success else {
                // Handle resource initialization failure
                print("❌ ExerciseDetailView.startExercise: Failed to initialize exercise resources.")
                DispatchQueue.main.async { // Ensure UI updates are on main thread
                    self.isStartingExercise = false
                    self.mediaLoadError = NSError(domain: "ExerciseDetailView", 
                                           code: 1, 
                                           userInfo: [NSLocalizedDescriptionKey: "Failed to initialize exercise resources"])
                    self.showErrorAlert = true
                }
                return
            }
            
            // Start camera session (already seems to handle async completion)
            cameraManager.startSession(withNotification: true) {
                // Start vision processing
                visionManager.startProcessing(cameraManager.videoOutput)
                
                // Start the unified ElevenLabs exercise coach agent
                print("▶️ Starting exercise coach agent")
                voiceManager.startElevenLabsSession(agentType: .exerciseCoach) { 
                    print("✅ Exercise coach agent session started completion handler")
                    
                    // Set current exercise ID after session starts
                    let exerciseId = self.exercise.firestoreId ?? self.exercise.id.uuidString
                    self.voiceManager.setCurrentExercise(id: exerciseId.lowercased())
                        
                    // Show the exercise view
                    // Use MainActor.run for UI updates from background completion handlers
                    Task { @MainActor in
                        // Add a small delay if needed, though maybe not necessary now
                        // try? await Task.sleep(nanoseconds: 500_000_000) 
                        self.isStartingExercise = false
                        self.showingExerciseView = true
                    }
                }
            }
        }
    }
}

// Update VideoPlayerView to handle aspect ratio
struct VideoPlayerView: View {
    let asset: AVAsset
    @State private var isPlaying = false
    @State private var player: AVPlayer?
    @EnvironmentObject private var voiceManager: VoiceManager
    var onError: ((Error) -> Void)?
    
    var body: some View {
        GeometryReader { geometry in
            ZStack {
                if let player = player {
                    VideoPlayer(player: player)
                        .aspectRatio(contentMode: .fit)
                        .frame(width: geometry.size.width, height: geometry.size.height)
                        .onDisappear {
                            player.pause()
                        }
                }
                
                if !isPlaying {
                    Button(action: {
                        startPlayback()
                    }) {
                        Image(systemName: "play.circle.fill")
                            .font(.system(size: 50))
                            .foregroundColor(.white)
                    }
                }
            }
        }
        .onAppear {
            setupPlayer()
        }
        .onDisappear {
            cleanup()
        }
    }
    
    private func setupPlayer() {
        let playerItem = AVPlayerItem(asset: asset)
        self.player = AVPlayer(playerItem: playerItem)
        
        // Configure audio session for video playback
        configureAudioSession()
        
        // Add error observation
        NotificationCenter.default.addObserver(
            forName: .AVPlayerItemFailedToPlayToEndTime,
            object: playerItem,
            queue: .main
        ) { notification in
            if let error = playerItem.error {
                onError?(error)
            }
        }
        
        // Add completion observer
        NotificationCenter.default.addObserver(
            forName: .AVPlayerItemDidPlayToEndTime,
            object: playerItem,
            queue: .main
        ) { _ in
            isPlaying = false
            player?.seek(to: .zero)
        }
    }
    
    private func startPlayback() {
        // Ensure audio session is properly configured before playing
        configureAudioSession()
        
        isPlaying = true
        player?.play()
    }
    
    private func configureAudioSession() {
        do {
            let audioSession = AVAudioSession.sharedInstance()
            
            // Check if we're using Bluetooth
            let currentRoute = audioSession.currentRoute
            let isBluetoothConnected = currentRoute.outputs.contains { 
                [.bluetoothA2DP, .bluetoothHFP, .bluetoothLE].contains($0.portType)
            }
            
            if isBluetoothConnected {
                // For Bluetooth, use playAndRecord category
                try audioSession.setCategory(
                    .playAndRecord,
                    mode: .moviePlayback,
                    options: [.allowBluetooth, .defaultToSpeaker]
                )
            } else {
                // For built-in speaker, just use playback category
                try audioSession.setCategory(
                    .playback,
                    mode: .moviePlayback,
                    options: [.mixWithOthers]  // Allow mixing with other audio
                )
                
                // Manually route to speaker if needed
                try audioSession.overrideOutputAudioPort(.speaker)
            }
            
            // Activate audio session
            if !audioSession.isOtherAudioPlaying {
                try audioSession.setActive(true, options: .notifyOthersOnDeactivation)
                print("✅ Audio session configured for video playback")
            }
        } catch {
            // Only log the error but don't treat it as critical
            print("ℹ️ Audio session configuration note: \(error.localizedDescription)")
        }
    }
    
    private func cleanup() {
        player?.pause()
        player = nil
        isPlaying = false
        
        // Only deactivate if we were the ones who activated it
        if AVAudioSession.sharedInstance().isOtherAudioPlaying == false {
            do {
                try AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
                print("✅ Audio session deactivated")
            } catch {
                // Just log the error
                print("ℹ️ Audio session cleanup note: \(error.localizedDescription)")
            }
        }
    }
}
