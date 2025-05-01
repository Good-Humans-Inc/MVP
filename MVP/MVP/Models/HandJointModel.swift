import Foundation
import Vision
import CoreGraphics

// Define hand joint types based on VNHumanHandPoseObservation
enum HandJointType: String, CaseIterable {
    // Wrist
    case wrist
    
    // Thumb joints
    case thumbCMC
    case thumbMP
    case thumbIP
    case thumbTip
    
    // Index finger joints
    case indexMCP
    case indexPIP
    case indexDIP
    case indexTip
    
    // Middle finger joints
    case middleMCP
    case middlePIP
    case middleDIP
    case middleTip
    
    // Ring finger joints
    case ringMCP
    case ringPIP
    case ringDIP
    case ringTip
    
    // Little finger joints
    case littleMCP
    case littlePIP
    case littleDIP
    case littleTip
    
    // Map to VNHumanHandPoseObservation points
    var visionPointName: VNHumanHandPoseObservation.JointName? {
        switch self {
        case .wrist: return .wrist
            
        case .thumbCMC: return .thumbCMC
        case .thumbMP: return .thumbMP
        case .thumbIP: return .thumbIP
        case .thumbTip: return .thumbTip
            
        case .indexMCP: return .indexMCP
        case .indexPIP: return .indexPIP
        case .indexDIP: return .indexDIP
        case .indexTip: return .indexTip
            
        case .middleMCP: return .middleMCP
        case .middlePIP: return .middlePIP
        case .middleDIP: return .middleDIP
        case .middleTip: return .middleTip
            
        case .ringMCP: return .ringMCP
        case .ringPIP: return .ringPIP
        case .ringDIP: return .ringDIP
        case .ringTip: return .ringTip
            
        case .littleMCP: return .littleMCP
        case .littlePIP: return .littlePIP
        case .littleDIP: return .littleDIP
        case .littleTip: return .littleTip
        }
    }
    
    // Hand joint connections for drawing lines
    static let connections: [(HandJointType, HandJointType)] = [
        // Thumb
        (.wrist, .thumbCMC),
        (.thumbCMC, .thumbMP),
        (.thumbMP, .thumbIP),
        (.thumbIP, .thumbTip),
        
        // Index finger
        (.wrist, .indexMCP),
        (.indexMCP, .indexPIP),
        (.indexPIP, .indexDIP),
        (.indexDIP, .indexTip),
        
        // Middle finger
        (.wrist, .middleMCP),
        (.middleMCP, .middlePIP),
        (.middlePIP, .middleDIP),
        (.middleDIP, .middleTip),
        
        // Ring finger
        (.wrist, .ringMCP),
        (.ringMCP, .ringPIP),
        (.ringPIP, .ringDIP),
        (.ringDIP, .ringTip),
        
        // Little finger
        (.wrist, .littleMCP),
        (.littleMCP, .littlePIP),
        (.littlePIP, .littleDIP),
        (.littleDIP, .littleTip),
        
        // Create palm structure by connecting knuckles
        (.indexMCP, .middleMCP),
        (.middleMCP, .ringMCP),
        (.ringMCP, .littleMCP),
        
        // Connect thumb to palm
        (.thumbCMC, .indexMCP),
        
        // Create palm web between thumb and index
        (.thumbMP, .indexMCP),
        
        // Additional palm connections for better visualization
        (.wrist, .thumbCMC),
        (.wrist, .indexMCP),
        (.wrist, .middleMCP),
        (.wrist, .ringMCP),
        (.wrist, .littleMCP),
        
        // Create palm triangulation for better shape
        (.wrist, .thumbMP),
        (.thumbCMC, .middleMCP),
        (.thumbCMC, .wrist)
    ]
}

// Hand joint with position
struct HandJoint: Identifiable {
    let id: HandJointType
    let position: CGPoint
    let confidence: Float
    
    var isValid: Bool {
        return confidence > 0.1 && position.x != .infinity && position.y != .infinity
    }
}

// Collection of hand joints forming a hand pose
struct HandPose {
    var joints: [HandJointType: HandJoint] = [:]
    
    // Get all valid connections for drawing
    func validConnections() -> [(CGPoint, CGPoint)] {
        return HandJointType.connections.compactMap { (start, end) in
            guard let startJoint = joints[start], let endJoint = joints[end],
                  startJoint.isValid && endJoint.isValid else { return nil }
            return (startJoint.position, endJoint.position)
        }
    }
    
    // Get finger extension values (0.0-1.0)
    func getFingerExtensionValues() -> [String: CGFloat] {
        var values: [String: CGFloat] = [:]
        
        // Calculate thumb extension
        if let tip = joints[.thumbTip], let base = joints[.thumbCMC], tip.isValid && base.isValid {
            let distance = tip.position.distance(to: base.position)
            values["thumb"] = min(max(distance / 100, 0), 1)
        }
        
        // Calculate index finger extension
        if let tip = joints[.indexTip], let base = joints[.indexMCP], tip.isValid && base.isValid {
            let distance = tip.position.distance(to: base.position)
            values["index"] = min(max(distance / 150, 0), 1)
        }
        
        // Middle finger extension
        if let tip = joints[.middleTip], let base = joints[.middleMCP], tip.isValid && base.isValid {
            let distance = tip.position.distance(to: base.position)
            values["middle"] = min(max(distance / 150, 0), 1)
        }
        
        // Ring finger extension
        if let tip = joints[.ringTip], let base = joints[.ringMCP], tip.isValid && base.isValid {
            let distance = tip.position.distance(to: base.position)
            values["ring"] = min(max(distance / 150, 0), 1)
        }
        
        // Little finger extension
        if let tip = joints[.littleTip], let base = joints[.littleMCP], tip.isValid && base.isValid {
            let distance = tip.position.distance(to: base.position)
            values["little"] = min(max(distance / 130, 0), 1)
        }
        
        return values
    }
    
