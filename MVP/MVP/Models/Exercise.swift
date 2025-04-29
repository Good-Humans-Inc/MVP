import Foundation

struct Exercise: Identifiable, Equatable {
    let id: UUID
    let name: String
    let description: String
    let imageURL: URL?
    let imageURL1: URL?
    let duration: TimeInterval
    let targetJoints: [BodyJointType]
    let handJointTargets: [HandJointType]
    let instructions: [String]
    let firestoreId: String?
    let videoURL: URL?
    
    init(id: UUID = UUID(), 
         name: String, 
         description: String,
         imageURLString: String? = nil, 
         imageURLString1: String? = nil, 
         duration: TimeInterval = 180,
         targetJoints: [BodyJointType] = [], 
         instructions: [String] = [],
         firestoreId: String? = nil,
         videoURL: URL? = nil,
         handJointTargets: [HandJointType] = []) {
        
        // Validate required fields
        guard !name.isEmpty else {
            fatalError("Exercise name cannot be empty")
        }
        guard !description.isEmpty else {
            fatalError("Exercise description cannot be empty")
        }
        
        self.id = id
        self.name = name
        self.description = description
        self.imageURL = imageURLString.flatMap { URL(string: $0) }
        self.imageURL1 = imageURLString1.flatMap { URL(string: $0) }
        self.duration = max(duration, 30) // Ensure minimum duration of 30 seconds
        self.targetJoints = targetJoints
        self.handJointTargets = handJointTargets
        self.instructions = instructions
        self.firestoreId = firestoreId
        self.videoURL = videoURL
    }
    
    // Computed property to check if exercise has media
    var hasMedia: Bool {
        return imageURL != nil || imageURL1 != nil || videoURL != nil
    }
    
    // Computed property to get primary media URL
    var primaryMediaURL: URL? {
        return videoURL ?? imageURL ?? imageURL1
    }
    
    // Computed property to check if this is a hand exercise (RSI)
    var isHandExercise: Bool {
        return !handJointTargets.isEmpty
    }
    
    // Validation method
    func validate() -> Bool {
        return !name.isEmpty && 
               !description.isEmpty && 
               duration >= 30 && 
               !instructions.isEmpty
    }
}
