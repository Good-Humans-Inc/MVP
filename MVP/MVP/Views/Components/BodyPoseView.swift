import SwiftUI
import UIKit

struct BodyPoseView: View {
    let bodyPose: BodyPose
    
    var body: some View {
        GeometryReader { geometry in
            ZStack {
                // Draw connections between joints
                JointConnectionView(
                    connections: bodyPose.validConnections(),
                    lineWidth: 3,
                    color: .green
                )
                
                // Draw the joints
                ForEach(Array(bodyPose.joints.values), id: \.id) { joint in
                    if joint.isValid {
                        Circle()
                            .fill(Color.blue)
                            .frame(width: 12, height: 12)
                            .position(joint.position)
                    }
                }
            }
        }
    }
}

// Preview
struct BodyPoseView_Previews: PreviewProvider {
    static var previews: some View {
        ZStack {
            Color.black.edgesIgnoringSafeArea(.all)
            // Create a sample body pose for preview
            BodyPoseView(bodyPose: createSampleBodyPose())
        }
    }
    
    static func createSampleBodyPose() -> BodyPose {
        var bodyPose = BodyPose()
        
        // Add some sample body joints for preview
        let centerX: CGFloat = UIScreen.main.bounds.width / 2
        let centerY: CGFloat = UIScreen.main.bounds.height / 2
        
        // Head
        bodyPose.joints[.nose] = BodyJoint(id: .nose, position: CGPoint(x: centerX, y: centerY - 90), confidence: 0.95)
        bodyPose.joints[.leftEye] = BodyJoint(id: .leftEye, position: CGPoint(x: centerX - 10, y: centerY - 95), confidence: 0.9)
        bodyPose.joints[.rightEye] = BodyJoint(id: .rightEye, position: CGPoint(x: centerX + 10, y: centerY - 95), confidence: 0.9)
        
        // Upper body
        bodyPose.joints[.neck] = BodyJoint(id: .neck, position: CGPoint(x: centerX, y: centerY - 70), confidence: 0.95)
        bodyPose.joints[.leftShoulder] = BodyJoint(id: .leftShoulder, position: CGPoint(x: centerX - 30, y: centerY - 50), confidence: 0.9)
        bodyPose.joints[.rightShoulder] = BodyJoint(id: .rightShoulder, position: CGPoint(x: centerX + 30, y: centerY - 50), confidence: 0.9)
        bodyPose.joints[.leftElbow] = BodyJoint(id: .leftElbow, position: CGPoint(x: centerX - 50, y: centerY - 20), confidence: 0.85)
        bodyPose.joints[.rightElbow] = BodyJoint(id: .rightElbow, position: CGPoint(x: centerX + 50, y: centerY - 20), confidence: 0.85)
        bodyPose.joints[.leftWrist] = BodyJoint(id: .leftWrist, position: CGPoint(x: centerX - 60, y: centerY + 10), confidence: 0.8)
        bodyPose.joints[.rightWrist] = BodyJoint(id: .rightWrist, position: CGPoint(x: centerX + 60, y: centerY + 10), confidence: 0.8)
        
        // Torso
        bodyPose.joints[.spine] = BodyJoint(id: .spine, position: CGPoint(x: centerX, y: centerY), confidence: 0.9)
        bodyPose.joints[.root] = BodyJoint(id: .root, position: CGPoint(x: centerX, y: centerY + 30), confidence: 0.9)
        
        // Lower body
        bodyPose.joints[.leftHip] = BodyJoint(id: .leftHip, position: CGPoint(x: centerX - 20, y: centerY + 30), confidence: 0.85)
        bodyPose.joints[.rightHip] = BodyJoint(id: .rightHip, position: CGPoint(x: centerX + 20, y: centerY + 30), confidence: 0.85)
        bodyPose.joints[.leftKnee] = BodyJoint(id: .leftKnee, position: CGPoint(x: centerX - 20, y: centerY + 80), confidence: 0.8)
        bodyPose.joints[.rightKnee] = BodyJoint(id: .rightKnee, position: CGPoint(x: centerX + 20, y: centerY + 80), confidence: 0.8)
        bodyPose.joints[.leftAnkle] = BodyJoint(id: .leftAnkle, position: CGPoint(x: centerX - 20, y: centerY + 130), confidence: 0.75)
        bodyPose.joints[.rightAnkle] = BodyJoint(id: .rightAnkle, position: CGPoint(x: centerX + 20, y: centerY + 130), confidence: 0.75)
        
        return bodyPose
    }
} 