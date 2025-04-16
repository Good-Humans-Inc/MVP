import Foundation
import SwiftUI
import AVFoundation
import Combine

class CameraManager: NSObject, ObservableObject, AVCaptureVideoDataOutputSampleBufferDelegate {
    // Reference to AppState
    private let appState: AppState
    
    // Reference to VisionManager
    private weak var visionManager: VisionManager?
    
    // Published properties
    @Published var isSessionRunning = false
    @Published var isCameraAuthorized = false
    @Published var cameraError: String?
    
    // Camera capture session
    let session = AVCaptureSession()
    var videoOutput = AVCaptureVideoDataOutput()
    
    // Video processing queue
    private let videoProcessingQueue = DispatchQueue(label: "com.kneerecovery.videoProcessing",
                                                     qos: .userInteractive)
    
    private var setupResult: SessionSetupResult = .notDetermined
    private enum SessionSetupResult {
        case success
        case notAuthorized
        case configurationFailed
        case notDetermined
    }
    
    // Completion handler for asynchronous operations
    private var startSessionCompletion: (() -> Void)?
    
    // Flag to track if session is currently being set up
    private var isSettingUpSession = false
    
    // Maximum attempts to start session
    private var startAttempts = 0
    private let maxStartAttempts = 3
    
    // Flag to determine if we should post notifications
    private var shouldPostNotifications = false
    
    // Add new properties for frame capture
    private var currentVideoFrame: CMSampleBuffer?
    private let frameAccessQueue = DispatchQueue(label: "com.app.frameAccess", qos: .userInteractive)
    
    // Initialize with AppState
    init(appState: AppState, visionManager: VisionManager? = nil) {
        self.appState = appState
        self.visionManager = visionManager
        super.init()
        
        // Update camera state
        updateCameraState(isRunning: isSessionRunning)
        updateCameraState(isAuthorized: isCameraAuthorized)
        
        // Check camera authorization status
        checkAuthorization()
        
        print("📷 CameraManager initialized")
    }
    
    // Update camera state in AppState
    private func updateCameraState(isRunning: Bool? = nil, isAuthorized: Bool? = nil, error: String? = nil) {
        DispatchQueue.main.async {
            if let isRunning = isRunning {
                self.appState.cameraState.isSessionRunning = isRunning
            }
            if let isAuthorized = isAuthorized {
                self.appState.cameraState.isCameraAuthorized = isAuthorized
            }
            if let error = error {
                self.appState.cameraState.cameraError = error
            }
        }
    }
    
