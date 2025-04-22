import Foundation
import Vision
import AVFoundation
import UIKit
import Combine

class VisionManager: NSObject, ObservableObject {
    // Reference to AppState
    private let appState: AppState
    
    // Vision request handlers
    private var requests = [VNRequest]()
    
    // Published properties for UI updates
    @Published var currentBodyPose: BodyPose?
    @Published var currentHandPose: HandPose?
    @Published var detectedJoints: Set<BodyJointType> = []
    @Published var painPoints: Set<BodyJointType> = []
    @Published var exerciseQuality: ExerciseQuality = .cannotDetermine
    @Published var isProcessing = false
    @Published var processingError: String?
    @Published var detectedHands: [VNHumanHandPoseObservation] = []
    @Published var isLeftHand: Bool = true // Track which hand is detected
    
    // Transform matrix for coordinate conversion
    private var transformMatrix: CGAffineTransform = .identity
    
    // Vision requests
    private var bodyPoseRequest: VNDetectHumanBodyPoseRequest?
    private var handPoseRequest: VNDetectHumanHandPoseRequest?
    private var currentExercise: Exercise?
    
    // Processing queue
    private let visionQueue = DispatchQueue(label: "com.rsirecovery.visionProcessing",
                                          qos: .userInteractive)
    
    // Timer for controlling frame processing rate
    private var processingTimer: Timer?
    private let frameProcessingInterval: TimeInterval = 0.1 // Process frames every 100ms
    
    // Size info for coordinate conversion
    private var previewLayer: CGRect = .zero
    
    // Frame count for performance tracking
    private var frameCount = 0
    private var lastFpsUpdate = Date()
    @Published var currentFps: Double = 0
    
    private var lastProcessedTime: Date = Date()
    private let minimumProcessingInterval: TimeInterval = 0.1 // 10 frames per second
    
    // Initialize with AppState
    init(appState: AppState) {
        self.appState = appState
        super.init()
        
        // Configure vision for hand tracking
        setupVision()
        print("👁 VisionManager initialized for hand tracking")
    }
    
    private func setupVision() {
        bodyPoseRequest = VNDetectHumanBodyPoseRequest()
        handPoseRequest = VNDetectHumanHandPoseRequest()
        
        // Configure to track all hand landmark points for RSI exercise tracking
        handPoseRequest?.revision = VNDetectHumanHandPoseRequestRevision1
        
        requests = [handPoseRequest!] // Add to requests array
        
        print("👁 Vision requests configured for hand tracking")
    }
    
    func startProcessing(_ videoOutput: AVCaptureVideoDataOutput) {
        isProcessing = true
        frameCount = 0
        lastFpsUpdate = Date()
        
        // Set up the preview layer size
        DispatchQueue.main.async {
            self.previewLayer = UIScreen.main.bounds
            // Update transform matrix
            self.transformMatrix = CGAffineTransform(scaleX: self.previewLayer.width, y: self.previewLayer.height)
        }
        
        print("👁 Started hand pose processing")
    }
    
    func stopProcessing() {
        isProcessing = false
        print("👁 Stopped hand pose processing")
    }
    
    func processFrame(_ sampleBuffer: CMSampleBuffer) {
        guard isProcessing,
              let imageBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else {
            return
        }
        
        // Increment frame counter for FPS calculation
        frameCount += 1
        
        // Update FPS every second
        let now = Date()
        if now.timeIntervalSince(lastFpsUpdate) >= 1.0 {
            let elapsed = now.timeIntervalSince(lastFpsUpdate)
            DispatchQueue.main.async { [weak self] in
                guard let self = self else { return }
                self.currentFps = Double(self.frameCount) / elapsed
            }
            frameCount = 0
            lastFpsUpdate = now
        }
        
        // Add throttling to reduce processing frequency
        if now.timeIntervalSince(lastProcessedTime) < minimumProcessingInterval {
            return // Skip this frame to maintain performance
        }
        lastProcessedTime = now
        
        // Process hand pose detection
        let handler = VNImageRequestHandler(cvPixelBuffer: imageBuffer, orientation: .up, options: [:])
        
        do {
            // Process body pose
            if let bodyPoseRequest = bodyPoseRequest {
                try handler.perform([bodyPoseRequest])
                if let observation = bodyPoseRequest.results?.first {
                    processBodyPoseObservation(observation)
                }
            }
            
            // Process hand pose
            if let handPoseRequest = handPoseRequest {
                try handler.perform([handPoseRequest])
                if let observation = handPoseRequest.results?.first {
                    processHandPoseObservation(observation)
                }
            }
        } catch {
            print("👁 Vision processing error: \(error)")
            DispatchQueue.main.async { [weak self] in
                guard let self = self else { return }
                self.processingError = error.localizedDescription
                self.appState.visionState.error = error.localizedDescription
            }
        }
    }
    
    private func processBodyPoseObservation(_ observation: VNHumanBodyPoseObservation) {
        var bodyPose = BodyPose()
        var detectedJoints: Set<BodyJointType> = []
        
        // Process each joint type
        for jointType in BodyJointType.allCases {
            if let visionJoint = jointType.visionJointName,
               let point = try? observation.recognizedPoint(visionJoint) {
                let joint = BodyJoint(
                    id: jointType,
                    position: CGPoint(x: point.location.x, y: 1 - point.location.y),
                    confidence: point.confidence
                )
                bodyPose.joints[jointType] = joint
                
                if joint.isValid {
                    detectedJoints.insert(jointType)
                }
            }
        }
        
        DispatchQueue.main.async {
            self.currentBodyPose = bodyPose
            self.detectedJoints = detectedJoints
            self.detectPainPoints(from: bodyPose)
            
            // Update AppState
            self.appState.visionState.currentBodyPose = bodyPose
            self.appState.visionState.isProcessing = true
            self.appState.visionState.error = nil
            
            // Log joint stats every 30 frames (about 1 second at 30fps)
            if self.frameCount % 30 == 0 {
                self.logHandStats(bodyPose)
            }
        }
    }
    
