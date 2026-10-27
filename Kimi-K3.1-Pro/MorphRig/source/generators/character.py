"""Original MorphRig Operative geometry, UVs, materials, and animator rigs.
All mesh coordinates, costume elements and skin weights are authored procedurally here.
"""
from pathlib import Path
from math import sin, cos, pi, exp, sqrt
import json
import math
import numpy as np
import bpy
from mathutils import Vector, Matrix, Quaternion

ROOT = Path(__file__).resolve().parents[2]
MATERIAL_NAMES = ["M_Skin", "M_Suit", "M_Armor", "M_Metal", "M_Accent", "M_Emissive", "M_Eye", "M_Hair"]
M = {name: i for i, name in enumerate(MATERIAL_NAMES)}
FINGERS = ["thumb", "index", "middle", "ring", "pinky"]
P = {}


def V(x, y, z):
    return Vector((x, y, z))


def basis(direction):
    z = Vector(direction).normalized()
    x = V(1, 0, 0) - z * z.x
    if x.length < .01:
        x = V(0, 1, 0) - z * z.y
    x.normalize()
    y = z.cross(x).normalized()
    return Matrix((x, y, z)).transposed()


def smoothstep(a, b, x):
    t = max(0., min(1., (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def points():
    P.update(root=V(0, 0, 0), pelvis=V(0, 0, .995), neck=V(0, 0, 1.495), head=V(0, 0, 1.555))
    for side, suffix in ((1, "L"), (-1, "R")):
        P[f"shoulder.{suffix}"] = V(side * .225, 0, 1.438)
        P[f"elbow.{suffix}"] = V(side * .277, -.016, 1.183)
        P[f"wrist.{suffix}"] = V(side * .305, -.036, .962)
        P[f"hip.{suffix}"] = V(side * .105, 0, .967)
        P[f"knee.{suffix}"] = V(side * .108, -.022, .550)
        P[f"ankle.{suffix}"] = V(side * .112, -.005, .140)
    return P


def add_bone(bones, name, parent, head, tail):
    bones.append({"name": name, "parent": parent, "head": tuple(head), "tail": tuple(tail)})


def skeleton_spec():
    points()
    b = []
    add_bone(b, "root", None, V(0, 0, 0), V(0, 0, .18))
    add_bone(b, "pelvis", "root", P['pelvis'], V(0, 0, 1.095))
    for name, h, t in [
        ("spine_01", V(0, 0, 1.095), V(0, 0, 1.225)),
        ("spine_02", V(0, 0, 1.225), V(0, 0, 1.365)),
        ("spine_03", V(0, 0, 1.365), P['neck']),
        ("neck", P['neck'], P['head']),
        ("head", P['head'], V(0, 0, 1.765)),
        ("jaw", V(0, .012, 1.59), V(0, -.067, 1.555)),
    ]:
        add_bone(b, name, "pelvis" if name == "spine_01" else {"spine_01": "pelvis", "spine_02": "spine_01", "spine_03": "spine_02", "neck": "spine_03", "head": "neck", "jaw": "head"}[name], h, t)
    for suffix in ("L", "R"):
        x = -.037 if suffix == "R" else .037
        add_bone(b, f"eye.{suffix}", "head", V(x, -.058, 1.697), V(x, -.11, 1.697))
    for side, s in ((1, "L"), (-1, "R")):
        shoulder, elbow, wrist = P[f"shoulder.{s}"], P[f"elbow.{s}"], P[f"wrist.{s}"]
        add_bone(b, f"clavicle.{s}", "spine_03", V(side * .045, 0, 1.445), shoulder)
        add_bone(b, f"upperarm.{s}", f"clavicle.{s}", shoulder, elbow)
        add_bone(b, f"forearm.{s}", f"upperarm.{s}", elbow, wrist)
        add_bone(b, f"hand.{s}", f"forearm.{s}", wrist, wrist + V(0, -.006, -.085))
        d = (elbow - shoulder).normalized()
        add_bone(b, f"upperarm_twist.{s}", f"upperarm.{s}", shoulder.lerp(elbow, .45), shoulder.lerp(elbow, .45) + d * .065)
        d = (wrist - elbow).normalized()
        add_bone(b, f"forearm_twist.{s}", f"forearm.{s}", elbow.lerp(wrist, .45), elbow.lerp(wrist, .45) + d * .065)
        hip, knee, ankle = P[f"hip.{s}"], P[f"knee.{s}"], P[f"ankle.{s}"]
        add_bone(b, f"thigh.{s}", "pelvis", hip, knee)
        add_bone(b, f"shin.{s}", f"thigh.{s}", knee, ankle)
        add_bone(b, f"foot.{s}", f"shin.{s}", ankle, V(side * .112, -.16, .105))
        add_bone(b, f"toe.{s}", f"foot.{s}", V(side * .112, -.14, .072), V(side * .112, -.205, .062))
        add_bone(b, f"thigh_twist.{s}", f"thigh.{s}", hip.lerp(knee, .45), hip.lerp(knee, .45) + (knee - hip).normalized() * .06)
        add_bone(b, f"shin_twist.{s}", f"shin.{s}", knee.lerp(ankle, .45), knee.lerp(ankle, .45) + (ankle - knee).normalized() * .06)
        if s == "R":
            add_bone(b, "blade_slide", "forearm.R", elbow.lerp(wrist, .43), elbow.lerp(wrist, .43) + (wrist - elbow).normalized() * .25)
            add_bone(b, "cell", "forearm.R", elbow.lerp(wrist, .69) + V(0, -.047, 0), elbow.lerp(wrist, .69) + V(0, -.047, -.07))
        else:
            add_bone(b, "beacon", "pelvis", V(.17, .075, 1.00), V(.17, .075, 1.06))
        starts = {
            "index": V(-.022, -.008, -.076), "middle": V(-.006, -.008, -.081),
            "ring": V(.011, -.008, -.077), "pinky": V(.026, -.007, -.069),
            "thumb": V(-side * .031, -.014, -.028),
        }
        lengths = {"thumb": [.026, .022, .018], "index": [.028, .022, .017], "middle": [.031, .025, .019], "ring": [.028, .023, .018], "pinky": [.023, .018, .015]}
        for finger in FINGERS:
            parent = f"hand.{s}"
            position = wrist + starts[finger]
            direction = V(-side * .50, -.32, -.78).normalized() if finger == "thumb" else V(0, -.10, -1).normalized()
            for j, length in enumerate(lengths[finger]):
                end = position + direction * length
                add_bone(b, f"{finger}_{j + 1:02d}.{s}", parent, position, end)
                parent = f"{finger}_{j + 1:02d}.{s}"
                position = end
    for i in range(3):
        h = V(.112 + .018 * i, .091 + .009 * i, 1.34 - .075 * i)
        add_bone(b, f"cable_{i + 1:02d}", "spine_03" if i == 0 else f"cable_{i:02d}", h, h + V(.023, .01, -.08))
    return b


class Builder:
    def __init__(self):
        self.vertices = []
        self.weights = []
        self.parts = []
        self.faces = []
        self.face_mats = []
        self.face_uv = []
        self.face_primitives = []
        self.face_smooth = []
        self.primitive = -1
        self.part_primitives = []

    def vert(self, co, weights, part):
        self.vertices.append(tuple(co))
        self.weights.append({weights: 1.0} if isinstance(weights, str) else dict(weights))
        self.parts.append(part)
        return len(self.vertices) - 1

    def face(self, indices, mat, uv=None, smooth=True):
        self.faces.append(tuple(indices))
        self.face_mats.append(M[mat] if isinstance(mat, str) else mat)
        self.face_uv.append(uv or [(0, 0)] * len(indices))
        self.face_primitives.append(self.primitive)
        self.face_smooth.append(smooth)

    def sphere(self, center, scale, bone, mat, part, seg=24, rings=16, rotation=None, deform=None):
        self.primitive += 1
        self.part_primitives.append(part)
        center = Vector(center)
        rotation = rotation or Matrix.Identity(3)
        def pos(theta, phi):
            p = V(scale[0] * sin(theta) * cos(phi), scale[1] * sin(theta) * sin(phi), scale[2] * cos(theta))
            if deform:
                p = deform(p, theta, phi)
            return center + rotation @ p
        north = self.vert(pos(0, 0), bone, part)
        rows = []
        for i in range(1, rings):
            rows.append([self.vert(pos(pi * i / rings, 2 * pi * j / seg), bone, part) for j in range(seg)])
        south = self.vert(pos(pi, 0), bone, part)
        for j in range(seg):
            j1 = (j + 1) % seg
            self.face((north, rows[0][j], rows[0][j1]), mat, [( .5 + .5 * cos(2 * pi * j / seg), 1), (j / seg, (rings - 1) / rings), ((j + 1) / seg, (rings - 1) / rings)])
            for i in range(len(rows) - 1):
                self.face((rows[i][j], rows[i + 1][j], rows[i + 1][j1], rows[i][j1]), mat, [(j / seg, (rings - 1 - i) / rings), (j / seg, (rings - 2 - i) / rings), ((j + 1) / seg, (rings - 2 - i) / rings), ((j + 1) / seg, (rings - 1 - i) / rings)])
            self.face((rows[-1][j], south, rows[-1][j1]), mat, [(j / seg, 1 / rings), (.5, 0), ((j + 1) / seg, 1 / rings)])

    def loft(self, centers, radii, weights, mat, part, sides=12, orient=None):
        self.primitive += 1
        self.part_primitives.append(part)
        centers = [Vector(c) for c in centers]
        rows = []
        for i, (center, radius) in enumerate(zip(centers, radii)):
            rot = basis(centers[min(i + 1, len(centers) - 1)] - centers[max(0, i - 1)]) if orient is None else orient
            rx, ry = (radius, radius) if isinstance(radius, (float, int)) else radius
            row = []
            for j in range(sides):
                co = center + rot @ V(rx * cos(2 * pi * j / sides), ry * sin(2 * pi * j / sides), 0)
                w = weights[i] if isinstance(weights, list) else weights
                row.append(self.vert(co, w, part))
            rows.append(row)
        for i in range(len(rows) - 1):
            for j in range(sides):
                k = (j + 1) % sides
                self.face((rows[i][j], rows[i][k], rows[i + 1][k], rows[i + 1][j]), mat, [(j / sides, i / (len(rows) - 1)), ((j + 1) / sides, i / (len(rows) - 1)), ((j + 1) / sides, (i + 1) / (len(rows) - 1)), (j / sides, (i + 1) / (len(rows) - 1))])
        self.face(tuple(reversed(rows[0])), mat, [(.5 + .46 * cos(2 * pi * j / sides), .5 + .46 * sin(2 * pi * j / sides)) for j in reversed(range(sides))], False)
        self.face(rows[-1], mat, [(.5 + .46 * cos(2 * pi * j / sides), .5 + .46 * sin(2 * pi * j / sides)) for j in range(sides)], False)

    def tube(self, pts, radius, bone, mat, part, sides=8):
        pts = [Vector(p) for p in pts]
        self.loft(pts, [radius] * len(pts), bone, mat, part, sides)

    def box(self, center, size, bone, mat, part, rotation=None, bevel=.13):
        self.primitive += 1
        self.part_primitives.append(part)
        center = Vector(center)
        rot = rotation or Matrix.Identity(3)
        hx, hy, hz = [v * .5 for v in size]
        chamfer = min(hx, hy) * bevel
        outline = [(-hx + chamfer, -hy), (hx - chamfer, -hy), (hx, -hy + chamfer), (hx, hy - chamfer), (hx - chamfer, hy), (-hx + chamfer, hy), (-hx, hy - chamfer), (-hx, -hy + chamfer)]
        rows = []
        for z, shrink in [(-hz, 1 - bevel * .55), (-hz + min(hz * .3, chamfer), 1), (hz - min(hz * .3, chamfer), 1), (hz, 1 - bevel * .55)]:
            rows.append([self.vert(center + rot @ V(x * shrink, y * shrink, z), bone, part) for x, y in outline])
        for i in range(3):
            for j in range(8):
                k = (j + 1) % 8
                self.face((rows[i][j], rows[i][k], rows[i + 1][k], rows[i + 1][j]), mat, [(j / 8, i / 3), ((j + 1) / 8, i / 3), ((j + 1) / 8, (i + 1) / 3), (j / 8, (i + 1) / 3)], i != 1)
        self.face(tuple(reversed(rows[0])), mat, [(x / (2 * hx) + .5, y / (2 * hy) + .5) for x, y in reversed(outline)], False)
        self.face(rows[-1], mat, [(x / (2 * hx) + .5, y / (2 * hy) + .5) for x, y in outline], False)

    def object(self, name, collection, rig, materials, tile_grid=16):
        mesh = bpy.data.meshes.new(name + "_Mesh")
        mesh.from_pydata(self.vertices, [], self.faces)
        mesh.update()
        uv = mesh.uv_layers.new(name="UVMap")
        grid = tile_grid
        tiles = max(1, self.primitive + 1)
        for poly, mat, coords, primitive, smooth in zip(mesh.polygons, self.face_mats, self.face_uv, self.face_primitives, self.face_smooth):
            poly.material_index = mat
            poly.use_smooth = smooth
            tile_x, tile_y = primitive % grid, primitive // grid
            for loop_index, (u, v) in zip(poly.loop_indices, coords):
                uv.data[loop_index].uv = ((tile_x + .025 + .95 * u) / grid, (tile_y + .025 + .95 * v) / grid)
        for mat in materials:
            mesh.materials.append(mat)
        obj = bpy.data.objects.new(name, mesh)
        collection.objects.link(obj)
        for group_name in {name for weights in self.weights for name in weights}:
            obj.vertex_groups.new(name=group_name)
        for i, weights in enumerate(self.weights):
            total = sum(weights.values())
            for bone, weight in weights.items():
                if weight > 0:
                    obj.vertex_groups[bone].add([i], weight / total, 'REPLACE')
        arm = obj.modifiers.new("Operative deformation skeleton", 'ARMATURE')
        arm.object = rig
        arm.use_deform_preserve_volume = True
        obj.parent = rig
        obj["authorship"] = "Original procedural geometry, UVs and explicit weights; MorphRig assignment"
        obj["max_influences"] = max(len(weights) for weights in self.weights) if self.weights else 0
        return obj


def make_materials(collection):
    texture_dir = ROOT / "source" / "textures"
    export_dir = ROOT / "export" / "textures"
    texture_dir.mkdir(parents=True, exist_ok=True)
    export_dir.mkdir(parents=True, exist_ok=True)
    specs = {
        "skin": ((.56, .31, .205), .51, 0, 1024), "suit": ((.026, .066, .076), .62, 0, 2048),
        "armor": ((.105, .145, .17), .32, .68, 2048), "metal": ((.28, .32, .36), .29, .90, 1024),
        "accent": ((.68, .84, .85), .31, .35, 1024), "emissive": ((.025, .55, .65), .28, .25, 512),
        "eye": ((.78, .79, .75), .26, 0, 512), "hair": ((.006, .011, .017), .72, 0, 1024),
    }
    images = {}
    rng = np.random.default_rng(731)
    for name, (color, rough, metal, size) in specs.items():
        h = w = size
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32) / size
        noise = rng.normal(0, .012, (h, w))
        pattern = noise
        if name == "suit":
            pattern += .020 * np.sin(xx * 180) * np.sin(yy * 170)
            pattern += .024 * ((xx * 32) % 1 < .06)
        elif name in ("armor", "metal"):
            pattern += .015 * np.sin(yy * 600) + .01 * ((yy * 90) % 1 < .08)
        elif name == "hair":
            pattern += .065 * np.sin(xx * 330 + np.sin(yy * 9))
        elif name == "skin":
            pattern += .012 * np.sin(xx * 11) * np.sin(yy * 13)
        rgb = np.zeros((h, w, 4), dtype=np.float32)
        for channel, value in enumerate(color):
            rgb[:, :, channel] = np.clip(value + pattern, .002, 1)
        rgb[:, :, 3] = 1
        paths = {}
        for kind, pixels in [("BaseColor", rgb), ("Roughness", np.dstack([np.clip(rough + noise * 2, .08, 1)] * 3 + [np.ones((h, w))])), ("Normal", np.dstack([.5 + noise * .35, .5 + np.roll(noise, 1, 1) * .35, np.ones((h, w)), np.ones((h, w))]))]:
            image = bpy.data.images.new(f"Operative_{name}_{kind}", width=w, height=h, alpha=True)
            if kind != "BaseColor":
                image.colorspace_settings.name = 'Non-Color'
            image.pixels.foreach_set(pixels.astype(np.float32).ravel())
            image.update()
            path = texture_dir / f"{name}_{kind}.png"
            image.filepath_raw = str(path)
            image.file_format = 'PNG'
            image.save()
            image.pack()
            image.filepath = f"//textures/{path.name}"
            images[f"{name}_{kind}"] = image
            paths[kind] = f"textures/{path.name}"
            (export_dir / path.name).write_bytes(path.read_bytes())
        (texture_dir / f"{name}_description.json").write_text(json.dumps({"size": size, "base_color_linear": color, "roughness": rough, "metalness": metal, "maps": paths}, indent=2))
    materials = []
    for name, token in zip(MATERIAL_NAMES, [k.lower() for k in MATERIAL_NAMES]):
        key = token.split("_")[1]
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        bsdf = nodes.get("Principled BSDF")
        bsdf.inputs["Metallic"].default_value = specs[key][2]
        bsdf.inputs["Specular IOR Level"].default_value = .18 if key == "hair" else .35
        base = nodes.new("ShaderNodeTexImage"); base.name = "Authored_BaseColor"; base.image = images[key + "_BaseColor"]; base.location = (-550, 200)
        rough = nodes.new("ShaderNodeTexImage"); rough.name = "Authored_Roughness"; rough.image = images[key + "_Roughness"]; rough.location = (-550, -60)
        normal = nodes.new("ShaderNodeTexImage"); normal.name = "Authored_Normal"; normal.image = images[key + "_Normal"]; normal.location = (-760, -300)
        normal_node = nodes.new("ShaderNodeNormalMap"); normal_node.inputs["Strength"].default_value = .28 if key == "skin" else .45; normal_node.location = (-270, -200)
        links.new(base.outputs["Color"], bsdf.inputs["Base Color"])
        links.new(rough.outputs["Color"], bsdf.inputs["Roughness"])
        links.new(normal.outputs["Color"], normal_node.inputs["Color"]); links.new(normal_node.outputs["Normal"], bsdf.inputs["Normal"])
        if key == "accent":
            tint = nodes.new("ShaderNodeMixRGB"); tint.blend_type = 'MULTIPLY'; tint.inputs[0].default_value = 1; tint.name = "TeamTint"; tint.label = "0 = cyan team / 1 = amber team"; tint.inputs[2].default_value = (.04, .55, .72, 1); tint.location = (-250, 220)
            links.new(base.outputs["Color"], tint.inputs[1]); links.new(tint.outputs[0], bsdf.inputs["Base Color"])
        if key == "emissive":
            links.new(base.outputs["Color"], bsdf.inputs["Emission Color"]); bsdf.inputs["Emission Strength"].default_value = 3.0
        mat.diffuse_color = (*specs[key][0], 1)
        mat["texture_size"] = specs[key][3]
        materials.append(mat)
    return materials


def torso_weights(z):
    if z < 1.06:
        t = smoothstep(.99, 1.06, z)
        return {"pelvis": 1 - t, "spine_01": t}
    if z < 1.22:
        t = smoothstep(1.06, 1.22, z)
        return {"spine_01": 1 - t, "spine_02": t}
    if z < 1.39:
        t = smoothstep(1.22, 1.39, z)
        return {"spine_02": 1 - t, "spine_03": t}
    t = smoothstep(1.39, 1.49, z)
    return {"spine_03": 1 - t, "neck": t}


def limb_weights(prefix, s, i, n, upper, lower):
    t = i / (n - 1)
    w = {}
    if t < .35:
        w[upper] = 1
    elif t < .56:
        blend = smoothstep(.35, .56, t)
        w[upper] = 1 - blend
        w[lower] = blend
    else:
        w[lower] = 1
    twist = upper + "_twist" if t < .4 else lower + "_twist"
    if t > .18 and t < .83:
        w[twist + "." + s] = .20
        for key in list(w):
            if key != twist + "." + s:
                w[key] *= .8
    return w


def build_body():
    b = Builder()
    rings_z = [.945, .978, 1.025, 1.09, 1.16, 1.23, 1.30, 1.365, 1.425, 1.465]
    radii = [(.122, .078), (.144, .091), (.138, .087), (.123, .074), (.111, .067), (.127, .078), (.153, .086), (.185, .092), (.203, .084), (.13, .065)]
    b.loft([V(0, 0, z) for z in rings_z], radii, [torso_weights(z) for z in rings_z], "M_Suit", "torso", 24)
    b.loft([V(0, 0, z) for z in (1.445, 1.475, 1.51, 1.55, 1.57)], [(.063, .052), (.052, .047), (.045, .043), (.045, .044), (.055, .047)], ["spine_03", "neck", "neck", {"neck": .35, "head": .65}, "head"], "M_Skin", "neck", 16)
    for side, s in ((1, "L"), (-1, "R")):
        shoulder, elbow, wrist = P[f"shoulder.{s}"], P[f"elbow.{s}"], P[f"wrist.{s}"]
        arm_centers = [shoulder, shoulder.lerp(elbow, .14), shoulder.lerp(elbow, .32), shoulder.lerp(elbow, .46), elbow, elbow.lerp(wrist, .12), elbow.lerp(wrist, .32), elbow.lerp(wrist, .62), elbow.lerp(wrist, .84), wrist]
        arm_radii = [(.066, .064), (.062, .060), (.054, .053), (.047, .046), (.043, .042), (.043, .043), (.048, .045), (.044, .041), (.034, .031), (.028, .025)]
        weights = [limb_weights("upperarm" if i < 5 else "forearm", s, i, 9, "upperarm." + s, "forearm." + s) for i in range(10)]
        for i, weight in enumerate(weights):
            if i < 5:
                t = i / 4
                upper = 1 - .45 * t
                weight = {"upperarm." + s: upper, "forearm." + s: .45 * t}
                if i in (1, 2): weight["upperarm_twist." + s] = .18; weight["upperarm." + s] -= .18
                weights[i] = weight
            else:
                t = (i - 4) / 5
                weight = {"forearm." + s: 1.0}
                if i in (5, 6, 7): weight["forearm_twist." + s] = .22; weight["forearm." + s] = .78
                if i == 9: weight = {"forearm." + s: .3, "hand." + s: .7}
                weights[i] = weight
        b.loft(arm_centers, arm_radii, weights, "M_Skin" if s == "L" else "M_Suit", "organic_arm." + s if s == "L" else "arm." + s, 16)
        if s == "R":
            shell_weights = [{k: v for k, v in weights[i].items() if not k.endswith("hand.R")} or "forearm.R" for i in range(5, 10)]
            b.loft(arm_centers[5:10], [(r[0] * 1.075, r[1] * 1.075) for r in arm_radii[5:10]], shell_weights, "M_Metal", "cyber_forearm", 16)
            rot = basis(wrist - elbow)
            for t in (.15, .53, .84):
                c = elbow.lerp(wrist, t) + V(0, -.038, 0)
                b.box(c, (.071, .026, .055), "forearm.R", "M_Armor", "forearm_armor", rot)
            b.tube([elbow.lerp(wrist, .10) + V(.025 * side, .026, 0), elbow.lerp(wrist, .55) + V(.025 * side, .026, 0), wrist + V(.018, .02, .018)], .007, "forearm.R", "M_Accent", "forearm_conduit")
        # Intentional joint rings, ankle volumes and fitted leg topology.
        hip, knee, ankle = P[f"hip.{s}"], P[f"knee.{s}"], P[f"ankle.{s}"]
        centers = [hip, hip.lerp(knee, .12), hip.lerp(knee, .32), hip.lerp(knee, .43), knee, knee.lerp(ankle, .12), knee.lerp(ankle, .33), knee.lerp(ankle, .62), knee.lerp(ankle, .85), ankle]
        radii = [(.082, .085), (.079, .082), (.071, .072), (.061, .064), (.054, .055), (.053, .052), (.056, .054), (.047, .048), (.037, .038), (.036, .035)]
        weights = []
        for i in range(10):
            if i < 4: w = {"thigh." + s: .85, "pelvis": .15} if i == 0 else {"thigh." + s: 1}
            elif i == 4: w = {"thigh." + s: .45, "shin." + s: .55}
            elif i < 9: w = {"shin." + s: 1}
            else: w = {"shin." + s: .25, "foot." + s: .75}
            if i in (2, 3): w["thigh_twist." + s] = .18; w["thigh." + s] = w.get("thigh." + s, 0) - .18
            if i in (6, 7): w["shin_twist." + s] = .20; w["shin." + s] = .8
            weights.append(w)
        b.loft(centers, radii, weights, "M_Suit", "leg." + s, 16)
        b.box((side * .108, -.059, .55), (.095, .039, .104), {"thigh." + s: .48, "shin." + s: .52}, "M_Armor", "knee_plate")
        b.box((side * .112, -.051, .075), (.104, .199, .124), "foot." + s, "M_Armor", "boot", bevel=.22)
        b.box((side * .112, -.14, .055), (.10, .095, .061), "toe." + s, "M_Metal", "toe_cap", bevel=.22)
        b.box((side * .112, -.04, .012), (.108, .20, .024), "foot." + s, "M_Suit", "sole")
        # Limited rigid armor with broad, readable graphic panels.
        b.box((side * .103, -.087, 1.36), (.167, .033, .145), "spine_03", "M_Armor", "chest_armor", Matrix.Rotation(side * -.10, 3, 'Y'))
        b.box((side * .109, -.106, 1.392), (.093, .009, .018), "spine_03", "M_Accent", "chest_chevron", Matrix.Rotation(side * -.25, 3, 'Y'))
        b.box((side * .224, -.004, 1.431), (.126, .148, .066), f"clavicle.{s}", "M_Armor", "shoulder_armor", Matrix.Rotation(side * -.15, 3, 'Y'))
        b.box((side * .116, -.084, 1.047), (.097, .032, .068), "pelvis", "M_Armor", "belt_pouch")
        b.box((side * .128, -.076, 1.20), (.027, .016, .087), torso_weights(1.20), "M_Accent", "suit_contrast")
        # Palm and all fifteen finger phalanges.
        b.box(wrist + V(0, -.004, -.042), (.062, .031, .077), "hand." + s, "M_Skin", "palm." + s, bevel=.24)
        b.box(wrist + V(0, .009, -.038), (.054, .014, .053), "hand." + s, "M_Suit", "fingerless_glove", bevel=.20)
        for finger in FINGERS:
            for j in range(3):
                name = f"{finger}_{j + 1:02d}.{s}"
                bone = next(item for item in SPEC if item["name"] == name)
                h, t = Vector(bone["head"]), Vector(bone["tail"])
                direction = t - h
                radius = .0092 if finger != "pinky" else .0076
                radius *= (1 - .10 * j)
                b.loft([h, h.lerp(t, .15), h.lerp(t, .76), t], [radius * .91, radius, radius * .87, radius * .74], name, "M_Skin", finger + "." + s, 10)
                b.sphere(h, (radius * .96,) * 3, name, "M_Skin", "knuckle_" + finger + "." + s, 10, 6)
        b.box(wrist + V(0, .0, -.002), (.063, .064, .029), "hand." + s, "M_Metal", "wrist_cuff", basis(wrist - elbow), bevel=.16)
    b.box((0, -.082, 1.028), (.065, .027, .043), "pelvis", "M_Metal", "belt_buckle")
    b.box((0, -.098, 1.028), (.031, .009, .016), "pelvis", "M_Accent", "team_icon")
    # Back-mounted compact relay and a bounded three-bone secondary cable.
    b.box((0, .093, 1.33), (.156, .056, .177), "spine_03", "M_Armor", "relay_pack")
    b.box((0, .125, 1.34), (.078, .014, .072), "spine_03", "M_Emissive", "relay_status")
    cable_pts = [V(.112, .091, 1.34), V(.129, .101, 1.272), V(.148, .108, 1.19), V(.166, .12, 1.117)]
    b.tube(cable_pts, .008, [{"cable_01": 1}, {"cable_01": .45, "cable_02": .55}, {"cable_02": .4, "cable_03": .6}, "cable_03"], "M_Metal", "secondary_cable", 10)
    return b


def build_face():
    b = Builder()
    center = V(0, 0, 1.662)
    def face_deform(p, theta, phi):
        z = 1.662 + p.z
        if p.z < -.015:
            p.x *= .94 + .06 * smoothstep(-.136, -.015, p.z)
        if p.y < 0:
            front = min(1, (-p.y / .09) ** 3)
            for x in (-.037, .037):
                eye = exp(-((p.x - x) / .030) ** 2 - ((z - 1.697) / .022) ** 2)
                p.y += .010 * eye * front
            cheek = exp(-((abs(p.x) - .052) / .029) ** 2 - ((z - 1.657) / .030) ** 2)
            p.y -= .007 * cheek * front
            nose = exp(-(p.x / .012) ** 2 - ((z - 1.673) / .036) ** 2)
            p.y -= .010 * nose * front
            if z < 1.595:
                p.y += .008 * smoothstep(1.595, 1.53, z)
        return p
    # Vertex weights are assigned after evaluating the deformed head coordinates.
    before = len(b.vertices)
    b.sphere(center, (.097, .089, .136), "head", "M_Skin", "head", 48, 32, deform=face_deform)
    for i in range(before, len(b.vertices)):
        z = b.vertices[i][2]
        t = smoothstep(1.59, 1.535, z)
        b.weights[i] = {"head": 1 - .68 * t, "jaw": .68 * t} if b.vertices[i][1] < .04 else {"head": 1.0}
    for side, s in ((1, "L"), (-1, "R")):
        b.sphere(V(side * .095, .0, 1.661), (.015, .016, .030), "head", "M_Skin", "ear." + s, 20, 14)
        b.sphere(V(side * .102, -.010, 1.663), (.006, .005, .017), "head", "M_Hair", "ear_inner." + s, 12, 8)
        x = side * .037
        b.sphere(V(x, -.076, 1.697), (.0195, .011, .0105), "eye." + s, "M_Eye", "eyeball." + s, 28, 16)
        b.sphere(V(x, -.0870, 1.697), (.0078, .0023, .0078), "eye." + s, "M_Accent", "iris." + s, 24, 12)
        b.sphere(V(x, -.0890, 1.697), (.0036, .0011, .0041), "eye." + s, "M_Hair", "pupil." + s, 20, 10)
        b.sphere(V(x - .002, -.0899, 1.700), (.0012, .0005, .0012), "eye." + s, "M_Eye", "eye_highlight." + s, 12, 8)
        b.sphere(V(x, -.0845, 1.697), (.0192, .0014, .0015), "head", "M_Skin", "blink_cover." + s, 28, 10)
        upper, lower = [], []
        for j in range(17):
            t = j / 16
            xx = x + (t - .5) * .043
            arch = sin(t * pi)
            upper.append(V(xx, -.083 - .006 * arch, 1.697 + .001 + .0098 * arch))
            lower.append(V(xx, -.083 - .006 * arch, 1.697 - .001 - .0065 * arch))
        b.tube(upper, .0018, "head", "M_Skin", "lid_upper." + s, 8)
        b.tube(lower, .0015, "head", "M_Skin", "lid_lower." + s, 8)
        brow = [V(x - .024, -.075, 1.722), V(x - .012, -.082, 1.727), V(x + .007, -.082, 1.727), V(x + .025, -.073, 1.723)]
        b.tube(brow, .0024, "head", "M_Hair", "brow." + s, 8)
    b.sphere(V(0, -.086, 1.669), (.009, .010, .023), "head", "M_Skin", "nose_bridge", 28, 18)
    b.sphere(V(0, -.096, 1.650), (.011, .009, .007), "head", "M_Skin", "nose_tip", 24, 14)
    for side, s in ((1, "L"), (-1, "R")):
        b.sphere(V(side * .007, -.098, 1.646), (.003, .002, .0014), "head", "M_Hair", "nostril." + s, 12, 8)
    # Closed neutral lips surround a shallow cavity; the jaw and visemes open it without exposing the skull.
    b.sphere(V(0, -.0885, 1.612), (.029, .0032, .0023), "jaw", "M_Hair", "mouth_cavity", 32, 12)
    for upper in (True, False):
        for side, s in ((1, "L"), (-1, "R")):
            pts = []
            for j in range(17):
                t = j / 16
                x = side * t * .029
                z = 1.612 + (1 if upper else -1) * (.00035 + .0009 * sin(t * pi))
                y = -.0895 - .004 * sin(t * pi)
                pts.append(V(x, y, z))
            b.tube(pts, .0017 if upper else .0019, "head" if upper else "jaw", "M_Skin", ("lip_upper." if upper else "lip_lower.") + s, 8)
    b.box(V(0, -.078, 1.613), (.043, .003, .0025), "head", "M_Eye", "teeth_upper", bevel=.18)
    b.box(V(0, -.078, 1.610), (.040, .003, .0025), "jaw", "M_Eye", "teeth_lower", bevel=.18)
    b.sphere(V(0, -.086, 1.609), (.019, .004, .0027), "jaw", "M_Skin", "tongue", 24, 12)
    # Short swept hair cap, kept above the face and under 1.80 m.
    b.primitive += 1; b.part_primitives.append("hair_cap")
    rows = []
    seg, rings = 40, 12
    for i in range(rings):
        row = []
        for j in range(seg):
            phi = j / seg * 2 * pi
            front = max(0, -sin(phi))
            theta_max = 1.91 - .86 * front
            theta = .025 + (theta_max - .025) * i / (rings - 1)
            row.append(b.vert(V(.101 * sin(theta) * cos(phi), .093 * sin(theta) * sin(phi), 1.661 + .139 * cos(theta)), "head", "hair_cap"))
        rows.append(row)
    top = b.vert(V(0, 0, 1.800), "head", "hair_cap")
    for j in range(seg):
        k = (j + 1) % seg
        b.face((top, rows[0][j], rows[0][k]), "M_Hair", [(.5, 1), (j / seg, .95), ((j + 1) / seg, .95)])
        for i in range(rings - 1):
            b.face((rows[i][j], rows[i + 1][j], rows[i + 1][k], rows[i][k]), "M_Hair", [(j / seg, 1 - i / rings), (j / seg, 1 - (i + 1) / rings), ((j + 1) / seg, 1 - (i + 1) / rings), ((j + 1) / seg, 1 - i / rings)])
    b.tube([V(.044, -.060, 1.761), V(.016, -.088, 1.788), V(-.020, -.080, 1.788), V(-.046, -.059, 1.770)], .012, "head", "M_Hair", "swept_forelock", 10)
    return b


def build_props():
    b = Builder()
    elbow, wrist = P["elbow.R"], P["wrist.R"]
    direction = (wrist - elbow).normalized()
    rot = basis(direction)
    c = elbow.lerp(wrist, .64) + V(0, -.037, 0)
    b.box(c, (.068, .070, .114), "forearm.R", "M_Armor", "wrist_emitter", rot)
    b.loft([c + direction * .025, c + direction * .065, c + direction * .103], [(.026, .025), (.026, .025), (.022, .022)], "forearm.R", "M_Metal", "emitter_barrel", 16, rot)
    b.loft([c + direction * .101, c + direction * .104], [(.015, .015), (.015, .015)], "forearm.R", "M_Emissive", "emitter_muzzle", 16, rot)
    for offset in (-.021, .021):
        b.box(c + V(offset, -.038, 0), (.012, .013, .075), "forearm.R", "M_Accent", "emitter_rail", rot)
    # Attached original tapered forearm blade with a luminous edge.
    start = elbow.lerp(wrist, .40) + V(-.037, -.006, 0)
    tip = start + direction * .305
    width_axis = rot @ V(1, 0, 0)
    thick_axis = rot @ V(0, 1, 0)
    b.primitive += 1; b.part_primitives.append("forearm_blade")
    v = [b.vert(start - width_axis * .012 - thick_axis * .003, "blade_slide", "blade_base"), b.vert(start + width_axis * .012 - thick_axis * .003, "blade_slide", "blade_base"), b.vert(start + width_axis * .009 + thick_axis * .003, "blade_slide", "blade_base"), b.vert(start - width_axis * .009 + thick_axis * .003, "blade_slide", "blade_base"), b.vert(tip, "blade_slide", "blade_tip")]
    for i in range(4):
        j = (i + 1) % 4
        b.face((v[i], v[j], v[4]), "M_Metal", [(0, 0), (1, 0), (.5, 1)], False)
    b.face((v[3], v[2], v[1], v[0]), "M_Accent", [(0, 0), (1, 0), (1, 1), (0, 1)], False)
    b.tube([start + width_axis * .011, start.lerp(tip, .72) + width_axis * .006, tip], .0024, "blade_slide", "M_Emissive", "blade_edge", 6)
    cell_center = elbow.lerp(wrist, .69) + V(0, -.084, 0)
    b.box(cell_center, (.040, .034, .082), "cell", "M_Metal", "power_cell", rot)
    b.box(cell_center + V(0, -.018, 0), (.024, .006, .049), "cell", "M_Emissive", "cell_charge", rot)
    b.box(cell_center + direction * .044, (.031, .030, .012), "cell", "M_Accent", "cell_latch", rot)
    beacon = V(.17, .075, 1.023)
    b.sphere(beacon, (.040, .033, .028), "beacon", "M_Armor", "beacon_core", 20, 12)
    b.sphere(beacon + V(0, -.029, .006), (.015, .008, .013), "beacon", "M_Emissive", "beacon_lens", 16, 10)
    for j in range(3):
        angle = j * 2 * pi / 3
        end = beacon + V(.052 * cos(angle), .052 * sin(angle), -.027)
        b.tube([beacon + V(.017 * cos(angle), .017 * sin(angle), -.005), end], .005, "beacon", "M_Metal", "beacon_leg", 6)
    return b


def add_shape_keys(obj):
    obj.shape_key_add(name="Basis")
    names = ["JawOpen", "Blink.L", "Blink.R", "Squint.L", "Squint.R", "BrowRaise.L", "BrowRaise.R", "BrowLower.L", "BrowLower.R", "Cheek.L", "Cheek.R", "LipClosed", "Smile.L", "Smile.R", "Frown.L", "Frown.R", "MouthWidth", "Pucker", "Funnel", "Viseme_MBP", "Viseme_FV", "Viseme_AA", "Viseme_EE", "Viseme_OO", "Viseme_TH", "Viseme_CH"]
    keys = {}
    for name in names:
        keys[name] = obj.shape_key_add(name=name, from_mix=False)
        keys[name].value = 0.0
    original = [Vector(v.co) for v in obj.data.vertices]
    for index, (co, part) in enumerate(zip(original, PARTS)):
        for name, key in keys.items():
            delta = morph_delta(name, co, part)
            key.data[index].co = co + delta
    for key in keys.values():
        key.value = 0.0
    obj.active_shape_key_index = 0
    obj["facial_controls"] = json.dumps(names)
    return names


def morph_delta(name, co, part):
    d = V(0, 0, 0)
    x, y, z = co
    side = "L" if x > 0 else "R"
    relevant = part.endswith("." + side)
    def mouth_weight():
        return min(1, abs(x) / .033)
    if name == "JawOpen":
        if part.startswith("lip_lower") or part in ("teeth_lower", "tongue"):
            d.z -= .027
        if part == "teeth_upper":
            d.y -= .012
        if part == "teeth_lower":
            d.y -= .015
        if part.startswith("lip_upper"):
            d.z += .0015
        if part == "mouth_cavity":
            d.z = (z - 1.612) * 6.5 - .0095
            d.y -= .003
        if part == "head" and z < 1.625 and y < .045:
            w = smoothstep(1.625, 1.54, z)
            d.z -= .020 * w; d.y += .005 * w
    elif name.startswith("Blink") and relevant:
        if part.startswith("lid_upper"):
            d.z -= .0100; d.y -= .002
        elif part.startswith("lid_lower"):
            d.z += .0070; d.y -= .002
        elif part.startswith("blink_cover"):
            d.z = (z - 1.697) * 7.0
            d.y -= .0060
    elif name.startswith("Squint") and relevant:
        if part.startswith("lid_lower"): d.z += .0042
        if part.startswith("lid_upper"): d.z -= .0020
    elif name.startswith("BrowRaise"):
        if part == "brow." + name[-1]: d.z += .007
        if part == "head" and (1 if name[-1] == 'L' else -1) * x > 0:
            d.z += .003 * exp(-((abs(x) - .038) / .03) ** 2 - ((z - 1.725) / .018) ** 2)
    elif name.startswith("BrowLower"):
        if part == "brow." + name[-1]: d.z -= .005; d.x -= (1 if x > 0 else -1) * .002
    elif name.startswith("Cheek"):
        if part == "head" and (1 if name[-1] == 'L' else -1) * x > 0 and y < -.025:
            w = exp(-((abs(x) - .053) / .03) ** 2 - ((z - 1.655) / .027) ** 2)
            d.y -= .009 * w; d.z += .003 * w
    elif name in ("LipClosed", "Viseme_MBP") and part.startswith("lip_"):
        d.z += (1.612 - z) * (.95 if name == "LipClosed" else .90)
        d.y -= .002
    elif name.startswith("Smile") or name.startswith("Frown"):
        if part.startswith("lip_") and part.endswith(name[-1]):
            w = mouth_weight() ** 1.4
            d.z += (.008 if name.startswith("Smile") else -.006) * w
            d.x += (1 if x > 0 else -1) * .002 * w
    elif name == "MouthWidth" and (part.startswith("lip_") or part == "mouth_cavity"):
        d.x += x * .22
    elif name in ("Pucker", "Funnel") and (part.startswith("lip_") or part == "mouth_cavity"):
        d.x *= -.36 if name == "Pucker" else -.25
        d.y -= .009 if name == "Pucker" else .006
        if name == "Funnel": d.z = (1.612 - z) * .35
    elif name == "Viseme_FV":
        if part.startswith("lip_upper"): d.z -= .0035; d.y += .002
        if part.startswith("lip_lower"): d.z += .0015; d.y -= .002
    elif name in ("Viseme_AA", "Viseme_EE", "Viseme_OO", "Viseme_TH", "Viseme_CH"):
        jaw = {"Viseme_AA": .85, "Viseme_EE": .16, "Viseme_OO": .28, "Viseme_TH": .18, "Viseme_CH": .13}[name]
        d += morph_delta("JawOpen", co, part) * jaw
        if name == "Viseme_EE": d += morph_delta("MouthWidth", co, part) * .75
        if name == "Viseme_OO": d += morph_delta("Pucker", co, part) * .9
        if name == "Viseme_CH" and part.startswith("lip_"): d.y -= .004
        if name == "Viseme_TH" and part == "tongue": d.y -= .016; d.z += .004
    return d


def create_armature(name, spec, collection, controls=False):
    data = bpy.data.armatures.new(name + "_Skeleton")
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    for item in spec:
        bone = data.edit_bones.new(item["name"])
        bone.head, bone.tail = item["head"], item["tail"]
        bone.use_deform = True
    for item in spec:
        if item["parent"]:
            data.edit_bones[item["name"]].parent = data.edit_bones[item["parent"]]
        head, tail = Vector(item["head"]), Vector(item["tail"])
        if item["parent"] and (Vector(next(b["head"] for b in spec if b["name"] == item["parent"])) - head).length < 1e-6:
            pass
        if item["parent"]:
            parent = data.edit_bones[item["name"]].parent
            if (parent.tail - head).length < 1e-6 and item["name"] not in ("neck", "spine_01", "spine_02", "spine_03"):
                data.edit_bones[item["name"]].use_connect = True
    if controls:
        helpers = []
        for s in ("L", "R"):
            helpers.extend([
                (f"CTRL_hand.{s}", P[f"wrist.{s}"], P[f"wrist.{s}"] + V(0, -.006, -.085)), (f"CTRL_foot.{s}", P[f"ankle.{s}"], V(P[f"ankle.{s}"].x, -.16, .105)),
                (f"CTRL_elbow.{s}", P[f"wrist.{s}"] + V(.22 if s == 'L' else -.22, .16, .05), P[f"wrist.{s}"] + V(.22 if s == 'L' else -.22, .16, .11)),
                (f"CTRL_knee.{s}", P[f"knee.{s}"] + V(0, -.4, .03), P[f"knee.{s}"] + V(0, -.4, .1)),
                (f"CTRL_heel.{s}", P[f"ankle.{s}"] + V(0, .085, -.1), P[f"ankle.{s}"] + V(0, .085, -.03)),
                (f"CTRL_toe_pivot.{s}", V(P[f"ankle.{s}"].x, -.18, .015), V(P[f"ankle.{s}"].x, -.18, .08)),
            ])
        helpers.append(("CTRL_look", V(0, -.85, 1.67), V(0, -.85, 1.76)))
        for name, head, tail in helpers:
            eb = data.edit_bones.new(name); eb.head, eb.tail = head, tail; eb.use_deform = False
        data.edit_bones["CTRL_look"].parent = data.edit_bones["root"]
    bpy.ops.object.mode_set(mode='OBJECT')
    obj.select_set(False)
    obj.show_in_front = controls
    data.display_type = 'OCTAHEDRAL'
    obj["role"] = "Editable animator control skeleton" if controls else "Connected export deformation skeleton"
    if controls:
        for s in ("L", "R"):
            for kind in ("arm", "leg"):
                obj[f"ik_{kind}_{s}"] = 0.0
                obj.id_properties_ui(f"ik_{kind}_{s}").update(min=0, max=1, description=f"FK/IK {kind} {s}; use embedded MorphRig controls to match before switching")
            obj[f"foot_roll_{s}"] = 0.0
            obj.id_properties_ui(f"foot_roll_{s}").update(min=-45, max=45)
            hand = obj.pose.bones[f"hand.{s}"]
            for finger in FINGERS:
                hand[f"curl_{finger}"] = .12
                hand.id_properties_ui(f"curl_{finger}").update(min=0, max=1)
            hand["spread"] = 0.0
            hand.id_properties_ui("spread").update(min=-1, max=1)
            limb, end, ctrl, pole = ("forearm", "hand", "CTRL_hand", "CTRL_elbow") if True else None
            ik = obj.pose.bones[f"forearm.{s}"].constraints.new('IK'); ik.target = obj; ik.subtarget = f"CTRL_hand.{s}"; ik.chain_count = 2; ik.use_stretch = False
            ik.pole_target = obj; ik.pole_subtarget = f"CTRL_elbow.{s}"; ik.pole_angle = pi / 2
            driver = ik.driver_add("influence").driver; driver.expression = "ik"
            var = driver.variables.new(); var.name = "ik"; var.targets[0].id = obj; var.targets[0].data_path = f'["ik_arm_{s}"]'
            copy = obj.pose.bones[f"hand.{s}"].constraints.new('COPY_ROTATION'); copy.target = obj; copy.subtarget = f"CTRL_hand.{s}"
            d = copy.driver_add("influence").driver; d.expression = "ik"; v = d.variables.new(); v.name = "ik"; v.targets[0].id = obj; v.targets[0].data_path = f'["ik_arm_{s}"]'
            ik = obj.pose.bones[f"shin.{s}"].constraints.new('IK'); ik.target = obj; ik.subtarget = f"CTRL_foot.{s}"; ik.chain_count = 2; ik.use_stretch = False
            ik.pole_target = obj; ik.pole_subtarget = f"CTRL_knee.{s}"; ik.pole_angle = -pi / 2
            d = ik.driver_add("influence").driver; d.expression = "ik"; v = d.variables.new(); v.name = "ik"; v.targets[0].id = obj; v.targets[0].data_path = f'["ik_leg_{s}"]'
            copy = obj.pose.bones[f"foot.{s}"].constraints.new('COPY_ROTATION'); copy.target = obj; copy.subtarget = f"CTRL_foot.{s}"
            d = copy.driver_add("influence").driver; d.expression = "ik"; v = d.variables.new(); v.name = "ik"; v.targets[0].id = obj; v.targets[0].data_path = f'["ik_leg_{s}"]'
        look = obj.pose.bones["head"].constraints.new('DAMPED_TRACK'); look.target = obj; look.subtarget = "CTRL_look"; look.track_axis = 'TRACK_Y'
        obj["look_at_weight"] = 0.0; obj.id_properties_ui("look_at_weight").update(min=0, max=1)
        d = look.driver_add("influence").driver; d.expression = "look"; v = d.variables.new(); v.name = "look"; v.targets[0].id = obj; v.targets[0].data_path = '["look_at_weight"]'
    else:
        for item in spec:
            obj.pose.bones[item["name"]].rotation_mode = 'QUATERNION'
    return obj


def make_control_shapes(collection):
    mesh = bpy.data.meshes.new("ControlRingMesh")
    vertices = [(cos(i * 2 * pi / 24) * .12, sin(i * 2 * pi / 24) * .12, 0) for i in range(24)]
    edges = [(i, (i + 1) % 24) for i in range(24)]
    mesh.from_pydata(vertices, edges, [])
    shape = bpy.data.objects.new("WGT_ControlRing", mesh); collection.objects.link(shape); shape.hide_render = True; shape.hide_set(True)
    return shape


def embed_controls():
    source = ROOT / "source" / "generators" / "rig_controls.py"
    text = bpy.data.texts.new("START_HERE_Rig_Controls.py")
    text.write(source.read_text())
    text.use_module = True


def build():
    global SPEC, PARTS
    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
    for collection in list(bpy.data.collections):
        if collection.name != "Collection": bpy.data.collections.remove(collection)
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'; scene.unit_settings.scale_length = 1.0
    scene.render.fps = 30; scene.render.fps_base = 1.0
    scene.frame_start = 0; scene.frame_end = 90
    collections = {}
    for name in ("01_CHARACTer_LOD0", "02_CHARACTER_LOD1", "03_CHARACTER_LOD2", "04_CONTROL_RIG", "05_EXPORT_RIG", "06_STAGE"):
        c = bpy.data.collections.new(name); scene.collection.children.link(c); collections[name] = c
    materials = make_materials(collections["06_STAGE"])
    SPEC = skeleton_spec()
    ctrl = create_armature("Operative_CTRL", SPEC, collections["04_CONTROL_RIG"], True)
    rig = create_armature("Operative_DEF", SPEC, collections["05_EXPORT_RIG"], False)
    shape = make_control_shapes(collections["04_CONTROL_RIG"])
    for pb in ctrl.pose.bones:
        pb.rotation_mode = 'QUATERNION'
        if pb.name.startswith("CTRL_"):
            pb.custom_shape = shape
    for item in SPEC:
        name = item["name"]
        constraint = rig.pose.bones[name].constraints.new('COPY_TRANSFORMS')
        constraint.name = "Source control: " + name
        constraint.target = ctrl; constraint.subtarget = name
        constraint.target_space = 'WORLD'; constraint.owner_space = 'WORLD'
    body = build_body().object("Operative_Body_LOD0", collections["01_CHARACTer_LOD0"], rig, materials, 16)
    face_builder = build_face()
    PARTS = face_builder.parts
    face = face_builder.object("Operative_Face", collections["01_CHARACTer_LOD0"], rig, materials, 12)
    add_shape_keys(face)
    props = build_props().object("Operative_Props", collections["01_CHARACTer_LOD0"], rig, materials, 8)
    # Genuine reduced meshes; face, eyes, hands and morph topology remain usable.
    body_lods = [body]
    for index, ratio in ((1, .48), (2, .22)):
        duplicate = body.copy(); duplicate.data = body.data.copy(); duplicate.name = f"Operative_Body_LOD{index}"
        collections[f"0{index + 1}_CHARACTER_LOD{index}"].objects.link(duplicate)
        decimate = duplicate.modifiers.new("Authored LOD reduction", 'DECIMATE'); decimate.ratio = ratio; decimate.use_collapse_triangulate = True
        bpy.context.view_layer.objects.active = duplicate
        bpy.ops.object.modifier_apply(modifier=decimate.name)
        body_lods.append(duplicate)
        for obj in (face, props): collections[f"0{index + 1}_CHARACTER_LOD{index}"].objects.link(obj)
        collections[f"0{index + 1}_CHARACTER_LOD{index}"].hide_render = True
        collections[f"0{index + 1}_CHARACTER_LOD{index}"].hide_viewport = True
    ctrl.hide_render = True; rig.hide_render = True
    ctrl["Team"] = 0
    ctrl.id_properties_ui("Team").update(min=0, max=1, description="0 cyan / I, 1 amber / II; runtime also changes the outline icon")
    accent = materials[M['M_Accent']]
    driver = accent.node_tree.nodes["TeamTint"].inputs[2].driver_add("default_value", 0).driver
    driver.expression = ".025 + .72 * team"
    var = driver.variables.new(); var.name = "team"; var.targets[0].id = ctrl; var.targets[0].data_path = '["Team"]'
    for component, expression in ((1, ".56 - .31 * team"), (2, ".74 - .64 * team")):
        d = accent.node_tree.nodes["TeamTint"].inputs[2].driver_add("default_value", component).driver; d.expression = expression
        v = d.variables.new(); v.name = "team"; v.targets[0].id = ctrl; v.targets[0].data_path = '["Team"]'
    scene["asset_title"] = "MORPHRIG / Operative"
    scene["source_units"] = "meters; Z up; forward -Y; anatomical left +X; ground origin (0,0,0)"
    scene["height_m"] = 1.80
    scene["forward_convention"] = "Blender forward -Y. Unreal import documented in skeleton_and_sockets.json."
    scene["fps"] = 30
    scene["team_variants"] = "Cyan / I and Amber / II; same mesh and skeleton"
    scene["authorship"] = "Original procedural character geometry, face, costume, props, weights and motion; no stock body/head or animation."
    scene.world.color = (.06, .06, .06)
    # Open in an immediately useful close/full-body material view.
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                area.spaces.active.region_3d.view_distance = 2.9
                area.spaces.active.region_3d.view_location = V(0, 0, .98)
                area.spaces.active.region_3d.view_rotation = Quaternion(V(1, 0, 0), pi / 2) @ Quaternion(V(0, 0, 1), pi)
                area.spaces.active.shading.type = 'MATERIAL'
    bpy.ops.object.select_all(action='DESELECT')
    ctrl.select_set(True); bpy.context.view_layer.objects.active = ctrl
    embed_controls()
    # Stage is only for inspection, never part of the exported character.
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, -.005))
    plane = bpy.context.object; plane.name = "Inspection_Ground"
    for c in list(plane.users_collection): c.objects.unlink(plane)
    collections["06_STAGE"].objects.link(plane)
    mat = bpy.data.materials.new("Inspection_Floor"); mat.diffuse_color = (.075, .09, .10, 1); plane.data.materials.append(mat)
    for location, power, size in [((1, -2, 3), 600, 3), ((-2, -1, 2), 350, 2), ((0, 2, 2.6), 500, 2)]:
        data = bpy.data.lights.new("Inspection_Light", 'AREA'); data.energy = power; data.shape = 'DISK'; data.size = size
        obj = bpy.data.objects.new("Inspection_Light", data); collections["06_STAGE"].objects.link(obj); obj.location = location
        obj.rotation_euler = (V(0, 0, 1) - obj.location).to_track_quat('-Z', 'Y').to_euler()
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 32
    scene.render.resolution_x = 900; scene.render.resolution_y = 1100; scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = 'AgX'
    scene.frame_set(0)
    # Remove stale source actions on deterministic regeneration.
    for action in list(bpy.data.actions):
        if action.name == "Neutral_Source": bpy.data.actions.remove(action)
    for arm in (ctrl, rig):
        arm.animation_data_create()
        action = bpy.data.actions.new("Neutral_Source" if arm == ctrl else "Neutral_BIND")
        arm.animation_data.action = action; action.use_fake_user = True
    counts = {}
    for i, obj in enumerate(body_lods):
        counts[f"LOD{i}"] = sum(len(p.vertices) - 2 for p in obj.data.polygons) + sum(len(p.vertices) - 2 for p in face.data.polygons) + sum(len(p.vertices) - 2 for p in props.data.polygons)
    report = {"units": "meters", "height_m": 1.8, "bones": len(SPEC), "triangles": counts, "materials": MATERIAL_NAMES, "shape_keys": names if False else json.loads(face['facial_controls']), "max_influences": max(int(o["max_influences"]) for o in (body, face, props)), "uv_sets": 1}
    (ROOT / "docs" / "source_geometry_report.json").write_text(json.dumps(report, indent=2))
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / "source" / "Operative.blend"))
    print("CHARACTER_BUILT", json.dumps(report), flush=True)
    return {"ctrl": ctrl, "rig": rig, "body_lods": body_lods, "face": face, "props": props, "collections": collections, "bones": SPEC}
