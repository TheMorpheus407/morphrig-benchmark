"""MorphRig 'dialogue' clip: speech performance driven by source/audio/dialogue_alignment.json.

Lip sync: every aligned phoneme maps to a viseme (documented table below); each phoneme
contributes a smooth bump (anticipation 70 ms, release 60 ms) to its viseme channel,
bilabials get a flat full-closure top and pull the jaw closed, the jaw and tongue follow
the weighted viseme tables in mr_face_list with a slower response.  Emotion, gaze, blinks,
head nods and hand gestures are key-posed against the word timings.
"""
import os
import json
import math
import numpy as np
from mr_clip import Clip
from mr_anim import merge, DEG
from mr_params import J
from mr_author import Prober, hand_rot, nrm
import mr_poses as P
from mr_face_list import VISEMES, VISEME_JAW_DEG, VISEME_TONGUE
from clips_common import clip, expr, breathing, blinks, face_mix

HERE = os.path.dirname(os.path.abspath(__file__))
ALIGN = os.path.join(os.path.dirname(HERE), "audio", "dialogue_alignment.json")

# IPA (espeak via Piper) -> viseme
PHONEME_VISEME = {
    "p": "V_MBP", "b": "V_MBP", "m": "V_MBP",
    "f": "V_FV", "v": "V_FV",
    "θ": "V_TH", "ð": "V_TH",
    "t": "V_LNT", "d": "V_LNT", "n": "V_LNT", "l": "V_LNT", "ɾ": "V_LNT",
    "s": "V_SS", "z": "V_SS",
    "ʃ": "V_CH", "ʒ": "V_CH", "tʃ": "V_CH", "dʒ": "V_CH", "j": "V_EE",
    "k": "V_KG", "ɡ": "V_KG", "g": "V_KG", "ŋ": "V_KG", "h": "V_KG", "x": "V_KG",
    "ɹ": "V_R", "r": "V_R", "ɚ": "V_R", "ɜ": "V_R", "ɝ": "V_R",
    "a": "V_AA", "ɑ": "V_AA", "æ": "V_AA", "ʌ": "V_AA", "ɐ": "V_AA",
    "ɛ": "V_EH", "e": "V_EH", "ə": "V_EH",
    "i": "V_EE", "ɪ": "V_IH", "ᵻ": "V_IH", "ɨ": "V_IH", "ʲ": "V_EE",
    "ɒ": "V_OH", "ɔ": "V_OH", "o": "V_OH",
    "u": "V_OO", "ʊ": "V_OO", "w": "V_OO",
}
MODIFIERS = {"ˈ", "ˌ", "ː", ",", ".", "!", "?", ";", ":"}


def load_alignment():
    with open(ALIGN) as fh:
        return json.load(fh)


def phoneme_events(al):
    """Fold stress/length marks into their neighbours; return list of (viseme, start, end, stressed).
    A stress mark's duration belongs to the following segment, a length mark's to the previous one."""
    ev = []
    pending = None          # start time of a stress mark waiting for its segment
    for ph in al["phonemes"]:
        p = ph["p"]
        if p in ("ˈ", "ˌ"):
            pending = ph["start"] if pending is None else pending
            continue
        if p in MODIFIERS:
            if ev:
                v, s, e, st = ev[-1]
                ev[-1] = (v, s, ph["end"], st)
            continue
        vis = PHONEME_VISEME.get(p)
        if vis is None:
            continue
        start = ph["start"] if pending is None else pending
        ev.append((vis, start, ph["end"], pending is not None))
        pending = None
    return ev


