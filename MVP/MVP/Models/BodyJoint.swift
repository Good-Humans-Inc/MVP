import Foundation
import Vision
import CoreGraphics

// Define body joint types based on VNHumanBodyPoseObservation.JointName
enum BodyJointType: String, CaseIterable {
    // Upper body
    case nose, leftEye, rightEye, leftEar, rightEar
    case neck
    case leftShoulder, rightShoulder
    case leftElbow, rightElbow
    case leftWrist, rightWrist
    
    // Mid body
    case root
    case spine
    case leftHip, rightHip
    
    // Lower body
    case leftKnee, rightKnee
    case leftAnkle, rightAnkle
    case leftFoot, rightFoot
    
    // Joint groups for exercise targeting
    static let shoulderGroup: Set<BodyJointType> = [.leftShoulder, .rightShoulder, .leftElbow, .rightElbow]
    static let kneeGroup: Set<BodyJointType> = [.leftKnee, .rightKnee, .leftHip, .rightHip]
    static let ankleGroup: Set<BodyJointType> = [.leftAnkle, .rightAnkle, .leftFoot, .rightFoot]
    static let lowerBackGroup: Set<BodyJointType> = [.root, .spine, .leftHip, .rightHip]
    
    // Map to VNHumanBodyPoseObservation.JointName
    var visionJointName: VNHumanBodyPoseObservation.JointName? {
        switch self {
        case .nose: return .nose
        case .leftEye: return .leftEye
        case .rightEye: return .rightEye
        case .leftEar: return .leftEar
        case .rightEar: return .rightEar
        case .neck: return .neck
        case .leftShoulder: return .leftShoulder
        case .rightShoulder: return .rightShoulder
        case .leftElbow: return .leftElbow
        case .rightElbow: return .rightElbow
        case .leftWrist: return .leftWrist
        case .rightWrist: return .rightWrist
        case .root: return .root
        case .spine: return .root // Map spine to root as approximation
        case .leftHip: return .leftHip
        case .rightHip: return .rightHip
        case .leftKnee: return .leftKnee
        case .rightKnee: return .rightKnee
        case .leftAnkle: return .leftAnkle
        case .rightAnkle: return .rightAnkle
        case .leftFoot: return .leftAnkle // Map foot to ankle as approximation
        case .rightFoot: return .rightAnkle // Map foot to ankle as approximation
        }
    }
    
    // Update connections to include new joints
    static let connections: [(BodyJointType, BodyJointType)] = [
        // Head
        (.nose, .leftEye), (.nose, .rightEye),
        (.leftEye, .leftEar), (.rightEye, .rightEar),
        
        // Shoulders
        (.leftShoulder, .rightShoulder),
        (.leftShoulder, .leftElbow), (.rightShoulder, .rightElbow),
        (.leftElbow, .leftWrist), (.rightElbow, .rightWrist),
        
        // Spine
        (.neck, .spine),
        (.spine, .root),
        
        // Torso
        (.leftShoulder, .leftHip), (.rightShoulder, .rightHip),
        (.leftHip, .rightHip),
        
        // Legs
        (.leftHip, .leftKnee), (.rightHip, .rightKnee),
        (.leftKnee, .leftAnkle), (.rightKnee, .rightAnkle),
        (.leftAnkle, .leftFoot), (.rightAnkle, .rightFoot)
    ]
}

// Body joint with position
struct BodyJoint: Identifiable {
    let id: BodyJointType
    let position: CGPoint
    let confidence: Float
    
    var isValid: Bool {
        return confidence > 0.5 && position.x != .infinity && position.y != .infinity
    }
}

// Collection of all body joints in a pose
struct BodyPose {
    var joints: [BodyJointType: BodyJoint] = [:]
    
    // Get all valid connections for drawing
    func validConnections() -> [(CGPoint, CGPoint)] {
        return BodyJointType.connections.compactMap { (start, end) in
            guard let startJoint = joints[start], let endJoint = joints[end],
                  startJoint.isValid && endJoint.isValid else { return nil }
            return (startJoint.position, endJoint.position)
        }
    }
}
