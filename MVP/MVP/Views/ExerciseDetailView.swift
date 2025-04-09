import SwiftUI
import AVKit
import AVFoundation

struct ExerciseDetailView: View {
    let exercise: Exercise
    
    // State variables
    @State private var isStartingExercise = false
    @State private var showingExerciseView = false
    
    // Environment objects
    @EnvironmentObject private var appState: AppState
    @EnvironmentObject private var voiceManager: VoiceManager
    @EnvironmentObject private var resourceCoordinator: ResourceCoordinator
    @EnvironmentObject private var cameraManager: CameraManager
    @EnvironmentObject private var visionManager: VisionManager
    
    var body: some View {
        ZStack {
            VStack(spacing: 20) {
                // Exercise video or image
                videoPreviewSection
                
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
                        Button(action: {
                            startExercise()
                        }) {
                            Text("Start Exercise")
                                .font(.headline)
                                .foregroundColor(.white)
                                .frame(maxWidth: .infinity)
                                .padding()
                                .background(isStartingExercise ? Color.gray : Color.blue)
                                .cornerRadius(12)
                        }
                        .padding(.top, 16)
                        .disabled(isStartingExercise)
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
            ExerciseView(exercise: exercise)
                .environmentObject(appState)
                .environmentObject(voiceManager)
                .environmentObject(resourceCoordinator)
                .environmentObject(cameraManager)
                .environmentObject(visionManager)
        }
        .onAppear {
            // Reset camera manager to ensure clean state
            cameraManager.resetSession()
            appState.currentExercise = exercise
        }
    }
    
    // MARK: - UI Sections
    
    private var videoPreviewSection: some View {
        Group {
            mediaContent
        }
    }

    // Helper to handle the conditional logic
    @ViewBuilder
    private var mediaContent: some View {
        if let videoURL = exercise.videoURL {
            VideoPlayerView(url: videoURL)
                .frame(height: 240)
                .cornerRadius(12)
                .padding(.horizontal)
        } else if let imageURL = exercise.imageURL {
            AsyncImage(url: imageURL) { phase in
                switch phase {
                case .empty:
                    Rectangle()
                        .fill(Color.gray.opacity(0.2))
                        .aspectRatio(16/9, contentMode: .fit)
                        .overlay(ProgressView())
                case .success(let image):
                    image
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                        .frame(height: 240)
                case .failure:
                    Rectangle()
                        .fill(Color.gray.opacity(0.2))
                        .aspectRatio(16/9, contentMode: .fit)
                        .overlay(
                            Image(systemName: "photo")
                                .font(.largeTitle)
                        )
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
                .aspectRatio(16/9, contentMode: .fit)
                .frame(height: 240)
                .overlay(
                    Image(systemName: "figure.walk")
                        .font(.system(size: 50))
                )
                .cornerRadius(12)
                .padding(.horizontal)
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
                    
                    Text("Place your device 5-6 feet away")
                        .foregroundColor(.white)
                        .padding(.top, 8)
                }
                .padding(.bottom, 40)
            }
            .padding(30)
        }
    }
    
    // MARK: - Actions
    
    private func startExercise() {
        isStartingExercise = true
        
        // Configure needed resources
        resourceCoordinator.startExerciseSession { success in
            if success {
                // Start camera session
                cameraManager.startSession(withNotification: true) {
                    // Start vision processing
                    visionManager.startProcessing(cameraManager.videoOutput)
                    
                    // Start ElevenLabs exercise coach agent
                    if appState.hasUserId {
                        // Returning user - use regular exercise agent
                        voiceManager.startElevenLabsSession(agentType: .exercise) {
                            appState.currentAgentType = .exercise
                            
                            // Show the exercise view
                            DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
                                isStartingExercise = false
                                showingExerciseView = true
                            }
                        }
                    } else {
                        // First-time user - use first exercise agent
                        voiceManager.startElevenLabsSession(agentType: .firstExercise) {
                            appState.currentAgentType = .firstExercise
                            
                            // Show the exercise view
                            DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
                                isStartingExercise = false
                                showingExerciseView = true
                            }
                        }
                    }
                }
            } else {
                // Handle resource initialization failure
                isStartingExercise = false
                // Show error alert (implementation needed)
            }
        }
    }
}

// Simple video player view
struct VideoPlayerView: View {
    let url: URL
    @State private var isPlaying = false
    
    var body: some View {
        ZStack {
            VideoPlayer(player: AVPlayer(url: url))
                .aspectRatio(contentMode: .fit)
            
            if !isPlaying {
                Button(action: {
                    isPlaying = true
                }) {
                    Image(systemName: "play.circle.fill")
                        .font(.system(size: 50))
                        .foregroundColor(.white)
                }
            }
        }
    }
}