    // Calculate wrist angle
    func getWristAngle() -> CGFloat? {
        guard let wrist = joints[.wrist], let index = joints[.indexMCP], let little = joints[.littleMCP],
              wrist.isValid && index.isValid && little.isValid else {
            return nil
        }
        
        let centerX = (index.position.x + little.position.x) / 2
        let centerY = (index.position.y + little.position.y) / 2
        let center = CGPoint(x: centerX, y: centerY)
        
        // Calculate angle between wrist and center of hand
        let dx = center.x - wrist.position.x
        let dy = center.y - wrist.position.y
        let angle = atan2(dy, dx) * 180 / .pi
        
        return angle
    }
    
    // Create a preview hand pose for SwiftUI previews
    static var preview: HandPose {
        var pose = HandPose()
        let center = CGPoint(x: 200, y: 200)
        
        // Add wrist
        pose.joints[.wrist] = HandJoint(id: .wrist, position: CGPoint(x: center.x, y: center.y + 100), confidence: 1.0)
        
        // Add thumb joints
        pose.joints[.thumbCMC] = HandJoint(id: .thumbCMC, position: CGPoint(x: center.x - 30, y: center.y + 70), confidence: 1.0)
        pose.joints[.thumbMP] = HandJoint(id: .thumbMP, position: CGPoint(x: center.x - 50, y: center.y + 50), confidence: 1.0)
        pose.joints[.thumbIP] = HandJoint(id: .thumbIP, position: CGPoint(x: center.x - 70, y: center.y + 30), confidence: 1.0)
        pose.joints[.thumbTip] = HandJoint(id: .thumbTip, position: CGPoint(x: center.x - 80, y: center.y + 15), confidence: 1.0)
        
        // Add index finger joints
        pose.joints[.indexMCP] = HandJoint(id: .indexMCP, position: CGPoint(x: center.x - 15, y: center.y + 40), confidence: 1.0)
        pose.joints[.indexPIP] = HandJoint(id: .indexPIP, position: CGPoint(x: center.x - 20, y: center.y + 0), confidence: 1.0)
        pose.joints[.indexDIP] = HandJoint(id: .indexDIP, position: CGPoint(x: center.x - 25, y: center.y - 30), confidence: 1.0)
        pose.joints[.indexTip] = HandJoint(id: .indexTip, position: CGPoint(x: center.x - 30, y: center.y - 60), confidence: 1.0)
        
        // Add middle finger joints
        pose.joints[.middleMCP] = HandJoint(id: .middleMCP, position: CGPoint(x: center.x + 0, y: center.y + 35), confidence: 1.0)
        pose.joints[.middlePIP] = HandJoint(id: .middlePIP, position: CGPoint(x: center.x + 0, y: center.y - 5), confidence: 1.0)
        pose.joints[.middleDIP] = HandJoint(id: .middleDIP, position: CGPoint(x: center.x + 0, y: center.y - 35), confidence: 1.0)
        pose.joints[.middleTip] = HandJoint(id: .middleTip, position: CGPoint(x: center.x + 0, y: center.y - 65), confidence: 1.0)
        
        // Add ring finger joints
        pose.joints[.ringMCP] = HandJoint(id: .ringMCP, position: CGPoint(x: center.x + 15, y: center.y + 40), confidence: 1.0)
        pose.joints[.ringPIP] = HandJoint(id: .ringPIP, position: CGPoint(x: center.x + 20, y: center.y + 0), confidence: 1.0)
        pose.joints[.ringDIP] = HandJoint(id: .ringDIP, position: CGPoint(x: center.x + 25, y: center.y - 30), confidence: 1.0)
        pose.joints[.ringTip] = HandJoint(id: .ringTip, position: CGPoint(x: center.x + 30, y: center.y - 60), confidence: 1.0)
        
        // Add little finger joints
        pose.joints[.littleMCP] = HandJoint(id: .littleMCP, position: CGPoint(x: center.x + 30, y: center.y + 50), confidence: 1.0)
        pose.joints[.littlePIP] = HandJoint(id: .littlePIP, position: CGPoint(x: center.x + 40, y: center.y + 20), confidence: 1.0)
        pose.joints[.littleDIP] = HandJoint(id: .littleDIP, position: CGPoint(x: center.x + 50, y: center.y - 10), confidence: 1.0)
        pose.joints[.littleTip] = HandJoint(id: .littleTip, position: CGPoint(x: center.x + 60, y: center.y - 40), confidence: 1.0)
        
        return pose
    }
}

// Helper extension for CGPoint
extension CGPoint {
    func distance(to point: CGPoint) -> CGFloat {
        let dx = point.x - self.x
        let dy = point.y - self.y
        return sqrt(dx*dx + dy*dy)
    }
} 