def viseme_curves(al, nframes, fps=30):
    """Per-frame viseme weights. Each segment is a smooth bump: attack 70 ms before the segment
    (anticipatory coarticulation), plateau over its middle half, release 60 ms after it."""
    t = np.arange(nframes + 1) / fps
    W = {v: np.zeros(len(t)) for v in VISEMES}
    for vis, s, e, st in phoneme_events(al):
        a0 = s - 0.070
        r1 = e + 0.060
        mid0 = s + 0.25 * (e - s)
        mid1 = e - 0.25 * (e - s)
        if vis == "V_MBP":
            # a bilabial must reach full closure on at least one sampled frame
            tc = round(0.5 * (s + e) * fps) / fps
            mid0, mid1 = min(mid0, tc), max(mid1, tc)
            amp = 1.0
        else:
            amp = 0.95 if st else 0.8
        up = np.clip((t - a0) / max(mid0 - a0, 1e-3), 0, 1)
        dn = np.clip((r1 - t) / max(r1 - mid1, 1e-3), 0, 1)
        bump = np.minimum(up, dn)
        bump = bump * bump * (3 - 2 * bump) * amp
        W[vis] = np.maximum(W[vis], bump)
    # the open/consonant shapes share the mouth: their sum never exceeds 1 ...
    others = [v for v in VISEMES if v != "V_MBP"]
    tot = sum(W[v] for v in others)
    scale = np.where(tot > 1.0, 1.0 / np.maximum(tot, 1e-6), 1.0)
    # ... and a bilabial closure overrides whatever is still releasing
    mbp = W["V_MBP"]
    for v in others:
        W[v] = W[v] * scale * (1.0 - mbp)
    return t, W


def jaw_curve(W, t):
    jaw = np.zeros(len(t))
    for v, w in W.items():
        jaw += w * VISEME_JAW_DEG.get(v, 0.0)
    # the jaw is heavier than the lips: zero-phase one-pole smoothing (~35 ms)
    k = 0.55
    for i in range(1, len(jaw)):
        jaw[i] = jaw[i - 1] + k * (jaw[i] - jaw[i - 1])
    for i in range(len(jaw) - 2, -1, -1):
        jaw[i] = jaw[i + 1] + k * (jaw[i] - jaw[i + 1])
    return jaw * (1.0 - W["V_MBP"])       # closure wins: jaw fully shut at full M/B/P


def tongue_curves(W, t):
    T = np.zeros((len(t), 4))
    for v, w in W.items():
        if v in VISEME_TONGUE:
            T += w[:, None] * np.asarray(VISEME_TONGUE[v])[None, :]
    return T


def lipsync_layer(al, nframes):
    t, W = viseme_curves(al, nframes)
    jaw = jaw_curve(W, t)
    tg = tongue_curves(W, t)

    def layer(frames, S):
        n = len(frames)
        for v in VISEMES:
            S[f"c_face[{v}]"][:, 0] = np.maximum(S[f"c_face[{v}]"][:, 0], W[v][:n])
        S["jaw.rot"][:, 0] += jaw[:n] * DEG
        for k in range(3):
            S[f"tongue_0{k + 1}.rot"][:, 0] += tg[:n, k] * DEG
    return layer, W, jaw


def word_time(al, text, nth=0):
    hits = [w for w in al["words"] if w.get("text", "").lower() == text.lower()]
    return hits[min(nth, len(hits) - 1)]["start"]


def ik(side, pos, fingers, back, pole_dir, dist=0.4):
    """IK arm key: wrist position, hand orientation (fingers / back-of-hand directions), elbow pole."""
    pos = np.asarray(pos, float)
    sh = J["upperarm_" + side]
    Rh = hand_rot(np.asarray(fingers, float), np.asarray(back, float))
    pole = 0.5 * (sh + pos) + nrm(np.asarray(pole_dir, float)) * dist
    return {"ik": tuple(pos), "hand_rot": Rh, "pole": tuple(pole)}


def rest_ik(pr, pose, side):
    """IK key reproducing the FK arm of `pose` (so every arm key of the performance is IK)."""
    W = pr.rig_world(pose, [f"hand_{side}", f"lowerarm_{side}", f"upperarm_{side}"])
    Hm = W[f"hand_{side}"]
    el = W[f"lowerarm_{side}"][:3, 3]
    sh = W[f"upperarm_{side}"][:3, 3]
    mid = 0.5 * (sh + Hm[:3, 3])
    pole = el + nrm(el - mid) * 0.4
    return {"ik": tuple(Hm[:3, 3]), "hand_rot": Hm[:3, :3].copy(), "pole": tuple(pole)}


def console_taps(pr, pose):
    """Left index-finger key on the cyber-forearm display of `pose` (same construction as uplink)."""
    W = pr.world(pose, ["lowerarm_r", "hand_r"])
    e = W["lowerarm_r"][:3, 3]
    w = W["hand_r"][:3, 3]
    disp = e + 0.72 * (w - e) + np.array([0, 0, 0.055])
    fa = nrm(w - e)
    Rl = hand_rot(nrm(np.array([0.0, -0.3, -1.0]) + fa * 0.2), nrm(np.array([0.2, 1.0, 0.3])))
    base = disp - Rl[:, 1] * 0.16

    def key(lift):
        hp = base + np.array([0, 0, lift])
        return {"ik": tuple(hp), "hand_rot": Rl, "pole": tuple(hp + np.array([0.4, 0.2, -0.2]))}
    return key


