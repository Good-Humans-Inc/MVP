import SwiftUI
import UIKit

struct JointConnectionView: View {
    let connections: [(CGPoint, CGPoint)]
    let lineWidth: CGFloat
    let color: Color
    
    init(connections: [(CGPoint, CGPoint)], lineWidth: CGFloat = 3, color: Color = .white) {
        self.connections = connections
        self.lineWidth = lineWidth
        self.color = color
    }
    
    var body: some View {
        Canvas { context, size in
            for connection in connections {
                let path = Path { p in
                    p.move(to: connection.0)
                    p.addLine(to: connection.1)
                }
                
                context.stroke(
                    path,
                    with: .color(color),
                    lineWidth: lineWidth
                )
            }
        }
    }
}

struct JointConnectionView_Previews: PreviewProvider {
    static var previews: some View {
        ZStack {
            Color.black.edgesIgnoringSafeArea(.all)
            
            JointConnectionView(
                connections: [
                    (CGPoint(x: 100, y: 100), CGPoint(x: 200, y: 200)),
                    (CGPoint(x: 200, y: 200), CGPoint(x: 300, y: 150)),
                    (CGPoint(x: 100, y: 100), CGPoint(x: 50, y: 200))
                ],
                lineWidth: 3,
                color: .green
            )
        }
    }
}
