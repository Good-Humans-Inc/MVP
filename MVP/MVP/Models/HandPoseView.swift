import SwiftUI
import UIKit

struct HandPoseView: View {
    let handPose: HandPose
    
    var body: some View {
        GeometryReader { geometry in
            ZStack {
                // Draw palm area first for better visual
                drawPalmArea(geometry)
                
                // Draw connections between joints
                ForEach(handPose.validConnections(), id: \.0) { connection in
                    let startPos = transformPoint(connection.0, in: geometry.size)
                    let endPos = transformPoint(connection.1, in: geometry.size)
                    
                    Line(from: startPos, to: endPos)
                        .stroke(Color.green, lineWidth: 4)
                }
                
                // Draw the joints
                ForEach(Array(handPose.joints.values), id: \.id) { joint in
                    if joint.isValid {
                        Circle()
                            .fill(Color.blue)
                            .frame(width: 12, height: 12)
                            .position(transformPoint(joint.position, in: geometry.size))
                    }
                }
            }
        }
    }
    
    // Draw a subtle palm area to better visualize hand shape
    private func drawPalmArea(_ geometry: GeometryProxy) -> some View {
        let palmJoints: [HandJointType] = [.wrist, .thumbCMC, .indexMCP, .middleMCP, .ringMCP, .littleMCP]
        
        // Only proceed if we have all the palm joints
        if palmJoints.allSatisfy({ handPose.joints[$0]?.isValid == true }) {
            let points = palmJoints.compactMap { jointType -> CGPoint? in
                guard let joint = handPose.joints[jointType], joint.isValid else { return nil }
                return transformPoint(joint.position, in: geometry.size)
            }
            
            return AnyView(
                Path { path in
                    if let first = points.first {
                        path.move(to: first)
                        for point in points.dropFirst() {
                            path.addLine(to: point)
                        }
                        path.closeSubpath()
                    }
                }
                .fill(Color.green.opacity(0.2))
            )
        } else {
            return AnyView(EmptyView())
        }
    }
    
    // Transform normalized Vision coordinates to SwiftUI view coordinates
    private func transformPoint(_ point: CGPoint, in size: CGSize) -> CGPoint {
        return CGPoint(
            x: point.x * size.width,
            y: point.y * size.height
        )
    }
}

// Helper shape for drawing lines
struct Line: Shape {
    var from: CGPoint
    var to: CGPoint
    
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: from)
        path.addLine(to: to)
        return path
    }
}
