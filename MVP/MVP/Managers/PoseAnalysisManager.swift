import Foundation
import UIKit
import AVFoundation
import Combine

class PoseAnalysisManager: ObservableObject {
    // Published properties for UI updates
    @Published var isCapturing = false
    @Published var captureProgress: Double = 0
    @Published var error: String?
    
    // Configuration
    private let setupDelay: TimeInterval = 5.0
    private let captureInterval: TimeInterval = 2.0
    private let totalScreenshots = 8
    private let startScreenshots = false // client tool flag for elevenlabs
    
    // State
    private var screenshots: [String] = [] // Base64 encoded images
    private var captureTimer: Timer?
    private var screenshotCount = 0
    private weak var cameraManager: CameraManager?
    private let processingQueue = DispatchQueue(label: "com.app.poseAnalysis", qos: .userInitiated)
    private let cloudFunctionURL = URL(string: "YOUR_CLOUD_FUNCTION_URL")! // Replace with actual URL
    
    // Cancellables
    private var cancellables = Set<AnyCancellable>()
    
    private var capturedFrames: [(frame: CMSampleBuffer, timestamp: Date)] = []
    private var currentFrameCount = 0
    
    init(cameraManager: CameraManager) {
        self.cameraManager = cameraManager
    }
    
    func startAnalysis(for exercise: Exercise) {
        guard !isCapturing else { return }
        
        isCapturing = true
        screenshotCount = 0
        screenshots.removeAll()
        captureProgress = 0
        
        // Wait for setup delay before starting capture
        print("🎥 Waiting \(setupDelay) seconds for camera setup...")
        DispatchQueue.main.asyncAfter(deadline: .now() + setupDelay) { [weak self] in
            self?.startScreenshotCapture(for: exercise)
        }
    }
    
    private func startScreenshotCapture(for exercise: Exercise) {
        print("📸 Starting screenshot capture...")
        
        // Create a repeating timer for screenshots
        captureTimer = Timer.scheduledTimer(withTimeInterval: captureInterval, repeats: true) { [weak self] _ in
            guard let self = self else { return }
            
            // Capture screenshot on processing queue
            self.processingQueue.async {
                self.captureAndProcessScreenshot(for: exercise)
            }
        }
    }
    
    private func captureAndProcessScreenshot(for exercise: Exercise) {
        guard let image = captureScreenshot() else {
            handleError("Failed to capture screenshot")
            return
        }
        
        // Convert to base64
        guard let base64String = image.jpegData(compressionQuality: 0.7)?.base64EncodedString() else {
            handleError("Failed to encode image")
            return
        }
        
        // Update progress on main thread
        DispatchQueue.main.async {
            self.screenshotCount += 1
            self.captureProgress = Double(self.screenshotCount) / Double(self.totalScreenshots)
            
            // Upload screenshot immediately
            self.uploadScreenshot(base64String, for: exercise)
            
            // Check if we're done
            if self.screenshotCount >= self.totalScreenshots {
                self.finishCapture()
            }
        }
    }
    
    private func captureScreenshot() -> UIImage? {
        // Ensure we're on the processing queue
        dispatchPrecondition(condition: .onQueue(processingQueue))
        
        guard let cameraManager = cameraManager else { return nil }
        
        // Get the current video frame
        guard let currentFrame = cameraManager.getCurrentFrame() else { return nil }
        
        // Convert CMSampleBuffer to UIImage
        guard let imageBuffer = CMSampleBufferGetImageBuffer(currentFrame) else { return nil }
        
        let ciImage = CIImage(cvPixelBuffer: imageBuffer)
        let context = CIContext()
        guard let cgImage = context.createCGImage(ciImage, from: ciImage.extent) else { return nil }
        
        return UIImage(cgImage: cgImage)
    }
    
    private func uploadScreenshot(_ base64Image: String, for exercise: Exercise) {
        guard let url = cloudFunctionURL else { return }
        
        // Prepare the request body
        let body: [String: Any] = [
            "images": [base64Image],
            "exerciseInfo": [
                "userId": UserDefaults.standard.string(forKey: "userId") ?? "",
                "exerciseId": exercise.id.uuidString,
                "name": exercise.name,
                "instructions": exercise.instructions.joined(separator: ". ")
            ]
        ]
        
        // Create the request
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        do {
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        } catch {
            handleError("Failed to encode request: \(error.localizedDescription)")
            return
        }
        
        // Make the request
        URLSession.shared.dataTaskPublisher(for: request)
            .map { $0.data }
            .decode(type: AnalysisResponse.self, decoder: JSONDecoder())
            .receive(on: DispatchQueue.main)
            .sink(
                receiveCompletion: { [weak self] completion in
                    if case .failure(let error) = completion {
                        self?.handleError("Upload failed: \(error.localizedDescription)")
                    }
                },
                receiveValue: { response in
                    print("✅ Screenshot uploaded and processed successfully")
                }
            )
            .store(in: &cancellables)
    }
    
    private func finishCapture() {
        captureTimer?.invalidate()
        captureTimer = nil
        isCapturing = false
        print("✅ Pose analysis capture completed")
    }
    
    private func handleError(_ message: String) {
        print("❌ Pose analysis error: \(message)")
        DispatchQueue.main.async {
            self.error = message
            self.finishCapture()
        }
    }
    
    func captureFrame(_ frame: CMSampleBuffer) {
        guard isCapturing else { return }
        
        // Increment frame counter
        currentFrameCount += 1
        
        // Store frame with timestamp
        capturedFrames.append((frame: frame, timestamp: Date()))
        
        // Update progress
        captureProgress = min(1.0, Float(currentFrameCount) / Float(targetFrameCount))
        
        // Check if we've captured enough frames
        if currentFrameCount >= targetFrameCount {
            isCapturing = false
            processCapturedFrames()
        }
    }
    
    private func processCapturedFrames() {
        // Sort frames by timestamp to ensure correct sequence
        capturedFrames.sort { $0.timestamp < $1.timestamp }
        
        // Convert frames to base64 images
        var base64Images: [String] = []
        
        for (index, frameData) in capturedFrames.enumerated() {
            if let imageData = convertFrameToJPEG(frameData.frame) {
                let base64String = imageData.base64EncodedString()
                base64Images.append(base64String)
                print("📸 Processed frame \(index + 1) of \(capturedFrames.count)")
            }
        }
        
        // Send to backend
        sendFramesToBackend(base64Images)
        
        // Reset state
        capturedFrames.removeAll()
        currentFrameCount = 0
        captureProgress = 0
    }
    
    private func sendFramesToBackend(_ base64Images: [String]) {
        // ... existing backend communication code ...
        // The images array will now be properly sequenced
    }
}

// Response type for cloud function
struct AnalysisResponse: Codable {
    let success: Bool
    let message: String?
    let error: String?
} 