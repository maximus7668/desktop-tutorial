"""Limpieza de un modelo dentro de Blender, sin ventana.

Lo lanza el agente «blender»:
  blender --background --factory-startup --python blender_limpiar.py -- '<opciones en JSON>'
Opciones: entrada, salida (.glb), vista (.png, opcional), altura (m), max_caras.
Al terminar escribe una línea «INFORME: {...}» con lo que ha hecho.
"""

import json
import sys

import bmesh
import bpy
from mathutils import Vector


def main() -> None:
    opciones = json.loads(sys.argv[sys.argv.index("--") + 1])
    informe = {}

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=opciones["entrada"])
    escena = bpy.context.scene
    mallas = [o for o in escena.objects if o.type == "MESH"]
    if not mallas:
        raise SystemExit("El archivo no tiene ninguna malla.")
    informe["caras_antes"] = sum(len(o.data.polygons) for o in mallas)
    con_esqueleto = any(o.type == "ARMATURE" for o in escena.objects)

    if con_esqueleto:
        # Con esqueleto no se tocan las transformaciones: se rompería el rig.
        informe["aviso"] = "El modelo ya tiene esqueleto: solo se exporta y se hace la vista previa."
        objetos = mallas
    else:
        malla = _una_sola_malla(mallas)
        _escalar_y_apoyar(malla, opciones.get("altura"), informe)
        _reducir(malla, opciones.get("max_caras"), informe)
        _normales(malla)
        objetos = [malla]

    minimo, maximo = _caja(objetos)
    informe["altura_final"] = round(maximo.z - minimo.z, 4)
    informe["caras_despues"] = sum(len(o.data.polygons) for o in objetos)

    bpy.ops.export_scene.gltf(filepath=opciones["salida"], export_format="GLB", export_apply=True)
    if opciones.get("vista"):
        _vista_previa(objetos, opciones["vista"])
    print("INFORME: " + json.dumps(informe))


def _una_sola_malla(mallas):
    bpy.ops.object.select_all(action="DESELECT")
    for o in mallas:
        o.select_set(True)
    bpy.context.view_layer.objects.active = mallas[0]
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if len(mallas) > 1:
        bpy.ops.object.join()
    malla = bpy.context.view_layer.objects.active
    # Lo que no es malla (nodos vacíos del glTF) ya no hace falta.
    for o in list(bpy.context.scene.objects):
        if o != malla and o.type != "MESH":
            bpy.data.objects.remove(o, do_unlink=True)
    return malla


def _escalar_y_apoyar(malla, altura, informe):
    minimo, maximo = _caja([malla])
    alto = maximo.z - minimo.z
    informe["altura_original"] = round(alto, 4)
    if altura and alto > 0:
        factor = float(altura) / alto
        malla.scale = (factor, factor, factor)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        informe["escala"] = round(factor, 4)
    minimo, maximo = _caja([malla])
    centro = (minimo + maximo) / 2
    # Origen entre los pies: centrado en planta y apoyado en el suelo.
    malla.location = (-centro.x, -centro.y, -minimo.z)
    bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)


def _reducir(malla, max_caras, informe):
    caras = len(malla.data.polygons)
    if not max_caras or caras <= max_caras:
        return
    modificador = malla.modifiers.new("Reducir", "DECIMATE")
    modificador.ratio = max_caras / caras
    bpy.ops.object.modifier_apply(modifier=modificador.name)
    informe["reducido"] = True


def _normales(malla):
    bm = bmesh.new()
    bm.from_mesh(malla.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(malla.data)
    bm.free()


def _caja(objetos):
    puntos = [o.matrix_world @ Vector(esquina) for o in objetos for esquina in o.bound_box]
    minimo = Vector((min(p.x for p in puntos), min(p.y for p in puntos), min(p.z for p in puntos)))
    maximo = Vector((max(p.x for p in puntos), max(p.y for p in puntos), max(p.z for p in puntos)))
    return minimo, maximo


def _vista_previa(objetos, ruta):
    """Render rápido de tres cuartos con Cycles en la CPU: funciona en cualquier PC."""
    escena = bpy.context.scene
    minimo, maximo = _caja(objetos)
    centro = (minimo + maximo) / 2
    tamano = max((maximo - minimo).length, 0.01)

    escena.render.engine = "CYCLES"
    escena.cycles.device = "CPU"
    escena.cycles.samples = 24
    escena.cycles.use_denoising = False
    escena.render.resolution_x = 640
    escena.render.resolution_y = 640
    escena.render.image_settings.file_format = "PNG"

    mundo = bpy.data.worlds.new("Fondo")
    escena.world = mundo
    if mundo.node_tree is None:
        mundo.use_nodes = True
    fondo = mundo.node_tree.nodes.get("Background")
    if fondo is not None:
        fondo.inputs[0].default_value = (0.82, 0.86, 0.95, 1.0)
        fondo.inputs[1].default_value = 0.9

    sol = bpy.data.objects.new("Sol", bpy.data.lights.new("Sol", "SUN"))
    sol.data.energy = 3.0
    sol.rotation_euler = (0.9, 0.2, 0.8)
    escena.collection.objects.link(sol)

    camara = bpy.data.objects.new("Camara", bpy.data.cameras.new("Camara"))
    escena.collection.objects.link(camara)
    # De frente es -Y en Blender (el +Z del glTF): cámara de tres cuartos por delante.
    camara.location = centro + Vector((tamano * 0.9, -tamano * 1.5, tamano * 0.35))
    camara.rotation_euler = (centro - camara.location).to_track_quat("-Z", "Y").to_euler()
    escena.camera = camara

    escena.render.filepath = ruta
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