@clip("dialogue")
def dialogue(R):
    al = load_alignment()
    N = int(math.ceil(al["duration"] * 30))
    c = Clip("dialogue", N, form="one_shot", layer="full_body", entry="idle_relaxed", exit="idle_relaxed",
             notes="spoken performance: '" + " ".join(s["text"] for s in al["sentences"]) + "'")
    pr = Prober(R)
    F = lambda sec: int(round(sec * 30))
    wt = lambda w, n=0: F(word_time(al, w, n))
    base = merge(P.RELAXED, {"look": (0, 0)})
    arm_r0 = dict(P.RELAXED["arm_r"])
    # emotions: confident (asymmetric half smile) -> concern -> anger -> resolve
    conf = expr("focus", 0.2, mouthSmile_L=0.32, mouthSmile_R=0.12, cheekRaise_L=0.15, browOuterUp_L=0.2)
    concern = expr("concern", 0.85)
    concern2 = face_mix(expr("concern", 0.9), {"browDown_L": 0.3, "browDown_R": 0.3, "squint_L": 0.2,
                                                "squint_R": 0.2})
    anger = expr("anger", 0.85)
    anger_hi = expr("anger", 1.0)
    resolve = expr("focus", 0.75, mouthSmile_L=0.1)
    # ---------------------------------------------------------------- hand targets
    east = ik("l", (0.40, -0.34, 1.22), (0.5, -0.85, -0.1), (0.15, 0.05, 1.0), (1, 0.4, -0.6))
    heart_near = ik("r", (-0.04, -0.245, 1.26), (1.0, 0.1, 0.15), (0.0, -1.0, 0.1), (-1, -0.1, -0.7))
    heart = ik("r", (-0.03, -0.172, 1.29), (1.0, 0.1, 0.15), (0.0, -1.0, 0.1), (-1, -0.1, -0.7))
    offer = ik("l", (0.25, -0.27, 1.10), (0.15, -1.0, 0.05), (0.1, 0.0, -1.0), (1, 0.5, -0.8))
    offer_up = ik("l", (0.25, -0.30, 1.14), (0.15, -1.0, 0.15), (0.1, 0.1, -1.0), (1, 0.5, -0.8))
    sweep0 = ik("l", (0.10, -0.36, 1.13), (-0.35, -0.94, 0.0), (0, 0, 1), (1, 0.3, -0.7))
    sweep1 = ik("l", (0.27, -0.36, 1.135), (0.15, -0.99, 0.0), (0, 0, 1), (1, 0.3, -0.7))
    sweep2 = ik("l", (0.43, -0.24, 1.14), (0.62, -0.78, 0.0), (0, 0, 1), (1, 0.3, -0.7))
    console = ik("r", (-0.05, -0.31, 1.15), (0.9, -0.3, 0.05), (0, 0, 1), (-1, 0.3, -0.2))
    fist_up = ik("r", (-0.13, -0.30, 1.25), (0.1, -0.6, 0.8), (-1.0, -0.1, 0.0), (-1, 0.3, -0.6))
    fist_beat = ik("r", (-0.12, -0.35, 1.215), (0.1, -0.7, 0.7), (-1.0, -0.1, 0.0), (-1, 0.3, -0.6))
    point = ik("l", (0.19, -0.47, 1.36), (-0.05, -1.0, 0.05), (0.15, 0.0, 1.0), (1, 0.2, -1.0))
    chest_near = ik("l", (0.10, -0.20, 1.23), (-0.75, -0.05, 0.66), (0.0, -1.0, 0.0), (1, 0.2, -0.8))
    chest = ik("l", (0.091, -0.132, 1.24), (-0.75, -0.05, 0.66), (0.0, -1.0, 0.0), (1, 0.2, -0.8))
    # console pose + the left finger's display taps (probe the rig in that pose)
    look_console = {"look": (8, -34), "head": (16, -6, 0), "neck": (8, -3, 0), "spine": (4, 4, 0)}
    con_pose = merge(base, {"arm_r": console, "hand_r": "loose_fist"}, look_console)
    con_pose["arm_l"] = dict(P.RELAXED["arm_l"])
    tap = console_taps(pr, con_pose)
    # ---------------------------------------------------------------- key poses
    def K(f, *d):
        """Key a pose; any FK arm is converted to an equivalent IK key under that pose's torso, so the
        whole performance interpolates in IK and resting arms follow torso motion."""
        pose = merge(base, *d)
        for sd in "lr":
            if "ik" not in pose["arm_" + sd]:
                pose["arm_" + sd] = rest_ik(pr, pose, sd)
        c.key(f, pose)
    t_east, t_lane, t_mine = wt("East"), wt("lane"), wt("mine")
    K(0, {"face": expr("focus", 0.15)})
    K(t_east - 5, {"face": conf, "head": (0, 4, 0), "look": (4, 0)})
    K(t_lane, {"face": conf, "arm_l": east, "hand_l": "open", "head": (-1, 14, 0), "look": (18, 0),
               "spine": (0.5, 5, 0)})
    K(t_mine - 7, {"face": conf, "arm_r": heart_near, "hand_r": "fist", "head": (-2, 4, 0), "look": (2, 0),
                   "spine": (-1, 1, 0)})
    K(t_mine, {"face": conf, "arm_r": heart, "hand_r": "fist", "head": (4, 0, 0), "look": (0, 0),
               "spine": (-2, 0, 0)})
    K(t_mine + 10, {"face": conf, "arm_r": heart, "hand_r": "fist", "head": (1, 0, 0), "spine": (-2, 0, 0)})
    t_give, t_nin, t_sec = wt("Give"), wt("ninety"), wt("seconds")
    K(t_mine + 22, {"face": conf, "arm_r": heart_near, "hand_r": "loose_fist", "head": (0, 0, 0)})
    K(t_give + 2, {"face": conf, "arm_l": offer, "hand_l": "open", "head": (-1, -3, 3), "spine": (2, -2, 0)})
    K(t_nin + 4, {"face": conf, "arm_l": offer_up, "hand_l": "spread", "head": (2, -3, 3), "spine": (3, -2, 0)})
    K(t_sec + 6, {"face": conf, "arm_l": offer, "hand_l": "open", "head": (0, -2, 1), "spine": (2, -1, 0),
                  "look": (-3, 0)})
    t_this, t_whole, t_net, t_stab = wt("this"), wt("whole"), wt("network"), wt("stabilizes")
    K(t_this - 2, {"face": conf, "arm_l": sweep0, "hand_l": "open", "spine": (2, -5, 0), "head": (0, -4, 0),
                   "look": (-6, -3)})
    K(t_net + 2, {"face": conf, "arm_l": sweep1, "hand_l": "open", "spine": (2, 1, 0), "head": (0, 2, 0),
                  "look": (2, -4)})
    K(t_stab + 30, {"face": conf, "arm_l": sweep2, "hand_l": "open", "spine": (1, 7, 0), "head": (-1, 8, 0),
                    "look": (10, -2)})
    t_hold, t_on = wt("Hold", 0), wt("on")
    K(t_hold - 6, {"face": face_mix(expr("concern", 0.3), {"browDown_L": 0.2}), "head": (4, -2, 0),
                   "look": (-4, -12)})
    K(t_on, merge(con_pose, {"face": concern}))
    t_some, t_rew, t_grid, t_in = wt("Something"), wt("rewriting"), wt("grid"), wt("inside")
    K((t_on + t_some) // 2, merge(con_pose, {"face": concern, "hand_l": "relaxed",
                                             "arm_l": {"fk": (42.0, -18.0, 0.0), "elbow": 75.0,
                                                       "wrist": (0.0, 0.0, 10.0)}}))
    K(t_some - 2, merge(con_pose, {"face": concern, "arm_l": tap(0.05), "hand_l": "point"}))
    K(t_rew + 2, merge(con_pose, {"face": concern, "arm_l": tap(0.0), "hand_l": "point", "look": (10, -36)}))
    K(t_rew + 8, merge(con_pose, {"face": concern, "arm_l": tap(0.03), "hand_l": "point", "look": (6, -34)}))
    K(t_grid + 2, merge(con_pose, {"face": concern2, "arm_l": tap(0.0), "hand_l": "point", "look": (4, -36)}))
    K(t_grid + 9, merge(con_pose, {"face": concern2, "arm_l": tap(0.035), "hand_l": "point"}))
    K(t_in + 6, merge(con_pose, {"face": concern2, "arm_l": tap(0.06), "hand_l": "loose_fist",
                                 "head": (20, -8, -4), "look": (8, -38)}))
    t_no = wt("No")
    K(t_no - 6, merge(con_pose, {"face": face_mix(concern2, expr("anger", 0.3)), "arm_l": tap(0.07),
                                 "hand_l": "loose_fist", "head": (22, -8, -3)}))
    K(t_no - 1, merge(con_pose, {"face": face_mix(concern2, expr("anger", 0.6)), "hand_l": "loose_fist",
                                 "arm_l": {"fk": (24.0, -20.0, 4.0), "elbow": 50.0, "wrist": (6.0, 0.0, 12.0)},
                                 "head": (8, -3, 0), "look": (0, -6)}))
    K(t_no + 2, {"face": anger_hi, "head": (-5, 0, 0), "neck": (-2, 0, 0), "look": (0, 1), "hand_l": "fist",
                 "hand_r": "fist", "spine": (0, 0, 0)})
    K(t_no + 14, {"face": anger, "head": (-3, 0, 0), "look": (0, 0), "hand_l": "fist", "hand_r": "fist"})
    t_not, t_watch = wt("Not"), wt("watch")
    K(t_not, {"face": anger, "arm_r": fist_up, "hand_r": "fist", "hand_l": "fist", "head": (0, 3, 0),
              "spine": (3, 3, 0), "cog": (0, -0.008, -0.012)})
    K(t_watch + 3, {"face": anger_hi, "arm_r": fist_beat, "hand_r": "fist", "hand_l": "fist", "head": (5, 2, 0),
                    "spine": (5, 3, 0), "cog": (0, -0.012, -0.014)})
    K(t_watch + 14, {"face": anger, "arm_r": fist_up, "hand_r": "fist", "hand_l": "loose_fist",
                     "head": (1, 2, 0), "spine": (3, 2, 0)})
    t_hold2, t_line = wt("Hold", 1), wt("line")
    K(t_hold2 - 2, {"face": resolve, "arm_r": arm_r0, "hand_r": "loose_fist", "head": (0, 0, 0), "look": (0, 0)})
    K(t_line, {"face": resolve, "arm_l": point, "hand_l": "point", "head": (-3, -2, 0), "spine": (1, -4, 0)})
    K(t_line + 14, {"face": resolve, "arm_l": point, "hand_l": "point", "head": (-2, -2, 0), "spine": (1, -4, 0)})
    t_im, t_patch, t_node, t_myself = wt("I'm"), wt("patching"), wt("node"), wt("myself")
    K(t_patch + 4, {"face": resolve, "arm_l": chest_near, "hand_l": "open", "head": (2, 0, 0), "look": (0, -3)})
    K(t_myself + 2, {"face": resolve, "arm_l": chest, "hand_l": "open", "head": (8, 0, 0), "look": (0, -6)})
    K(t_myself + 12, {"face": resolve, "arm_l": chest, "hand_l": "open", "head": (0, 0, 0), "look": (0, 0)})
    K(N, {"face": expr("focus", 0.4)})
    ls, W, jaw = lipsync_layer(al, N)
    blink_times = [F(x) for x in (2.02, 6.62, 11.38, 13.9, 15.22, 17.25)]
    c.layers += [ls, blinks(blink_times), breathing(0.8, period=N // 4)]
    c.dense = True
    for s in al["sentences"]:
        c.markers.append((F(s["start"]), "line_start"))
    c.markers += [(0, "audio_start"), (t_mine, "gesture_heart"), (t_on, "console_raise"), (t_no, "emotion_shift"),
                  (t_line, "gesture_point")]
    c.extra["audio"] = "source/audio/dialogue.wav"
    c.extra["alignment"] = "source/audio/dialogue_alignment.json"
    c.extra["no_floor_fix"] = True
    c.extra["mbp_frames"] = [int(i) for i in np.nonzero(W["V_MBP"] > 0.95)[0]]
    c.extra["contacts"] = {"fist_on_chest": [t_mine, t_mine + 10], "finger_on_console": [t_rew + 2, t_grid + 2],
                           "hand_on_chest": [t_myself + 2, t_myself + 12]}
    return c