    private func processHandPoseObservation(_ observation: VNHumanHandPoseObservation) {
        var handPose = HandPose()
        
        // Process each hand joint type
        for jointType in HandJointType.allCases {
            if let visionPoint = jointType.visionPointName,
               let point = try? observation.recognizedPoint(visionPoint) {
                let joint = HandJoint(
                    id: jointType,
                    position: CGPoint(x: point.location.x, y: 1 - point.location.y),
                    confidence: point.confidence
                )
                handPose.joints[jointType] = joint
            }
        }
        
        // Determine if it's left or right hand
        if let observation = observation as? VNRecognizedPointsObservation {
            handPose.isLeftHand = observation.points.count > 0
        }
        
        DispatchQueue.main.async {
            self.currentHandPose = handPose
            
            // Update AppState
            self.appState.visionState.currentHandPose = handPose
            self.appState.visionState.isProcessing = true
            self.appState.visionState.error = nil
            
            // Log joint stats every 30 frames (about 1 second at 30fps)
            if self.frameCount % 30 == 0 {
                self.logHandStats(handPose)
            }
        }
    }
    
    // MARK: - Pain Point Detection
    func detectPainPoints(from bodyPose: BodyPose) {
        var detectedPains: Set<BodyJointType> = []
        
        // Check shoulder group
        if let leftShoulder = bodyPose.joints[.leftShoulder],
           let rightShoulder = bodyPose.joints[.rightShoulder] {
            if leftShoulder.confidence > 0.7 || rightShoulder.confidence > 0.7 {
                detectedPains.formUnion(BodyJointType.shoulderGroup)
            }
        }
        
        // Check knee group
        if let leftKnee = bodyPose.joints[.leftKnee],
           let rightKnee = bodyPose.joints[.rightKnee] {
            if leftKnee.confidence > 0.7 || rightKnee.confidence > 0.7 {
                detectedPains.formUnion(BodyJointType.kneeGroup)
            }
        }
        
        // Check lower back group
        if let spine = bodyPose.joints[.spine],
           let root = bodyPose.joints[.root] {
            if spine.confidence > 0.7 || root.confidence > 0.7 {
                detectedPains.formUnion(BodyJointType.lowerBackGroup)
            }
        }
        
        // Check ankle group
        if let leftAnkle = bodyPose.joints[.leftAnkle],
           let rightAnkle = bodyPose.joints[.rightAnkle] {
            if leftAnkle.confidence > 0.7 || rightAnkle.confidence > 0.7 {
                detectedPains.formUnion(BodyJointType.ankleGroup)
            }
        }
        
        DispatchQueue.main.async {
            self.painPoints = detectedPains
        }
    }
    
    // MARK: - Exercise Recommendation
    func recommendExercises(for painPoints: Set<BodyJointType>) -> [Exercise] {
        var recommendedExercises: [Exercise] = []
        
        for joint in painPoints {
            let exercises = ExerciseCatalog.getExercisesForJoint(joint)
            recommendedExercises.append(contentsOf: exercises)
        }
        
        // Remove duplicates and limit to 5 exercises
        return Array(Set(recommendedExercises)).prefix(5).map { $0 }
    }
    
    // MARK: - Exercise Tracking
    func startTrackingExercise(_ exercise: Exercise) {
        currentExercise = exercise
    }
    
    func stopTrackingExercise() {
        currentExercise = nil
        exerciseQuality = .cannotDetermine
    }
    
    // Log hand stats for debugging
    private func logHandStats(_ handPose: HandPose) {
        DispatchQueue.main.async {
            // Get finger extension values
            let extensionValues = handPose.getFingerExtensionValues()
            print("HAND STATS (FINGER EXTENSION):")
            for (finger, value) in extensionValues {
                print("- \(finger): \(value)")
            }
            
            // Log wrist angle if available
            if let wristAngle = handPose.getWristAngle() {
                print("- Wrist angle: \(wristAngle)°")
            }
            
            print("-----------------------------------")
        }
    }
    
    // Clean up resources
    func cleanUp() {
        DispatchQueue.main.async {
            self.isProcessing = false
            self.detectedHands.removeAll()
            self.processingError = nil
        }
    }
}

// Extension for AppState integration
extension AppState {
    // Update VisionState to handle hand poses
    class VisionState: ObservableObject {
        @Published var currentBodyPose: BodyPose?
        @Published var currentHandPose: HandPose?
        @Published var detectedJoints: Set<BodyJointType> = []
        @Published var painPoints: Set<BodyJointType> = []
        @Published var exerciseQuality: ExerciseQuality = .cannotDetermine
        @Published var isProcessing = false
        @Published var error: String?
        
        func cleanup() {
            currentBodyPose = nil
            currentHandPose = nil
            detectedJoints.removeAll()
            painPoints.removeAll()
            exerciseQuality = .cannotDetermine
            isProcessing = false
            error = nil
        }
    }
}
