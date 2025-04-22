import firebase_admin
from firebase_admin import credentials, firestore
import json

# Initialize Firebase Admin
cred = credentials.Certificate('serviceAccountKey.json')
firebase_admin.initialize_app(cred)
db = firestore.Client(project='pepmvp')

# Exercise definitions
shoulder_exercises = [
    {
        "name": "Shoulder External Rotation",
        "description": "Strengthens rotator cuff muscles to improve shoulder stability and reduce pain.",
        "instructions": [
            "Stand with your elbow at your side, bent at 90 degrees",
            "Keeping your elbow against your body, rotate your forearm outward",
            "Hold for 5 seconds",
            "Return to starting position",
            "Repeat 10 times"
        ],
        "duration": 180
    },
    {
        "name": "Pendulum Exercise",
        "description": "Gentle shoulder mobility exercise that helps reduce pain and stiffness.",
        "instructions": [
            "Lean over and support yourself with your good arm",
            "Let your affected arm hang down",
            "Gently swing your arm in small circles",
            "Gradually increase the size of the circles",
            "Continue for 1 minute"
        ],
        "duration": 120
    },
    {
        "name": "Wall Slides",
        "description": "Improves shoulder mobility and strengthens stabilizing muscles.",
        "instructions": [
            "Stand with your back against a wall",
            "Place your arms against the wall in a 'W' position",
            "Slowly slide your arms up the wall",
            "Hold at the top for 2 seconds",
            "Return to starting position"
        ],
        "duration": 180
    },
    {
        "name": "Shoulder Blade Squeeze",
        "description": "Strengthens upper back muscles and improves posture.",
        "instructions": [
            "Sit or stand with arms at your sides",
            "Squeeze your shoulder blades together",
            "Hold for 5 seconds",
            "Release slowly",
            "Repeat 10 times"
        ],
        "duration": 150
    },
    {
        "name": "Cross-Body Shoulder Stretch",
        "description": "Stretches the posterior shoulder muscles to improve flexibility.",
        "instructions": [
            "Bring one arm across your chest",
            "Use your other arm to gently pull it closer",
            "Hold for 30 seconds",
            "Release and repeat on other side",
            "Do 3 sets per side"
        ],
        "duration": 240
    }
]

knee_exercises = [
    {
        "name": "Straight Leg Raises",
        "description": "Strengthens quadriceps while minimizing knee stress.",
        "instructions": [
            "Lie on your back with one leg straight and other bent",
            "Tighten your thigh muscles",
            "Raise your straight leg about 6 inches",
            "Hold for 5 seconds",
            "Lower slowly and repeat"
        ],
        "duration": 180
    },
    {
        "name": "Hamstring Curls",
        "description": "Strengthens hamstrings to support knee stability.",
        "instructions": [
            "Stand holding onto a chair for balance",
            "Slowly bend your knee, bringing heel toward buttocks",
            "Hold for 5 seconds",
            "Lower slowly",
            "Repeat 10 times each leg"
        ],
        "duration": 200
    },
    {
        "name": "Wall Squats",
        "description": "Builds leg strength while providing back support.",
        "instructions": [
            "Stand with back against wall",
            "Slide down until thighs are parallel to ground",
            "Keep knees aligned with ankles",
            "Hold for 10 seconds",
            "Slowly return to standing"
        ],
        "duration": 180
    },
    {
        "name": "Step-Ups",
        "description": "Strengthens legs while improving balance and coordination.",
        "instructions": [
            "Stand in front of a step",
            "Step up with affected leg",
            "Bring other foot up to step",
            "Step back down",
            "Repeat 10 times"
        ],
        "duration": 200
    },
    {
        "name": "Calf Raises",
        "description": "Strengthens lower leg muscles to support knee function.",
        "instructions": [
            "Stand holding onto counter for balance",
            "Rise up on toes",
            "Hold for 2 seconds",
            "Lower slowly",
            "Repeat 15 times"
        ],
        "duration": 150
    }
]

