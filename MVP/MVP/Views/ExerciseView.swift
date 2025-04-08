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
    @State private var coachMessages: [String] = []
    @State private var showCoachFeedback = false
    @State private var isStoppingExercise = false
    
    // Environment objects
    @Environment(\.presentationMode) var presentationMode
    @EnvironmentObject private var appState: AppState
    @EnvironmentObject private var cameraManager: CameraManager
    @EnvironmentObject private var visionManager: VisionManager
    @EnvironmentObject private var voiceManager: VoiceManager
    @EnvironmentObject private var resourceCoordinator: ResourceCoordinator
    
    var body: some View {
        ZStack {
            // Camera feed with body pose visualization overlay
            CameraPreview(session: cameraManager.session)
                .edgesIgnoringSafeArea(.all)
            
            // Body pose overlay
            BodyPoseView(bodyPose: visionManager.currentBodyPose)
                .edgesIgnoringSafeArea(.all)
            
            // Coach message bubble if there are messages
            if !coachMessages.isEmpty, showCoachFeedback {
                coachMessageView
            }
            
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
            // Clean up resources
            timer?.invalidate()
            timer = nil
            voiceManager.endElevenLabsSession()
            visionManager.stopProcessing()
            cameraManager.resetSession()
            resourceCoordinator.stopExerciseSession()
            
            // Deactivate audio session when leaving
            do {
                try AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
            } catch {
                print("Error deactivating audio session: \(error)")
            }
        }
        .fullScreenCover(isPresented: $showingExerciseReport) {
            ReportView(
                exercise: exercise,
                duration: exerciseDuration
            )
        }
    }
    
    // MARK: - UI Components
    
    // Coach message view
    private var coachMessageView: some View {
        VStack {
            Text(coachMessages.last ?? "")
                .padding()
                .background(Color.white.opacity(0.8))
                .foregroundColor(.black)
                .cornerRadius(12)
                .padding(.horizontal)
                .padding(.top, 40)
            
            Spacer()
        }
    }
    
    // Controls view for active exercise
    private var exerciseControlsView: some View {
        VStack {
            Spacer()
            
            // Timer display
            Text(timeString(from: remainingTime))
                .font(.system(size: 48, weight: .bold, design: .rounded))
                .foregroundColor(.white)
                .padding()
                .background(Color.black.opacity(0.5))
                .cornerRadius(16)
            
            Spacer()
            
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
        coachMessages = ["I'll help guide you through this exercise. Let me see your form..."]
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
            print("Error configuring audio session: \(error)")
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
            self.coachMessages.append(message)
            
            // Show the feedback
            self.showCoachFeedback = true
            
            // Auto-hide after a delay
            DispatchQueue.main.asyncAfter(deadline: .now() + 5) {
                if self.isExerciseActive {
                    self.showCoachFeedback = false
                }
            }
        }
    }
    
    // MARK: - Actions
    
    private func stopExercise() {
        isStoppingExercise = true
        
        // Stop the timer
        timer?.invalidate()
        timer = nil
        
        // Calculate exercise duration
        exerciseDuration = exercise.duration - remainingTime
        
        // Set current exercise ID in VoiceManager and end session
        if let exerciseId = exercise.firestoreId ?? exercise.id.uuidString {
            voiceManager.setCurrentExercise(id: exerciseId)
        }
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
    
    private func timeString(from timeInterval: TimeInterval) -> String {
        let minutes = Int(timeInterval) / 60
        let seconds = Int(timeInterval) % 60
        return String(format: "%02d:%02d", minutes, seconds)
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
