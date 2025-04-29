import Foundation
import UIKit
import AVFoundation
import Combine

class PoseAnalysisManager: ObservableObject {
    // Published properties for UI updates
    @Published var isCapturing = false
    @Published var captureProgress: Double = 0
    @Published var error: String?
    
    // Reference to AppState
    private let appState: AppState
    
    // Configuration
    private let setupDelay: TimeInterval = 5.0
    private let captureInterval: TimeInterval = 2.0
    private let totalScreenshots = 8
    private let targetFrameCount = 8
    
    // State
    private var screenshots: [String] = [] // Base64 encoded images
    private var captureTimer: Timer?
    private var screenshotCount = 0
    private weak var cameraManager: CameraManager?
    private let processingQueue = DispatchQueue(label: "com.app.poseAnalysis", qos: .userInitiated)
    
    // Cloud Function URL
    private let cloudFunctionURL = URL(string: "https://us-central1-pepmvp.cloudfunctions.net/analyze_exercise_poses")!
    
    // Cancellables
    private var cancellables = Set<AnyCancellable>()
    
    private var capturedFrames: [(frame: CMSampleBuffer, timestamp: Date)] = []
    private var currentFrameCount = 0
    
    init(cameraManager: CameraManager, appState: AppState) {
        self.cameraManager = cameraManager
        self.appState = appState
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
            // Store the screenshot for batch upload
            self.screenshots.append(base64String)
            self.screenshotCount += 1
            self.captureProgress = Double(self.screenshotCount) / Double(self.totalScreenshots)
            
            print("📸 Captured screenshot \(self.screenshotCount) of \(self.totalScreenshots)")
            
            // Check if we're done
            if self.screenshotCount >= self.totalScreenshots {
                print("✅ All screenshots captured, preparing batch upload...")
                // Upload all screenshots in a single batch
                self.uploadScreenshots(self.screenshots, for: exercise)
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
    
    private func finishCapture() {
        captureTimer?.invalidate()
        captureTimer = nil
        isCapturing = false
        screenshots.removeAll()
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
        captureProgress = Double(currentFrameCount) / Double(targetFrameCount)
        
        // Check if we've captured enough frames
        if currentFrameCount >= targetFrameCount {
            isCapturing = false
            processCapturedFrames()
        }
    }
    
    // Process the captured frames for analysis
    func processCapturedFrames() {
        // Perform analysis based on exercise type
        guard let currentExercise = appState.currentExercise else {
            handleError("No current exercise set for analysis")
            return
        }
        
        let exerciseData: [String: Any] = [
            "exerciseName": currentExercise.name,
            "exerciseType": currentExercise.isHandExercise ? "hand" : "body", 
            "targetJoints": currentExercise.isHandExercise 
                ? currentExercise.handJointTargets.map { $0.rawValue } 
                : currentExercise.targetJoints.map { $0.rawValue },
            "timestamp": ISO8601DateFormatter().string(from: Date())
        ]
        
        // Process the analysis
        DispatchQueue.main.async {
            print("✅ Analysis completed for \(currentExercise.name)")
            self.finishCapture()
            
            // For now, just log the analysis data
            print("📊 Exercise Data: \(exerciseData)")
        }
    }
    
    private func convertFrameToJPEG(_ sampleBuffer: CMSampleBuffer) -> Data? {
        guard let imageBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else {
            print("❌ Failed to get image buffer")
            return nil
        }
        
        let ciImage = CIImage(cvPixelBuffer: imageBuffer)
        let context = CIContext()
        guard let cgImage = context.createCGImage(ciImage, from: ciImage.extent) else {
            print("❌ Failed to create CGImage")
            return nil
        }
        
        let uiImage = UIImage(cgImage: cgImage)
        
        // Try different compression qualities if the image is too large
        let compressionQualities: [CGFloat] = [0.8, 0.5, 0.3]
        
        for quality in compressionQualities {
            if let data = uiImage.jpegData(compressionQuality: quality) {
                let sizeInMB = Double(data.count) / 1_000_000.0
                print("📊 Image size at quality \(quality): \(String(format: "%.2f", sizeInMB))MB")
                
                // If size is reasonable, use this version
                if sizeInMB < 1.0 {  // Less than 1MB
                    return data
                }
            }
        }
        
        // If we get here, try the lowest quality as a last resort
        return uiImage.jpegData(compressionQuality: 0.1)
    }
    
    private func uploadScreenshots(_ base64Images: [String], for exercise: Exercise) {
        guard let userId = UserDefaults.standard.string(forKey: "userId") else {
            handleError("No user ID found")
            return
        }

        print("\n🎯 Starting Batch Upload:")
        print("--------------------------------")
        print("📤 Request Details:")
        print("- Number of images: \(base64Images.count)")
        print("- Exercise ID: \(exercise.id.uuidString.lowercased())")
        print("- User ID: \(userId)")
        print("- Exercise Name: \(exercise.name)")
        
        // Create the request
        var request = URLRequest(url: cloudFunctionURL)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        // Prepare the request body
        let body: [String: Any] = [
            "images": base64Images,
            "exerciseInfo": [
                "userId": userId,
                "exerciseId": exercise.id.uuidString.lowercased(),
                "name": exercise.name,
                "instructions": exercise.instructions.joined(separator: ". ")
            ]
        ]
        
        do {
            let jsonData = try JSONSerialization.data(withJSONObject: body)
            request.httpBody = jsonData
            
            print("\n📊 Request Metrics:")
            print("- Total payload size: \(String(format: "%.2f", Double(jsonData.count) / 1_000_000.0))MB")
            print("- Average image size: \(String(format: "%.2f", Double(jsonData.count) / Double(base64Images.count) / 1_000_000.0))MB")
            print("--------------------------------")
        } catch {
            print("❌ Batch Upload JSON Serialization Error:")
            print(error)
            handleError("Failed to encode batch request: \(error.localizedDescription)")
            return
        }
        
        print("⏳ Sending batch request to Cloud Function...")
        
        URLSession.shared.dataTaskPublisher(for: request)
            .map { data, response -> Data in
                print("\n📥 Received Batch Response:")
                print("--------------------------------")
                
                if let httpResponse = response as? HTTPURLResponse {
                    print("- Status code: \(httpResponse.statusCode)")
                    print("- Response size: \(String(format: "%.2f", Double(data.count) / 1_000.0))KB")
                    
                    if httpResponse.statusCode != 200 {
                        print("⚠️ Unexpected status code: \(httpResponse.statusCode)")
                    }
                }
                
                if let responseString = String(data: data, encoding: .utf8) {
                    print("\n📄 Response Body:")
                    print(responseString)
                }
                
                return data
            }
            .decode(type: AnalysisResponse.self, decoder: JSONDecoder())
            .receive(on: DispatchQueue.main)
            .sink(
                receiveCompletion: { [weak self] completion in
                    switch completion {
                    case .failure(let error):
                        print("\n❌ Batch Upload Error:")
                        print("--------------------------------")
                        print("Error type: \(type(of: error))")
                        print("Error description: \(error.localizedDescription)")
                        if let decodingError = error as? DecodingError {
                            print("Decoding error details: \(decodingError)")
                        }
                        self?.handleError("Batch upload failed: \(error.localizedDescription)")
                    case .finished:
                        print("\n✅ Batch Upload Request Complete")
                    }
                },
                receiveValue: { response in
                    print("\n🎯 Batch Upload Response:")
                    print("--------------------------------")
                    if response.success {
                        print("✅ All screenshots processed successfully")
                    } else {
                        print("⚠️ Server reported failure")
                    }
                    print("📝 Server message: \(response.message)")
                    print("--------------------------------")
                }
            )
            .store(in: &cancellables)
    }
}

// Response type for cloud function
struct AnalysisResponse: Codable {
    let success: Bool
    let message: String
    
    enum CodingKeys: String, CodingKey {
        case success
        case message
    }
    
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        success = try container.decode(Bool.self, forKey: .success)
        message = try container.decodeIfPresent(String.self, forKey: .message) ?? ""
    }
} 
