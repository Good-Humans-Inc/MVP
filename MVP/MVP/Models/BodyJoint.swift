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
    case leftHip, rightHip
    
    // Lower body
    case leftKnee, rightKnee
    case leftAnkle, rightAnkle
    
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
        case .leftHip: return .leftHip
        case .rightHip: return .rightHip
        case .leftKnee: return .leftKnee
        case .rightKnee: return .rightKnee
        case .leftAnkle: return .leftAnkle
        case .rightAnkle: return .rightAnkle
        }
    }
    
    // Specify joint connections for drawing lines
    static let connections: [(BodyJointType, BodyJointType)] = [
        // Head
        (.nose, .leftEye), (.nose, .rightEye),
        (.leftEye, .leftEar), (.rightEye, .rightEar),
        
        // Shoulders
        (.leftShoulder, .rightShoulder),
        (.leftShoulder, .leftElbow), (.rightShoulder, .rightElbow),
        (.leftElbow, .leftWrist), (.rightElbow, .rightWrist),
        
        // Torso
        (.leftShoulder, .leftHip), (.rightShoulder, .rightHip),
        (.leftHip, .rightHip),
        
        // Legs
        (.leftHip, .leftKnee), (.rightHip, .rightKnee),
        (.leftKnee, .leftAnkle), (.rightKnee, .rightAnkle)
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
