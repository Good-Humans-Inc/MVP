import Foundation
import Vision
import CoreGraphics

// Define hand joint types based on VNHumanHandPoseObservation points
enum HandJointType: String, CaseIterable {
    // Wrist
    case wrist
    
    // Thumb joints (CMC, MCP, IP, TIP)
    case thumbCMC, thumbMCP, thumbIP, thumbTip
    
    // Index finger joints (MCP, PIP, DIP, TIP)
    case indexMCP, indexPIP, indexDIP, indexTip
    
    // Middle finger joints (MCP, PIP, DIP, TIP)
    case middleMCP, middlePIP, middleDIP, middleTip
    
    // Ring finger joints (MCP, PIP, DIP, TIP)
    case ringMCP, ringPIP, ringDIP, ringTip
    
    // Little finger joints (MCP, PIP, DIP, TIP)
    case littleMCP, littlePIP, littleDIP, littleTip
    
    // Map to VNHumanHandPoseObservation point names
    var visionPointName: VNHumanHandPoseObservation.JointName? {
        switch self {
        case .wrist: return .wrist
            
        case .thumbCMC: return .thumbCMC
        case .thumbMCP: return .thumbMP
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
    
    // Specify joint connections for drawing lines
    static let connections: [(HandJointType, HandJointType)] = [
        // Thumb connections
        (.wrist, .thumbCMC),
        (.thumbCMC, .thumbMCP),
        (.thumbMCP, .thumbIP),
        (.thumbIP, .thumbTip),
        
        // Index finger connections
        (.wrist, .indexMCP),
        (.indexMCP, .indexPIP),
        (.indexPIP, .indexDIP),
        (.indexDIP, .indexTip),
        
        // Middle finger connections
        (.wrist, .middleMCP),
        (.middleMCP, .middlePIP),
        (.middlePIP, .middleDIP),
        (.middleDIP, .middleTip),
        
        // Ring finger connections
        (.wrist, .ringMCP),
        (.ringMCP, .ringPIP),
        (.ringPIP, .ringDIP),
        (.ringDIP, .ringTip),
        
        // Little finger connections
        (.wrist, .littleMCP),
        (.littleMCP, .littlePIP),
        (.littlePIP, .littleDIP),
        (.littleDIP, .littleTip),
        
        // Palm connections
        (.indexMCP, .middleMCP),
        (.middleMCP, .ringMCP),
        (.ringMCP, .littleMCP)
    ]
}

// Hand joint with position
struct HandJoint: Identifiable {
    let id: HandJointType
    let position: CGPoint
    let confidence: Float
    
    var isValid: Bool {
        return confidence > 0.3 && position.x != .infinity && position.y != .infinity
    }
}

// Collection of all hand joints in a pose
struct HandPose {
    var joints: [HandJointType: HandJoint] = [:]
    var isLeftHand: Bool = true
    
    // Get all valid connections for drawing
    func validConnections() -> [(CGPoint, CGPoint)] {
        return HandJointType.connections.compactMap { (start, end) in
            guard let startJoint = joints[start], let endJoint = joints[end],
                  startJoint.isValid && endJoint.isValid else { return nil }
            return (startJoint.position, endJoint.position)
        }
    }
    
    // Get finger positions for exercise validation
    func getFingerExtensionValues() -> [String: CGFloat] {
        var values: [String: CGFloat] = [:]
        
        // Calculate thumb extension (distance from wrist to tip)
        if let wrist = joints[.wrist]?.position, let thumbTip = joints[.thumbTip]?.position {
            values["thumb"] = distance(from: wrist, to: thumbTip)
        }
        
        // Calculate index finger extension
        if let indexMCP = joints[.indexMCP]?.position, let indexTip = joints[.indexTip]?.position {
            values["index"] = distance(from: indexMCP, to: indexTip)
        }
        
        // Calculate middle finger extension
        if let middleMCP = joints[.middleMCP]?.position, let middleTip = joints[.middleTip]?.position {
            values["middle"] = distance(from: middleMCP, to: middleTip)
        }
        
        // Calculate ring finger extension
        if let ringMCP = joints[.ringMCP]?.position, let ringTip = joints[.ringTip]?.position {
            values["ring"] = distance(from: ringMCP, to: ringTip)
        }
        
        // Calculate little finger extension
        if let littleMCP = joints[.littleMCP]?.position, let littleTip = joints[.littleTip]?.position {
            values["little"] = distance(from: littleMCP, to: littleTip)
        }
        
        return values
    }
    
    // Calculate wrist angle
    func getWristAngle() -> CGFloat? {
        guard let wrist = joints[.wrist]?.position,
              let middleMCP = joints[.middleMCP]?.position,
              let middleTip = joints[.middleTip]?.position else {
            return nil
        }
        
        let wristToMCP = CGPoint(x: middleMCP.x - wrist.x, y: middleMCP.y - wrist.y)
        let mcpToTip = CGPoint(x: middleTip.x - middleMCP.x, y: middleTip.y - middleMCP.y)
        
        // Calculate angle in radians
        let angle = atan2(wristToMCP.y, wristToMCP.x) - atan2(mcpToTip.y, mcpToTip.x)
        
        // Convert to degrees
        return abs(angle * 180 / .pi)
    }
    
    // Helper method to calculate distance between points
    private func distance(from point1: CGPoint, to point2: CGPoint) -> CGFloat {
        let dx = point2.x - point1.x
        let dy = point2.y - point1.y
        return sqrt(dx*dx + dy*dy)
    }
}

// For previews and examples
extension HandPose {
    static var preview: HandPose {
        var pose = HandPose()
        
        // Add some sample hand joints for preview
        let centerX: CGFloat = UIScreen.main.bounds.width / 2
        let centerY: CGFloat = UIScreen.main.bounds.height / 2
        
        // Wrist
        pose.joints[.wrist] = HandJoint(id: .wrist, position: CGPoint(x: centerX, y: centerY + 100), confidence: 0.98)
        
        // Thumb
        pose.joints[.thumbCMC] = HandJoint(id: .thumbCMC, position: CGPoint(x: centerX - 30, y: centerY + 80), confidence: 0.95)
        pose.joints[.thumbMCP] = HandJoint(id: .thumbMCP, position: CGPoint(x: centerX - 50, y: centerY + 60), confidence: 0.95)
        pose.joints[.thumbIP] = HandJoint(id: .thumbIP, position: CGPoint(x: centerX - 60, y: centerY + 40), confidence: 0.90)
        pose.joints[.thumbTip] = HandJoint(id: .thumbTip, position: CGPoint(x: centerX - 65, y: centerY + 20), confidence: 0.90)
        
        // Index finger
        pose.joints[.indexMCP] = HandJoint(id: .indexMCP, position: CGPoint(x: centerX - 15, y: centerY + 70), confidence: 0.95)
        pose.joints[.indexPIP] = HandJoint(id: .indexPIP, position: CGPoint(x: centerX - 15, y: centerY + 50), confidence: 0.90)
        pose.joints[.indexDIP] = HandJoint(id: .indexDIP, position: CGPoint(x: centerX - 15, y: centerY + 30), confidence: 0.90)
        pose.joints[.indexTip] = HandJoint(id: .indexTip, position: CGPoint(x: centerX - 15, y: centerY + 10), confidence: 0.90)
        
        // Middle finger
        pose.joints[.middleMCP] = HandJoint(id: .middleMCP, position: CGPoint(x: centerX, y: centerY + 70), confidence: 0.95)
        pose.joints[.middlePIP] = HandJoint(id: .middlePIP, position: CGPoint(x: centerX, y: centerY + 45), confidence: 0.90)
        pose.joints[.middleDIP] = HandJoint(id: .middleDIP, position: CGPoint(x: centerX, y: centerY + 25), confidence: 0.90)
        pose.joints[.middleTip] = HandJoint(id: .middleTip, position: CGPoint(x: centerX, y: centerY + 5), confidence: 0.90)
        
        // Ring finger
        pose.joints[.ringMCP] = HandJoint(id: .ringMCP, position: CGPoint(x: centerX + 15, y: centerY + 70), confidence: 0.95)
        pose.joints[.ringPIP] = HandJoint(id: .ringPIP, position: CGPoint(x: centerX + 15, y: centerY + 45), confidence: 0.90)
        pose.joints[.ringDIP] = HandJoint(id: .ringDIP, position: CGPoint(x: centerX + 15, y: centerY + 25), confidence: 0.90)
        pose.joints[.ringTip] = HandJoint(id: .ringTip, position: CGPoint(x: centerX + 15, y: centerY + 5), confidence: 0.90)
        
        // Little finger
        pose.joints[.littleMCP] = HandJoint(id: .littleMCP, position: CGPoint(x: centerX + 30, y: centerY + 75), confidence: 0.95)
        pose.joints[.littlePIP] = HandJoint(id: .littlePIP, position: CGPoint(x: centerX + 35, y: centerY + 55), confidence: 0.90)
        pose.joints[.littleDIP] = HandJoint(id: .littleDIP, position: CGPoint(x: centerX + 40, y: centerY + 35), confidence: 0.90)
        pose.joints[.littleTip] = HandJoint(id: .littleTip, position: CGPoint(x: centerX + 45, y: centerY + 15), confidence: 0.90)
        
        return pose
    }
}
