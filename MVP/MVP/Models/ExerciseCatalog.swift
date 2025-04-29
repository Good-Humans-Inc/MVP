import Foundation

struct ExerciseCatalog {
    static let shoulderExercises: [Exercise] = [
        Exercise(
            name: "Shoulder Rolls",
            description: "Gentle circular movements of the shoulders to improve mobility and reduce tension.",
            targetJoints: Array(BodyJointType.shoulderGroup),
            instructions: [
                "Stand or sit with your back straight",
                "Roll your shoulders forward in a circular motion",
                "Repeat 5 times",
                "Roll your shoulders backward in a circular motion",
                "Repeat 5 times"
            ]
        ),
        Exercise(
            name: "Wall Slides",
            description: "Sliding arms up and down against a wall to improve shoulder mobility and posture.",
            targetJoints: Array(BodyJointType.shoulderGroup),
            instructions: [
                "Stand with your back against a wall",
                "Keep elbows bent at 90 degrees, touching the wall",
                "Slide your arms up the wall while maintaining contact",
                "Lower back down slowly",
                "Repeat 10 times"
            ]
        ),
        Exercise(
            name: "Cross-Body Shoulder Stretch",
            description: "Gentle stretch for the posterior shoulder.",
            targetJoints: Array(BodyJointType.shoulderGroup),
            instructions: [
                "Bring one arm across your chest",
                "Use other arm to apply gentle pressure above the elbow",
                "Hold for 30 seconds",
                "Release and repeat on other side",
                "Do 3 sets per side"
            ]
        )
    ]
    
    static let kneeExercises: [Exercise] = [
        Exercise(
            name: "Straight Leg Raises",
            description: "Strengthening exercise for the quadriceps while keeping knee straight.",
            targetJoints: Array(BodyJointType.kneeGroup),
            instructions: [
                "Lie on your back with one leg straight and other bent",
                "Tighten thigh muscles of straight leg",
                "Lift straight leg about 6 inches off ground",
                "Hold for 5 seconds",
                "Lower slowly and repeat 10 times"
            ]
        ),
        Exercise(
            name: "Wall Squats",
            description: "Controlled squat exercise using wall support.",
            targetJoints: Array(BodyJointType.kneeGroup),
            instructions: [
                "Stand with back against wall",
                "Slide down wall until thighs are parallel to ground",
                "Hold position for 5-10 seconds",
                "Slide back up",
                "Repeat 10 times"
            ]
        ),
        Exercise(
            name: "Knee Flexion and Extension",
            description: "Range of motion exercise for the knee joint.",
            targetJoints: Array(BodyJointType.kneeGroup),
            instructions: [
                "Sit in a chair with feet flat on ground",
                "Slowly straighten one knee",
                "Hold for 5 seconds",
                "Slowly bend knee back to starting position",
                "Repeat 10 times per leg"
            ]
        )
    ]
    
    static let lowerBackExercises: [Exercise] = [
        Exercise(
            name: "Bridge Exercise",
            description: "Strengthening exercise for lower back and glutes.",
            targetJoints: Array(BodyJointType.lowerBackGroup),
            instructions: [
                "Lie on back with knees bent",
                "Lift hips toward ceiling",
                "Hold for 5 seconds",
                "Lower slowly",
                "Repeat 10 times"
            ]
        ),
        Exercise(
            name: "Bird Dog",
            description: "Balance and stability exercise for core and back.",
            targetJoints: Array(BodyJointType.lowerBackGroup),
            instructions: [
                "Start on hands and knees",
                "Extend right arm and left leg",
                "Hold for 5 seconds",
                "Return to start and switch sides",
                "Repeat 10 times per side"
            ]
        ),
        Exercise(
            name: "Knee to Chest Stretch",
            description: "Gentle stretch for lower back muscles.",
            targetJoints: Array(BodyJointType.lowerBackGroup),
            instructions: [
                "Lie on back with knees bent",
                "Bring one knee toward chest",
                "Hold for 30 seconds",
                "Lower and switch legs",
                "Repeat 3 times per leg"
            ]
        )
    ]
    
