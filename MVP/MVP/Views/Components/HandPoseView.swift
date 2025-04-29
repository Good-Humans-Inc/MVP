import SwiftUI
import UIKit

struct HandPoseView: View {
    let handPose: HandPose
    
    var body: some View {
        GeometryReader { geometry in
            ZStack {
                // Draw connections between joints
                JointConnectionView(
                    connections: handPose.validConnections(),
                    lineWidth: 3,
                    color: .green
                )
                
                // Draw the joints
                ForEach(Array(handPose.joints.values), id: \.id) { joint in
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
struct HandPoseView_Previews: PreviewProvider {
    static var previews: some View {
        ZStack {
            Color.black.edgesIgnoringSafeArea(.all)
            HandPoseView(handPose: HandPose.preview)
        }
    }
} 