    func checkAuthorization() {
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized:
            self.setupResult = .success
            self.updateCameraState(isAuthorized: true)
            print("📷 Camera authorization: already authorized")
        case .notDetermined:
            // Request permission
            print("📷 Camera authorization: requesting permission")
            AVCaptureDevice.requestAccess(for: .video) { granted in
                DispatchQueue.main.async {
                    if granted {
                        self.setupResult = .success
                        self.updateCameraState(isAuthorized: true)
                        print("📷 Camera authorization: permission granted")
                    } else {
                        self.setupResult = .notAuthorized
                        self.updateCameraState(isAuthorized: false)
                        print("📷 Camera authorization: permission denied")
                    }
                }
            }
        default:
            setupResult = .notAuthorized
            self.updateCameraState(isAuthorized: false)
            print("📷 Camera authorization: not authorized")
        }
    }
    
    // Force reset the session completely - useful for first launch issues
    func resetSession() {
        print("📷 Force resetting camera session")
        
        // First stop any running session
        if session.isRunning {
            session.stopRunning()
            updateCameraState(isRunning: false)
        }
        
        // Clear all inputs and outputs
        session.beginConfiguration()
        
        // Remove all existing inputs
        for input in session.inputs {
            session.removeInput(input)
        }
        
        // Remove all existing outputs
        for output in session.outputs {
            session.removeOutput(output)
        }
        
        session.commitConfiguration()
        
        // Reset setup result
        setupResult = .notDetermined
        
        // Check authorization again
        checkAuthorization()
        
        // Reset start attempts counter
        startAttempts = 0
        
        print("📷 Camera session reset complete")
    }
    
    func setupSession() {
        if isSettingUpSession {
            print("📷 Camera session already being set up, ignoring duplicate call")
            return
        }
        
        isSettingUpSession = true
        
        if setupResult != .success {
            print("📷 Camera setup result not successful: \(setupResult)")
            isSettingUpSession = false
            return
        }
        
        // First, check if we need to clean up existing configuration
        if !session.inputs.isEmpty || !session.outputs.isEmpty {
            print("📷 Clearing existing camera session configuration")
            session.beginConfiguration()
            
            // Remove all existing inputs
            for input in session.inputs {
                session.removeInput(input)
            }
            
            // Remove all existing outputs
            for output in session.outputs {
                session.removeOutput(output)
            }
            
            session.commitConfiguration()
        }
        
        print("📷 Setting up camera session...")
        
        session.beginConfiguration()
        
        session.sessionPreset = .high
        
        // Add video input
        do {
            var defaultVideoDevice: AVCaptureDevice?
            
            // For RSI exercises use front camera as default for easier hand tracking
            if let frontCameraDevice = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .front) {
                defaultVideoDevice = frontCameraDevice
                print("📷 Using front camera for hand tracking")
            } else {
                // No front camera, use default
                defaultVideoDevice = AVCaptureDevice.default(for: .video)
                print("📷 Front camera not available, using default camera")
            }
            
            guard let videoDevice = defaultVideoDevice else {
                print("📷 Default video device is unavailable.")
                setupResult = .configurationFailed
                session.commitConfiguration()
                isSettingUpSession = false
                
                if shouldPostNotifications {
                    NotificationCenter.default.post(name: .cameraSessionDidFail, object: self)
                }
                return
            }
            
            let videoDeviceInput = try AVCaptureDeviceInput(device: videoDevice)
            
            if session.canAddInput(videoDeviceInput) {
                session.addInput(videoDeviceInput)
                print("📷 Added video device input to session")
            } else {
                print("📷 Couldn't add video device input to the session.")
                setupResult = .configurationFailed
                session.commitConfiguration()
                isSettingUpSession = false
                
                if shouldPostNotifications {
                    NotificationCenter.default.post(name: .cameraSessionDidFail, object: self)
                }
                return
            }
        } catch {
            print("📷 Couldn't create video device input: \(error)")
            setupResult = .configurationFailed
            session.commitConfiguration()
            isSettingUpSession = false
            
            if shouldPostNotifications {
                NotificationCenter.default.post(name: .cameraSessionDidFail, object: self)
            }
            return
        }
        
        // Add video output
        if session.canAddOutput(videoOutput) {
            session.addOutput(videoOutput)
            
            videoOutput.setSampleBufferDelegate(self, queue: videoProcessingQueue)
            videoOutput.alwaysDiscardsLateVideoFrames = true
            videoOutput.videoSettings = [kCVPixelBufferPixelFormatTypeKey as String: Int(kCVPixelFormatType_32BGRA)]
            
            if let connection = videoOutput.connection(with: .video) {
                if connection.isVideoOrientationSupported {
                    connection.videoOrientation = .portrait
                    print("📷 Set video orientation to portrait")
                }
                if connection.isVideoMirroringSupported {
                    connection.isVideoMirrored = true
                    print("📷 Enabled video mirroring for front camera")
                }
            }
            print("📷 Added video output to session")
        } else {
            print("📷 Could not add video output to the session")
            setupResult = .configurationFailed
            session.commitConfiguration()
            isSettingUpSession = false
            
            if shouldPostNotifications {
                NotificationCenter.default.post(name: .cameraSessionDidFail, object: self)
            }
            return
        }
        
        session.commitConfiguration()
        print("📷 Camera session setup completed successfully")
        
        isSettingUpSession = false
    }
    
    // Method with option to post notifications about camera status
    func startSession(withNotification: Bool = false, completion: (() -> Void)? = nil) {
        startSessionCompletion = completion
        shouldPostNotifications = withNotification
        
        // Reset start attempts counter on fresh start
        if !session.isRunning {
            startAttempts = 0
        }
        
        if session.isRunning {
            print("📷 Camera session already running")
            DispatchQueue.main.async {
                self.updateCameraState(isRunning: true)
                
                // Still post the notification if requested
                if withNotification {
                    NotificationCenter.default.post(name: .cameraSessionDidStart, object: self)
                }
                
                self.startSessionCompletion?()
                self.startSessionCompletion = nil
            }
            return
        }
        
        // Increment attempt counter
        startAttempts += 1
        print("📷 Camera session start attempt #\(startAttempts)")
        
        // Check if we've exceeded max attempts
        if startAttempts > maxStartAttempts {
            print("⚠️ Exceeded maximum camera start attempts, notifying failure")
            DispatchQueue.main.async {
                if self.shouldPostNotifications {
                    NotificationCenter.default.post(name: .cameraSessionDidFail, object: self)
                }
                self.startSessionCompletion?()
                self.startSessionCompletion = nil
            }
            return
        }
        
        if setupResult != .success {
            checkAuthorization()
        }
        
        if setupResult == .success {
            print("📷 Setting up camera session...")
            setupSession()
            
            // Use background queue for starting the session
            videoProcessingQueue.async {
                // Add a robust check to make sure session isn't already running
                if !self.session.isRunning {
                    print("📷 Starting camera session...")
                    self.session.startRunning()
                    
                    // Check if session actually started
                    let sessionRunning = self.session.isRunning
                    print("📷 Camera session running status: \(sessionRunning)")
                    
                    DispatchQueue.main.async {
                        self.updateCameraState(isRunning: sessionRunning)
                        
                        if sessionRunning {
                            // Success - post notification if requested
                            if self.shouldPostNotifications {
                                NotificationCenter.default.post(name: .cameraSessionDidStart, object: self)
                            }
                        } else {
                            // Failure - either retry or notify failure
                            if self.startAttempts < self.maxStartAttempts {
                                // Retry with a delay
                                print("⚠️ Camera session didn't start, retrying...")
                                DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                                    self.startSession(withNotification: self.shouldPostNotifications,
                                                     completion: self.startSessionCompletion)
                                }
                                return
                            } else if self.shouldPostNotifications {
                                // Max retries exceeded - notify failure
                                NotificationCenter.default.post(name: .cameraSessionDidFail, object: self)
                            }
                        }
                        
                        self.startSessionCompletion?()
                        self.startSessionCompletion = nil
                    }
                } else {
                    print("📷 Session was already running in background")
                    DispatchQueue.main.async {
                        self.updateCameraState(isRunning: true)
                        
                        // Session was running already - still post notification if requested
                        if self.shouldPostNotifications {
                            NotificationCenter.default.post(name: .cameraSessionDidStart, object: self)
                        }
                        
                        self.startSessionCompletion?()
                        self.startSessionCompletion = nil
                    }
                }
            }
        } else {
            print("❌ Camera setup result not successful: \(setupResult)")
            DispatchQueue.main.async {
                // Notify failure
                if self.shouldPostNotifications {
                    NotificationCenter.default.post(name: .cameraSessionDidFail, object: self)
                }
                
                self.startSessionCompletion?()
                self.startSessionCompletion = nil
            }
        }
    }
    
    func stopSession() {
        print("📷 Stopping camera session")
        if session.isRunning {
            videoProcessingQueue.async {
                self.session.stopRunning()
                DispatchQueue.main.async {
                    self.updateCameraState(isRunning: self.session.isRunning)
                    print("📷 Camera session stopped")
                }
            }
        } else {
            print("📷 Camera session already stopped")
        }
        
        // Reset notification flag
        shouldPostNotifications = false
    }
    
    // Clean up method
    func cleanUp() {
        print("📷 Cleaning up camera resources")
        stopSession()
        isSessionRunning = false
        updateCameraState(isRunning: false)
    }
    
    // MARK: - AVCaptureVideoDataOutputSampleBufferDelegate
    
    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        // Store the current frame
        frameAccessQueue.sync {
            self.currentVideoFrame = sampleBuffer
        }
        
        // Forward the frame to VisionManager for processing
        if let visionManager = visionManager {
            visionManager.processFrame(sampleBuffer)
        }
    }
    
    func captureOutput(_ output: AVCaptureOutput, didDrop sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        // Called when a frame is dropped
        print("📷 Camera frame dropped")
    }
    
    // Add method to get current frame
    func getCurrentFrame() -> CMSampleBuffer? {
        var frame: CMSampleBuffer?
        frameAccessQueue.sync {
            frame = self.currentVideoFrame
        }
        return frame
    }
}

// MARK: - Notification names for camera status
extension Notification.Name {
    static let cameraSessionDidStart = Notification.Name("CameraSessionDidStart")
    static let cameraSessionDidFail = Notification.Name("CameraSessionDidFail")
}
