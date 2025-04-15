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
    @Published var currentHandPose = HandPose()
    @Published var isProcessing = false
    @Published var processingError: String?
    @Published var detectedHands: [VNHumanHandPoseObservation] = []
    @Published var isLeftHand: Bool = true // Track which hand is detected
    
    // Transform matrix for coordinate conversion
    private var transformMatrix: CGAffineTransform = .identity
    
    // Vision requests
    private var handPoseRequest: VNDetectHumanHandPoseRequest!
    
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
        // Create and configure the hand pose detection request
        handPoseRequest = VNDetectHumanHandPoseRequest()
        handPoseRequest.maximumHandCount = 1 // Focus on one hand at a time for RSI exercises
        
        // Configure to track all hand landmark points for RSI exercise tracking
        handPoseRequest.revision = VNDetectHumanHandPoseRequestRevision1
        
        requests = [handPoseRequest] // Add to requests array
        
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
            try handler.perform(requests)
            
            guard let observations = handPoseRequest.results, !observations.isEmpty else {
                // No hands detected
                return
            }
            
            // Take the first hand observation (we set maximumHandCount to 1)
            let observation = observations[0]
            
            // Use confidence threshold for detection quality
            guard observation.confidence > 0.6 else {
                // Low confidence detection, skip
                return
            }
            
            print("👁 Hand detected with confidence: \(observation.confidence)")
            
            // Determine if it's a left or right hand (simplified method)
            determineHandOrientation(observation)
            
            // Convert the hand observation to our HandPose model
            let handPose = createHandPose(from: observation)
            
            // Update all UI-related state on the main thread
            DispatchQueue.main.async { [weak self] in
                guard let self = self else { return }
                
                // Update detected hands
                self.detectedHands = observations
                
                // Update current hand pose
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
        } catch {
            print("👁 Vision processing error: \(error)")
            DispatchQueue.main.async { [weak self] in
                guard let self = self else { return }
                self.processingError = error.localizedDescription
                self.appState.visionState.error = error.localizedDescription
            }
        }
    }
    
    // Convert VNHumanHandPoseObservation to our HandPose model
    private func createHandPose(from observation: VNHumanHandPoseObservation) -> HandPose {
        var handPose = HandPose()
        handPose.isLeftHand = isLeftHand
        
        // Process each joint from the observation
        for jointType in HandJointType.allCases {
            guard let visionPointName = jointType.visionPointName else { continue }
            
            do {
                let jointPoint = try observation.recognizedPoint(visionPointName)
                
                // Only process joints with sufficient confidence
                if jointPoint.confidence > 0.3 {
                    let normalizedPosition = CGPoint(x: jointPoint.x, y: 1 - jointPoint.y) // Flip Y coordinate
                    let transformedPosition = normalizedPosition.applying(transformMatrix)
                    
                    handPose.joints[jointType] = HandJoint(
                        id: jointType,
                        position: transformedPosition,
                        confidence: jointPoint.confidence
                    )
                }
            } catch {
                print("👁 Error getting joint \(jointType): \(error)")
            }
        }
        
        return handPose
    }
    
    // Determine if the observed hand is left or right
    private func determineHandOrientation(_ observation: VNHumanHandPoseObservation) {
        // Simple heuristic: check if thumb is on left or right side of hand
        do {
            let wrist = try observation.recognizedPoint(.wrist)
            let thumbTip = try observation.recognizedPoint(.thumbTip)
            let indexTip = try observation.recognizedPoint(.indexTip)
            
            // If thumb is to the left of index finger (from camera's perspective),
            // it's likely a right hand; otherwise, it's a left hand
            let thumbToWristX = thumbTip.x - wrist.x
            let indexToWristX = indexTip.x - wrist.x
            
            // This simple heuristic is based on the typical position of the thumb
            // relative to the fingers when the palm is facing the camera
            let detectedIsLeftHand = thumbToWristX > indexToWristX
            
            // Update isLeftHand on main thread
            DispatchQueue.main.async {
                self.isLeftHand = detectedIsLeftHand
                print("👁 Hand orientation detected: \(detectedIsLeftHand ? "Left" : "Right") hand")
            }
        } catch {
            print("👁 Error determining hand orientation: \(error)")
            // Default to left hand if determination fails
            DispatchQueue.main.async {
                self.isLeftHand = true
            }
        }
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
        @Published var currentHandPose = HandPose()
        @Published var isProcessing = false
        @Published var error: String?
        
        func cleanup() {
            currentHandPose = HandPose()
            isProcessing = false
            error = nil
        }
    }
}
