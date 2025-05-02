import SwiftUI
import UIKit

struct BodyPoseView: View {
    let bodyPose: BodyPose
    var lineColor: Color = .green
    var jointColor: Color = .blue
    var lineWidth: CGFloat = 3
    var jointRadius: CGFloat = 8
    var painPointColor: Color = .red
    var painPoints: Set<BodyJointType> = []
    
    var body: some View {
        GeometryReader { geometry in
            ZStack {
                // Draw connections between joints
                ForEach(bodyPose.validConnections(), id: \.0) { connection in
                    let startPos = transformPoint(connection.0, in: geometry.size)
                    let endPos = transformPoint(connection.1, in: geometry.size)
                    
                    Line(from: startPos, to: endPos)
                        .stroke(lineColor, lineWidth: lineWidth)
                }
                
                // Draw joint points
                ForEach(Array(bodyPose.joints.values.filter { $0.isValid }), id: \.id) { joint in
                    let position = transformPoint(joint.position, in: geometry.size)
                    
                    Circle()
                        .fill(painPoints.contains(joint.id) ? painPointColor : jointColor)
                        .frame(width: jointRadius * 2, height: jointRadius * 2)
                        .position(position)
                    
                    // Add joint labels for key joints for better visualization
                    if shouldLabelJoint(joint.id) {
                        Text(jointLabel(for: joint.id))
                            .font(.system(size: 10))
                            .foregroundColor(.white)
                            .padding(4)
                            .background(Color.black.opacity(0.7))
                            .cornerRadius(4)
                            .position(position.offsetBy(dx: 0, dy: -20))
                    }
                }
            }
        }
    }
    
    // Transform normalized Vision coordinates to SwiftUI view coordinates
    private func transformPoint(_ point: CGPoint, in size: CGSize) -> CGPoint {
        return CGPoint(
            x: point.x * size.width,
            y: point.y * size.height
        )
    }
    
    // Helper to determine if we should show a label for this joint
    private func shouldLabelJoint(_ jointType: BodyJointType) -> Bool {
        return [
            BodyJointType.leftShoulder, BodyJointType.rightShoulder,
            BodyJointType.leftHip, BodyJointType.rightHip,
            BodyJointType.leftKnee, BodyJointType.rightKnee,
            BodyJointType.leftAnkle, BodyJointType.rightAnkle
        ].contains(jointType)
    }
    
    // Helper to get a display label for important joints
    private func jointLabel(for jointType: BodyJointType) -> String {
        switch jointType {
        case .leftShoulder: return "LS"
        case .rightShoulder: return "RS"
        case .leftElbow: return "LE"
        case .rightElbow: return "RE"
        case .leftHip: return "LH"
        case .rightHip: return "RH"
        case .leftKnee: return "LK"
        case .rightKnee: return "RK"
        case .leftAnkle: return "LA"
        case .rightAnkle: return "RA"
        default: return ""
        }
    }
}

// Extend CGPoint to add offset utility
extension CGPoint {
    func offsetBy(dx: CGFloat, dy: CGFloat) -> CGPoint {
        return CGPoint(x: self.x + dx, y: self.y + dy)
    }
} 