import SwiftUI
import AVFoundation

struct ExerciseView: View {
    let exercise: Exercise
    
    // State variables
    @State private var isExerciseActive = true
    @State private var remainingTime: TimeInterval = 0
    @State private var timer: Timer? = nil
    @State private var showingExerciseReport = false
    @State private var exerciseDuration: TimeInterval = 0
    //@State private var coachMessages: [String] = []
    @State private var showCoachFeedback = false
    @State private var isStoppingExercise = false
    @State private var showErrorAlert = false
    @State private var errorMessage: String?
    
    // Environment objects
    @Environment(\.presentationMode) var presentationMode
    @EnvironmentObject private var appState: AppState
    @EnvironmentObject private var cameraManager: CameraManager
    @EnvironmentObject private var visionManager: VisionManager
    @EnvironmentObject private var voiceManager: VoiceManager
    @EnvironmentObject private var resourceCoordinator: ResourceCoordinator
    
    // Add PoseAnalysisManager
    @StateObject private var poseAnalysisManager: PoseAnalysisManager
    
    init(exercise: Exercise, cameraManager: CameraManager, appState: AppState) {
        self.exercise = exercise
        _poseAnalysisManager = StateObject(wrappedValue: PoseAnalysisManager(cameraManager: cameraManager, appState: appState))
    }
    
    var body: some View {
        ZStack {
            // Camera feed with body pose visualization overlay
            CameraPreview(session: cameraManager.session)
                .edgesIgnoringSafeArea(.all)
            
            // Body pose overlay for general exercises
            if let bodyPose = visionManager.currentBodyPose, !isRSIExercise() {
                BodyPoseView(
                    bodyPose: bodyPose,
                    lineColor: .green,
                    jointColor: .blue,
                    painPoints: visionManager.painPoints
                )
                .edgesIgnoringSafeArea(.all)
            }
            
            // Hand pose overlay for RSI exercises
            if let handPose = visionManager.currentHandPose, isRSIExercise() {
                HandPoseView(handPose: handPose)
                    .edgesIgnoringSafeArea(.all)
            }
            
            // Coach message bubble if there are messages
            // if !coachMessages.isEmpty, showCoachFeedback {
            //     coachMessageView
            // }
            
            // Timer and controls overlay
            exerciseControlsView
        }
        .onAppear {
            // Setup the exercise session
            setupExerciseSession()
            
            // Setup coach feedback notification observer
            setupExerciseCoachObserver()
        }
        .onDisappear {
            cleanupResources()
            // Remove notification observer
            NotificationCenter.default.removeObserver(self, name: VoiceManager.startPoseAnalysisNotification, object: nil)
        }
        .fullScreenCover(isPresented: $showingExerciseReport) {
            ReportView(
                exercise: exercise,
                duration: exerciseDuration
            )
            .onDisappear {
                // Dismiss ExerciseView when ReportView disappears
                presentationMode.wrappedValue.dismiss()
            }
        }
    }
    
    // MARK: - UI Components
    
    // Coach message view
    // private var coachMessageView: some View {
    //     VStack {
    //         Text(coachMessages.last ?? "")
    //             .padding()
    //             .background(Color.white.opacity(0.8))
    //             .foregroundColor(.black)
    //             .cornerRadius(12)
    //             .padding(.horizontal)
    //             .padding(.top, 40)
            
    //         Spacer()
    //     }
    // }
    
    // Controls view for active exercise
    private var exerciseControlsView: some View {
        VStack {
            // Timer display moved to top
            Text(timeString(from: remainingTime))
                .font(.system(size: 48, weight: .bold, design: .rounded))
                .foregroundColor(.white)
                .padding()
                .background(Color.black.opacity(0.5))
                .cornerRadius(16)
                .padding(.top, 32)  // Add padding from top edge
            
            Spacer()
            
            // Analysis overlay will be positioned here when active
            if poseAnalysisManager.isCapturing {
                poseAnalysisOverlay
                    .padding(.bottom, 20)  // Add space between overlay and stop button
            }
            
            // Stop button
            Button(action: {
                stopExercise()
            }) {
                HStack {
                    Image(systemName: "stop.fill")
                    Text("Stop Exercise")
                }
                .padding()
                .background(Color.red)
                .foregroundColor(.white)
                .cornerRadius(8)
            }
            .padding(.bottom, 32)
            .disabled(isStoppingExercise)
        }
    }
    
    // Add pose analysis overlay
    private var poseAnalysisOverlay: some View {
        VStack {
            Text("Analyzing Your Form")
                .font(.headline)
                .foregroundColor(.white)
            
            ProgressView(value: poseAnalysisManager.captureProgress)
                .progressViewStyle(LinearProgressViewStyle())
                .frame(width: 200)
                .tint(.blue)
            
            Text("\(Int(poseAnalysisManager.captureProgress * 100))%")
                .foregroundColor(.white)
        }
        .padding()
        .background(Color.black.opacity(0.7))
        .cornerRadius(10)
    }
    
    // MARK: - Setup Methods
    
