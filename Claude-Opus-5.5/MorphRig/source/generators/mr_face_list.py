"""MorphRig facial control vocabulary (shared by Blender rig, shape keys, Unreal panel).

Bone-driven controls (drivers on eyelid bones): blink_*, wide_*, squint_* (squint also
drives the eyeSquint_* shape key).  Jaw opening, tongue and gaze are bones (jaw,
tongue_01..03, eye_l/eye_r via c_look).  Everything else is a shape key / morph target
with the same name.
"""

LID_PROPS = ["blink_L", "blink_R", "wide_L", "wide_R", "squint_L", "squint_R"]

SHAPES = [
    # brows
    "browInnerUp_L", "browInnerUp_R", "browOuterUp_L", "browOuterUp_R", "browDown_L", "browDown_R",
    # eyes / cheeks / nose
    "eyeSquint_L", "eyeSquint_R", "cheekRaise_L", "cheekRaise_R", "cheekPuff", "noseSneer_L", "noseSneer_R",
    # mouth
    "mouthSmile_L", "mouthSmile_R", "mouthFrown_L", "mouthFrown_R", "mouthStretch_L", "mouthStretch_R",
    "mouthPucker", "mouthFunnel", "mouthPress", "mouthRollUpper", "mouthRollLower",
    "mouthUpperUp_L", "mouthUpperUp_R", "mouthLowerDown_L", "mouthLowerDown_R", "mouthClose",
    "mouthLeft", "mouthRight",
]

# Viseme shape keys (documented mapping in docs/rig_usage.md / face section)
VISEMES = ["V_MBP", "V_FV", "V_TH", "V_LNT", "V_SS", "V_CH", "V_KG", "V_R", "V_AA", "V_EH", "V_EE", "V_IH",
           "V_OH", "V_OO"]

# jaw opening (degrees) and tongue pose that accompany each viseme at full weight
VISEME_JAW_DEG = {"V_MBP": 0.0, "V_FV": 2.0, "V_TH": 5.0, "V_LNT": 5.5, "V_SS": 1.5, "V_CH": 3.5, "V_KG": 7.0,
                  "V_R": 5.0, "V_AA": 17.0, "V_EH": 11.0, "V_EE": 6.0, "V_IH": 8.0, "V_OH": 12.0, "V_OO": 5.0}
# tongue: (tongue_01 X deg, tongue_02 X deg, tongue_03 X deg, tongue_03 forward mm)
VISEME_TONGUE = {"V_TH": (4.0, 6.0, 8.0, 7.0), "V_LNT": (6.0, 18.0, 28.0, 2.0), "V_KG": (16.0, 4.0, -6.0, -2.0),
                 "V_R": (8.0, 14.0, 18.0, -1.0), "V_SS": (4.0, 8.0, 12.0, 1.0), "V_CH": (6.0, 12.0, 14.0, 0.0)}

FACE_PROPS = LID_PROPS + SHAPES + VISEMES

# Expression presets: property weights + jaw degrees (neutral = all zero)
EXPRESSIONS = {
    "neutral": {},
    "joy": {"mouthSmile_L": 0.85, "mouthSmile_R": 0.85, "cheekRaise_L": 0.6, "cheekRaise_R": 0.6,
            "eyeSquint_L": 0.3, "eyeSquint_R": 0.3, "squint_L": 0.25, "squint_R": 0.25,
            "browOuterUp_L": 0.2, "browOuterUp_R": 0.2, "mouthStretch_L": 0.2, "mouthStretch_R": 0.2, "jaw": 3.0},
    "anger": {"browDown_L": 0.9, "browDown_R": 0.9, "noseSneer_L": 0.55, "noseSneer_R": 0.55,
              "squint_L": 0.45, "squint_R": 0.45, "mouthPress": 0.45, "mouthFrown_L": 0.4, "mouthFrown_R": 0.4,
              "mouthUpperUp_L": 0.25, "mouthUpperUp_R": 0.25, "jaw": 1.0},
    "concern": {"browInnerUp_L": 0.85, "browInnerUp_R": 0.85, "browDown_L": 0.15, "browDown_R": 0.15,
                "mouthFrown_L": 0.45, "mouthFrown_R": 0.45, "mouthStretch_L": 0.15, "mouthStretch_R": 0.15,
                "mouthPress": 0.2, "blink_L": 0.12, "blink_R": 0.12, "jaw": 1.5},
    "surprise": {"browInnerUp_L": 0.9, "browInnerUp_R": 0.9, "browOuterUp_L": 0.9, "browOuterUp_R": 0.9,
                 "wide_L": 0.9, "wide_R": 0.9, "mouthFunnel": 0.3, "jaw": 13.0},
    "pain": {"browDown_L": 0.5, "browDown_R": 0.5, "browInnerUp_L": 0.7, "browInnerUp_R": 0.7,
             "squint_L": 0.8, "squint_R": 0.8, "eyeSquint_L": 0.7, "eyeSquint_R": 0.7, "noseSneer_L": 0.6,
             "noseSneer_R": 0.6, "mouthStretch_L": 0.7, "mouthStretch_R": 0.7, "mouthUpperUp_L": 0.5,
             "mouthUpperUp_R": 0.5, "cheekRaise_L": 0.5, "cheekRaise_R": 0.5, "jaw": 6.0},
    "focus": {"browDown_L": 0.45, "browDown_R": 0.45, "squint_L": 0.35, "squint_R": 0.35,
              "eyeSquint_L": 0.25, "eyeSquint_R": 0.25, "mouthPress": 0.35, "mouthRollLower": 0.1, "jaw": 0.0},
}