    static let ankleExercises: [Exercise] = [
        Exercise(
            name: "Ankle Circles",
            description: "Range of motion exercise for ankle mobility.",
            targetJoints: Array(BodyJointType.ankleGroup),
            instructions: [
                "Sit with leg extended",
                "Rotate ankle clockwise 10 times",
                "Rotate ankle counterclockwise 10 times",
                "Repeat with other ankle",
                "Do 3 sets per ankle"
            ]
        ),
        Exercise(
            name: "Ankle Alphabet",
            description: "Mobility exercise writing alphabet with toes.",
            targetJoints: Array(BodyJointType.ankleGroup),
            instructions: [
                "Sit with leg extended",
                "Use your toes to write alphabet in air",
                "Move only your ankle, not your leg",
                "Go slowly and deliberately",
                "Repeat with other ankle"
            ]
        ),
        Exercise(
            name: "Heel-Toe Raises",
            description: "Strengthening exercise for ankle stability.",
            targetJoints: Array(BodyJointType.ankleGroup),
            instructions: [
                "Stand holding onto chair for balance",
                "Rise onto toes, then onto heels",
                "Alternate between positions",
                "Move slowly and controlled",
                "Repeat 15 times"
            ]
        )
    ]
    
    // RSI Exercises (using HandJointType)
    static let rsiExercises: [Exercise] = [
        Exercise(
            name: "Wrist Extension",
            description: "Gentle stretching of wrist tendons to reduce tension and increase mobility.",
            imageURLString: "https://storage.googleapis.com/mvp-vids/wrist_extension.jpg",
            targetJoints: [], // No BodyJointType, using hand joints instead
            instructions: [
                "Place your arm on a flat surface with palm down",
                "Slowly extend your wrist upward",
                "Hold for 15-20 seconds",
                "Return to starting position",
                "Repeat 5 times per wrist"
            ],
            handJointTargets: [.wrist, .middleMCP, .middlePIP, .middleDIP]
        ),
        Exercise(
            name: "Finger Stretch",
            description: "Spreading and stretching fingers to reduce tension and improve flexibility.",
            imageURLString: "https://storage.googleapis.com/mvp-vids/finger_stretch.jpg",
            targetJoints: [], // No BodyJointType, using hand joints instead
            instructions: [
                "Extend your hand with palm facing up",
                "Spread your fingers as wide as possible",
                "Hold for 10 seconds",
                "Relax your hand",
                "Repeat 10 times"
            ],
            handJointTargets: [.indexTip, .middleTip, .ringTip, .littleTip]
        ),
        Exercise(
            name: "Thumb Opposition",
            description: "Touching thumb to fingertips to improve dexterity and reduce stiffness.",
            imageURLString: "https://storage.googleapis.com/mvp-vids/thumb_opposition.jpg",
            targetJoints: [], // No BodyJointType, using hand joints instead
            instructions: [
                "Hold your hand in a relaxed position",
                "Touch your thumb to each fingertip in sequence",
                "Start with index finger and end with pinky",
                "Repeat in reverse order",
                "Complete 5 cycles"
            ],
            handJointTargets: [.thumbTip, .indexTip, .middleTip, .ringTip, .littleTip]
        ),
        Exercise(
            name: "Wrist Rotation",
            description: "Circular movements of the wrist to improve mobility and reduce stiffness.",
            imageURLString: "https://storage.googleapis.com/mvp-vids/wrist_rotation.jpg",
            targetJoints: [], // No BodyJointType, using hand joints instead
            instructions: [
                "Extend your arm with elbow slightly bent",
                "Make a gentle fist with your hand",
                "Rotate your wrist in a circular motion",
                "Do 10 clockwise rotations",
                "Do 10 counterclockwise rotations"
            ],
            handJointTargets: [.wrist, .indexMCP, .littleMCP]
        )
    ]
    
    // MARK: - Helper Methods
    static func getExercisesForJoint(_ joint: BodyJointType) -> [Exercise] {
        if BodyJointType.shoulderGroup.contains(joint) {
            return shoulderExercises
        } else if BodyJointType.kneeGroup.contains(joint) {
            return kneeExercises
        } else if BodyJointType.lowerBackGroup.contains(joint) {
            return lowerBackExercises
        } else if BodyJointType.ankleGroup.contains(joint) {
            return ankleExercises
        }
        return []
    }
    
    static func getAllExercises() -> [Exercise] {
        return shoulderExercises + kneeExercises + lowerBackExercises + ankleExercises + rsiExercises
    }
    
    static func getBodyJointExercises() -> [Exercise] {
        return shoulderExercises + kneeExercises + lowerBackExercises + ankleExercises
    }
    
    static func getHandExercises() -> [Exercise] {
        return rsiExercises
    }
} 