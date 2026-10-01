"""
blender_terrain.py
---------------------
Builds the CM DSM mesh and applies the prepared orthomosaic texture.

COMO USAR:
1. Rode "web/prepare_site_data.py" fora do Blender (Python com rasterio).
2. Abra o Blender > aba "Scripting".
3. Abra este arquivo (ou cole o conteúdo) no editor de texto do Blender.
4. Ajuste as variáveis em "CONFIGURAÇÃO" abaixo se quiser (caminho dos
   arquivos, nível de detalhe, exagero vertical etc.).
5. Clique em "Run Script" (▶).

Execute prepare_site_data.py antes deste script. O GLB resultante e salvo
em data/terreno_cm.glb.
"""

import json
import os

import bmesh
import bpy
import numpy as np

# ---------------------------------------------------------------------------
# CONFIGURAÇÃO
# ---------------------------------------------------------------------------
# Dados otimizados pelo prepare_site_data.py
WEB_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(WEB_DIR, "data")
NPY_PATH = os.path.join(DATA_PATH, "dsm_cm.npy")
JSON_PATH = os.path.join(DATA_PATH, "dsm_cm.json")
MOSAIC_PATH = os.path.join(DATA_PATH, "mosaico.webp")
GLB_PATH = os.path.join(DATA_PATH, "terreno_cm.glb")

# STEP = 1 usa todos os pixels; aumente para reduzir a malha.
# Aumente para reduzir o número de vértices (mais leve/rápido no viewport).
STEP = 5

# Exagero vertical para tornar o relevo sutil legível no celular.
Z_EXAGGERATION = 2.0

# Se True, centraliza o objeto na origem do mundo (recomendado, já que as
# coordenadas UTM originais são números grandes, ex.: 235726, 9205324).
CENTER_ON_ORIGIN = True

OBJECT_NAME = "Terreno_CM"

# ---------------------------------------------------------------------------
# Carrega dados
# ---------------------------------------------------------------------------
with open(JSON_PATH, "r", encoding="utf-8") as f:
    meta = json.load(f)

if "mosaic" not in meta:
    raise RuntimeError(
        "Metadados do mosaico ausentes. Rode prepare_site_data.py novamente "
        "fora do Blender."
    )

data = np.load(NPY_PATH)  # shape (height, width), NaN = sem dado
mosaic_meta = meta["mosaic"]

res_x = meta["res_x"]
res_y = meta["res_y"]  # negativo
origin_x = meta["origin_x"]
origin_y = meta["origin_y"]
z_min = meta["z_min"]

# Downsample (amostragem) conforme STEP
data_ds = data[::STEP, ::STEP]
rows, cols = data_ds.shape

# ---------------------------------------------------------------------------
# Remove objeto antigo com mesmo nome (se existir)
# ---------------------------------------------------------------------------
for old_name in (OBJECT_NAME, "Terreno_Mari1", "Terreno_Creche"):
    old_obj = bpy.data.objects.get(old_name)
    if old_obj is not None:
        bpy.data.objects.remove(old_obj, do_unlink=True)

    old_mesh = bpy.data.meshes.get(old_name)
    if old_mesh is not None:
        bpy.data.meshes.remove(old_mesh)

# ---------------------------------------------------------------------------
# Construção da malha
# ---------------------------------------------------------------------------
mesh = bpy.data.meshes.new(OBJECT_NAME)
bm = bmesh.new()

# Offset para centralizar (calculado a partir do centro da área amostrada)
if CENTER_ON_ORIGIN:
    offset_x = origin_x + (cols * STEP * res_x) / 2.0
    offset_y = origin_y + (rows * STEP * res_y) / 2.0
    offset_z = z_min
else:
    offset_x = 0.0
    offset_y = 0.0
    offset_z = 0.0

valid_mask = ~np.isnan(data_ds)

# Cria um vértice para cada célula da grade (mesmo as inválidas, para manter
# o índice alinhado); vértices inválidos ficam no plano z_min e não entram
# em nenhuma face.
verts = np.empty((rows, cols), dtype=object)
for r in range(rows):
    real_y = origin_y + (r * STEP) * res_y - offset_y
    for c in range(cols):
        real_x = origin_x + (c * STEP) * res_x - offset_x
        if valid_mask[r, c]:
            real_z = (data_ds[r, c] - offset_z) * Z_EXAGGERATION
        else:
            real_z = 0.0
        verts[r, c] = bm.verts.new((real_x, real_y, real_z))

bm.verts.ensure_lookup_table()

