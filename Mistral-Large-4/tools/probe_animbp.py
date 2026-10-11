import unreal, traceback

def p(*a):
    print("PROBE7", *a)

bp = unreal.load_asset("/Game/Pilot/ABP_Probe5")
graphs = bp.get_animation_graphs()
g = graphs[0]
inner = unreal.load_asset(str(g).split("'")[1]) if False else None
# graphs[0] is an Object; get the actual graph object
gobj = g
p("gobj", gobj, type(gobj).__name__)
methods = sorted([m for m in dir(gobj) if not m.startswith('_')])
p("GMETHODS", methods)
for attr in ["nodes", "Nodes", "root_node", "RootNode", "graph_node_root", "schema", "Schema", "children", "sub_graphs", "SubGraphs", "all_nodes", "AllNodes"]:
    try:
        v = gobj.get_editor_property(attr)
        p("EATTR", attr, "->", type(v).__name__ if v is not None else None, (len(v) if hasattr(v, '__len__') else v))
    except Exception as e:
        p("EATTR", attr, "FAIL", repr(e))
try:
    nodes = gobj.get_editor_property("nodes")
    p("NODES", [(n.get_name(), type(n).__name__) for n in nodes])
    for n in nodes:
        p("NODE", n.get_name(), type(n).__name__, "props", sorted([m for m in dir(n) if not m.startswith('_')])[:80])
        pins = n.get_editor_property("pins")
        p("  PINS", [(pp.get_name(), str(pp.get_editor_property("direction"))) for pp in pins])
        pp0 = pins[0]
        p("  PINPROPS", sorted([m for m in dir(pp0) if not m.startswith('_')]))
        p("  PINCLASS", type(pp0).__name__)
except Exception:
    traceback.print_exc()
print("PROBE7_DONE")