lower_back_exercises = [
    {
        "name": "Cat-Cow Stretch",
        "description": "Improves spine flexibility and relieves back tension.",
        "instructions": [
            "Start on hands and knees",
            "Arch your back while looking up",
            "Round your back while looking down",
            "Move slowly between positions",
            "Repeat 10 times"
        ],
        "duration": 180
    },
    {
        "name": "Bird Dog",
        "description": "Strengthens core and improves spine stability.",
        "instructions": [
            "Start on hands and knees",
            "Extend opposite arm and leg",
            "Hold for 5 seconds",
            "Return to start",
            "Alternate sides"
        ],
        "duration": 200
    },
    {
        "name": "Pelvic Tilt",
        "description": "Strengthens abdominal muscles and relieves lower back pain.",
        "instructions": [
            "Lie on back with knees bent",
            "Flatten lower back against floor",
            "Hold for 5 seconds",
            "Release",
            "Repeat 10 times"
        ],
        "duration": 150
    },
    {
        "name": "Bridge Exercise",
        "description": "Strengthens lower back and glutes.",
        "instructions": [
            "Lie on back with knees bent",
            "Lift hips toward ceiling",
            "Hold for 10 seconds",
            "Lower slowly",
            "Repeat 10 times"
        ],
        "duration": 180
    },
    {
        "name": "Child's Pose",
        "description": "Gentle stretch for lower back muscles.",
        "instructions": [
            "Kneel on floor with toes together",
            "Sit back on heels",
            "Stretch arms forward",
            "Hold for 30 seconds",
            "Repeat 3 times"
        ],
        "duration": 160
    }
]

ankle_exercises = [
    {
        "name": "Ankle Alphabet",
        "description": "Improves ankle mobility and strength.",
        "instructions": [
            "Sit with leg extended",
            "Draw alphabet letters with toes",
            "Keep leg still",
            "Complete A-Z",
            "Repeat with other foot"
        ],
        "duration": 200
    },
    {
        "name": "Ankle Circles",
        "description": "Increases range of motion and reduces stiffness.",
        "instructions": [
            "Sit with leg extended",
            "Rotate foot clockwise 10 times",
            "Rotate counterclockwise 10 times",
            "Keep movements slow and controlled",
            "Repeat with other foot"
        ],
        "duration": 160
    },
    {
        "name": "Heel Raises",
        "description": "Strengthens calf muscles and improves ankle stability.",
        "instructions": [
            "Stand near wall for support",
            "Rise onto toes",
            "Hold for 5 seconds",
            "Lower slowly",
            "Repeat 15 times"
        ],
        "duration": 180
    },
    {
        "name": "Resistance Band Flex",
        "description": "Strengthens ankle muscles using resistance.",
        "instructions": [
            "Sit with leg straight",
            "Loop band around foot",
            "Point toes away",
            "Slowly flex foot back",
            "Repeat 15 times"
        ],
        "duration": 200
    },
    {
        "name": "Balance Training",
        "description": "Improves ankle stability and proprioception.",
        "instructions": [
            "Stand on one foot",
            "Hold for 30 seconds",
            "Progress to closing eyes",
            "Switch feet",
            "Repeat 3 times each side"
        ],
        "duration": 240
    }
]

def populate_exercises():
    # Clear existing exercises
    collections = ['shoulder_exercises', 'knee_exercises', 'lower_back_exercises', 'ankle_exercises']
    for collection in collections:
        docs = db.collection(collection).get()
        for doc in docs:
            doc.reference.delete()
    
    # Add new exercises
    for exercise in shoulder_exercises:
        db.collection('shoulder_exercises').add(exercise)
    
    for exercise in knee_exercises:
        db.collection('knee_exercises').add(exercise)
    
    for exercise in lower_back_exercises:
        db.collection('lower_back_exercises').add(exercise)
    
    for exercise in ankle_exercises:
        db.collection('ankle_exercises').add(exercise)
    
    print("Successfully populated exercise database!")

if __name__ == "__main__":
    populate_exercises() 