    private func setupExerciseSession() {
        // Initialize timer
        remainingTime = exercise.duration
        timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { _ in
            if remainingTime > 0 {
                remainingTime -= 1
            } else {
                stopExercise()
            }
        }
        
        // Set initial coach message
        //coachMessages = ["I'll help guide you through this exercise. Let me see your form..."]
        showCoachFeedback = true
        
        // Auto-hide initial message after a few seconds
        DispatchQueue.main.asyncAfter(deadline: .now() + 5) {
            if isExerciseActive {
                showCoachFeedback = false
            }
        }
        
        // Configure audio session for speaker output
        do {
            if voiceManager.isBluetoothConnected == false {
                try AVAudioSession.sharedInstance().overrideOutputAudioPort(.speaker)
            } else {
                try AVAudioSession.sharedInstance().overrideOutputAudioPort(.none)
                try AVAudioSession.sharedInstance().setCategory(.playAndRecord,
                                          mode: .spokenAudio,
                                          options: [.allowBluetooth])
            }
        } catch {
            handleError("Failed to configure audio: \(error.localizedDescription)")
        }
    }
    
    // Set up notification observer for the exercise coach
    private func setupExerciseCoachObserver() {
        NotificationCenter.default.addObserver(
            forName: Notification.Name("ExerciseFeedback"),
            object: nil,
            queue: .main
        ) { [self] notification in
            guard let userInfo = notification.userInfo,
                  let message = userInfo["message"] as? String else {
                return
            }
            
            // Add message to the coach messages
            //self.coachMessages.append(message)
            
            // Show the feedback
            self.showCoachFeedback = true
            
            // Auto-hide after a delay
            DispatchQueue.main.asyncAfter(deadline: .now() + 5) {
                if self.isExerciseActive {
                    self.showCoachFeedback = false
                }
            }
        }

        // --> Add Observer for StartPoseAnalysisNotification <--
        NotificationCenter.default.addObserver(
            forName: VoiceManager.startPoseAnalysisNotification,
            object: nil,
            queue: .main
        ) { [self] notification in
            print("✅ ExerciseView received StartPoseAnalysisNotification")
            // We already have the correct exercise object as a property of this view
            poseAnalysisManager.startAnalysis(for: self.exercise)
        }
    }
    
    // MARK: - Actions
    
    private func cleanupResources() {
        // Clean up resources
        timer?.invalidate()
        timer = nil
        voiceManager.endElevenLabsSession()
        visionManager.stopProcessing()
        cameraManager.resetSession()
        resourceCoordinator.stopExerciseSession()
        
        // Deactivate audio session
        do {
            try AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
            print("Audio session deactivated successfully")
        } catch {
            print("Error deactivating audio session: \(error)")
        }
        
        // Clear any cached data
        URLCache.shared.removeAllCachedResponses()
    }
    
    private func stopExercise() {
        isStoppingExercise = true
        
        // Stop the timer
        timer?.invalidate()
        timer = nil
        
        // Calculate exercise duration
        exerciseDuration = exercise.duration - remainingTime
        
        // Set current exercise ID in VoiceManager and end session
        let exerciseId = exercise.firestoreId ?? exercise.id.uuidString
        voiceManager.setCurrentExercise(id: exerciseId)
        voiceManager.endExerciseSession()
        
        // Clean up resources
        resourceCoordinator.stopExerciseSession()
        visionManager.stopProcessing()
        cameraManager.resetSession()
        
        // Reset states and show report
        DispatchQueue.main.async {
            self.isExerciseActive = false
            self.isStoppingExercise = false
            self.showingExerciseReport = true
        }
    }
    
    private func handleError(_ message: String) {
        errorMessage = message
        showErrorAlert = true
    }
    
    private func timeString(from timeInterval: TimeInterval) -> String {
        let minutes = Int(timeInterval) / 60
        let seconds = Int(timeInterval) % 60
        return String(format: "%02d:%02d", minutes, seconds)
    }
    
    // Helper to determine if this is an RSI exercise
    private func isRSIExercise() -> Bool {
        // Check if exercise is for hands/wrists based on targetJoints
        let rsiJointTypes: Set<BodyJointType> = [
            .leftWrist, .rightWrist,
            .leftElbow, .rightElbow
        ]
        
        // Check if any of the exercise's target joints are wrist/hand related
        return exercise.targetJoints.contains { joint in
            rsiJointTypes.contains(joint)
        } || exercise.name.contains("RSI") || 
           exercise.name.contains("Wrist") || 
           exercise.name.contains("Hand") ||
           exercise.name.contains("Finger")
    }
}

// Camera preview for AVCaptureSession
struct CameraPreview: UIViewRepresentable {
    let session: AVCaptureSession
    
    func makeUIView(context: Context) -> UIView {
        let view = UIView(frame: UIScreen.main.bounds)
        
        let previewLayer = AVCaptureVideoPreviewLayer(session: session)
        previewLayer.frame = view.frame
        previewLayer.videoGravity = .resizeAspectFill
        view.layer.addSublayer(previewLayer)
        
        return view
    }
    
    func updateUIView(_ uiView: UIView, context: Context) {}
}

// Helper for pose analysis errors
struct PoseAnalysisError: Identifiable {
    let id = UUID()
    let message: String
}