# Cria faces somente onde os 4 cantos são válidos (preserva o contorno real
# do levantamento, sem "esticar" o terreno sobre áreas sem dado).
face_count = 0
for r in range(rows - 1):
    for c in range(cols - 1):
        if (
            valid_mask[r, c]
            and valid_mask[r, c + 1]
            and valid_mask[r + 1, c]
            and valid_mask[r + 1, c + 1]
        ):
            v1 = verts[r, c]
            v2 = verts[r, c + 1]
            v3 = verts[r + 1, c + 1]
            v4 = verts[r + 1, c]
            try:
                bm.faces.new((v1, v4, v3, v2))
                face_count += 1
            except ValueError:
                # Face duplicada (não deveria ocorrer nesta grade regular)
                pass

# Remove vértices que não formaram nenhuma face (ficaram "soltos")
loose_verts = [v for v in bm.verts if not v.link_faces]
bmesh.ops.delete(bm, geom=loose_verts, context="VERTS")

bm.normal_update()
bm.to_mesh(mesh)
bm.free()

mesh.update()

obj = bpy.data.objects.new(OBJECT_NAME, mesh)
bpy.context.collection.objects.link(obj)

# UV coordinates use the mosaic's georeferenced bounds, which can differ
# from the DTM bounds.
mosaic_south = mosaic_meta["origin_y"] + mosaic_meta["height"] * mosaic_meta["res_y"]
mosaic_width = mosaic_meta["width"] * mosaic_meta["res_x"]
mosaic_height = -mosaic_meta["height"] * mosaic_meta["res_y"]
uv_layer = mesh.uv_layers.new(name="MosaicoUV")
for polygon in mesh.polygons:
    for loop_index in polygon.loop_indices:
        vertex = mesh.vertices[mesh.loops[loop_index].vertex_index]
        world_x = vertex.co.x + offset_x
        world_y = vertex.co.y + offset_y
        uv_layer.data[loop_index].uv = (
            (world_x - mosaic_meta["origin_x"]) / mosaic_width,
            (world_y - mosaic_south) / mosaic_height,
        )

# Apply the aerial mosaic as a georeferenced image texture.
image = bpy.data.images.load(MOSAIC_PATH, check_existing=True)
image.pack()
material = bpy.data.materials.new(name="Material_Mosaico_CM")
material.use_nodes = True
nodes = material.node_tree.nodes
nodes.clear()
output_node = nodes.new("ShaderNodeOutputMaterial")
shader_node = nodes.new("ShaderNodeBsdfPrincipled")
uv_node = nodes.new("ShaderNodeUVMap")
uv_node.uv_map = uv_layer.name
image_node = nodes.new("ShaderNodeTexImage")
image_node.image = image
image_node.extension = "CLIP"
material.node_tree.links.new(uv_node.outputs["UV"], image_node.inputs["Vector"])
material.node_tree.links.new(
    image_node.outputs["Color"], shader_node.inputs["Base Color"]
)
material.node_tree.links.new(
    image_node.outputs["Alpha"], shader_node.inputs["Alpha"]
)
material.node_tree.links.new(shader_node.outputs["BSDF"], output_node.inputs["Surface"])
material.diffuse_color = (1.0, 1.0, 1.0, 1.0)
if hasattr(material, "surface_render_method"):
    material.surface_render_method = "DITHERED"
elif hasattr(material, "blend_method"):
    material.blend_method = "HASHED"
obj.data.materials.append(material)

# Emission keeps the orthomosaic readable regardless of scene lighting.
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type == "VIEW_3D":
            space = area.spaces.active
            space.shading.type = "MATERIAL"
            space.overlay.show_overlays = False
            space.region_3d.view_location = (
                0.0,
                0.0,
                (meta["z_max"] - z_min) * Z_EXAGGERATION / 2.0,
            )
            space.region_3d.view_distance = max(
                meta["width"] * abs(res_x),
                meta["height"] * abs(res_y),
            ) * 1.5

# Sombreamento suave
for poly in mesh.polygons:
    poly.use_smooth = True

bpy.context.view_layer.objects.active = obj
obj.select_set(True)

# Export only the terrain; GLB embeds the packed orthomosaic image.
os.makedirs(WEB_DIR, exist_ok=True)
bpy.ops.object.select_all(action="DESELECT")
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
bpy.ops.export_scene.gltf(
    filepath=GLB_PATH,
    export_format="GLB",
    use_selection=True,
    export_apply=True,
)

print(f"Malha '{OBJECT_NAME}' criada: {len(mesh.vertices)} vértices, {face_count} faces.")
print(f"Grade amostrada: {rows} x {cols} (STEP={STEP})")
print(f"Elevação original: min={meta['z_min']:.2f} m, max={meta['z_max']:.2f} m")
print(f"Mosaico aplicado: {image.name} ({image.size[0]} x {image.size[1]} px)")
print(f"Modelo web exportado: {GLB_PATH}")
