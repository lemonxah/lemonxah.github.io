<!-- Copied from docs/importing-megascans-fab.md in the engine repository by sync.py. Edit it there, then run ./sync.py. -->

# Importing Megascans / Fab assets and recognising MetaHuman packages (IMP-8)

ZestEngine does not download anything and there is no public Fab API. You download a pack yourself (from
https://www.fab.com, Quixel Bridge, Sketchfab, a marketplace, ...), then import the folder or the `.zip`. The importer
only reads your files and writes native assets into your project. Nothing is bundled and no Quixel or Epic code is used.

Code: `zestengine-assets/src/{pack_zip,tex_roles,megascans,pack_scan,pack_convert,mhpkg}.rs`, editor
`zestengine-engine/src/pack_import_ui.rs`. Modelled on the Unity package converter (`unity_package.rs`,
`unity_convert.rs`, `docs/shaders-unity-compat.md`): detect, parse, convert, report what could not be mapped.

## Using it

- Files panel: Create menu (empty area, or the Create button) > `Import Megascans / Fab Asset...`; or right-click a folder,
  `.zip` or `.mhpkg` > `Import Megascans / Fab Asset...`; or drop a folder / `.zip` / `.mhpkg` from the file manager onto
  the panel.
- The dialog scans (a zip is extracted to a temp folder first, with size limits) and lists the assets it found. Pick a
  type (3D asset, plant, surface, atlas, decal, imperfection, brush), check the texture roles (every row has a dropdown;
  a "guessed" badge marks short names like `_N`), set the real-world size of tiling surfaces, the target folder (default
  `megascans`), the texture size cap and what to do if the folder already exists. `Import` runs as a task with progress.
- `Browse on Fab` opens https://www.fab.com in your browser. `Watch the Downloads folder` (off by default) lists
  `~/Downloads` every 3 seconds and offers to import a new `.zip` / `.mhpkg` / folder once it has stopped growing. No network.

## What a Megascans export looks like (checked against 82 real Fab downloads)

One folder per asset id (5-12 lowercase letters / digits, e.g. `xb5ebhf`):

- Models: `<id>.fbx`, or `<id>_VarA_LOD0.fbx`, `<id>_VarB_LOD0.fbx`, ... (`_LODn` numbering is read numerically, so LOD10
  sorts after LOD2).
- Textures: `<id>_<res>_<Role>.jpg` with `Albedo` or `BaseColor`/`Basecolor`, `Normal`, `Roughness`, `Gloss`, `AO`,
  `Cavity`, `Bump`, `Displacement`, `Specular`, `Opacity`, `Translucency`, `Metalness`, `Fuzz`, and packed
  `ORM` / `Occlusion-Roughness-Metallic`; plants add `<id>_8K_Billboard_<Role>.jpg`.
- Fab downloads carry no JSON. Quixel Bridge exports carry `<id>.json`, read leniently (every field optional, unknown
  fields ignored, numbers may be strings): `semanticTags.asset_type` / `categories[0]` for the type, `semanticTags.name`,
  `meta[]` with `scanArea` (`2x2`, `2 x 2 m`, `50 cm`) for the real-world size, `meshes[].uris[].lod`, `maps[]`. The JSON
  schema is from the documentation; no export JSON was on the development machine, so it is untested against a real one.

Without JSON the type is inferred: a mesh with billboard maps, or with opacity and translucency, is a plant; a mesh is a
3D asset; textures only is a surface. Change it in the dialog if that is wrong.

## Conversion table

| Source | Result |
|---|---|
| LOD0..n meshes of a variant | Model files copied with `.meta`; one `.prefab` per variant; a LOD Group (by screen size, 0.30, 0.12, 0.048, ... then 0) over the provided LOD files when the model is a single part. Several parts: the files are copied, the automatic LOD chain applies (reported). One LOD only: automatic chain and octahedral impostor |
| Albedo / BaseColor | Albedo slot, sRGB, BC7, mips |
| Normal | Normal slot. Megascans, glTF and Substance default normals are OpenGL (Y+), which is the engine's convention: used as they are. DirectX maps (`_DX`, `_Normal_DirectX`, Unreal `T_*_N`) get `flip_green` set on the texture import |
| Roughness | Roughness slot (single channel, BC4) |
| Gloss / smoothness | Roughness slot with `roughness_invert` (no pixels touched); a Roughness map wins if both exist |
| Metalness / Metallic | Metallic slot; no map means dielectric (metallic 0) |
| AO | Occlusion slot |
| ORM / Occlusion-Roughness-Metallic / ARM | ORM slot as it is (R occlusion, G roughness, B metallic) |
| RMA, glTF metal-rough, Unity metal-gloss and mask map | Repacked into an ORM PNG (channel picks and inversion in `tex_roles::orm_layout`), missing channels filled from separate maps, size capped |
| Displacement / Height | Displacement slot, parallax occlusion strength 0.03 (Approx) |
| Bump | Only a stand-in for height on surfaces and imperfections when there is no displacement; ignored otherwise |
| Opacity | Opacity slot, alpha clip at 0.5, mips keep alpha coverage |
| Plants, atlases, opacity + translucency | Two-sided |
| Translucency, Fuzz | Reported as unsupported (no thin-translucency or sheen term in the standard shader yet) |
| Specular, Cavity | Reported, not used |
| Billboard maps | Skipped: the engine builds its own octahedral impostor for distant meshes |
| Surface, imperfection | Material only; tiling = 1 / real-world size in metres on albedo, normal and ORM (one UV unit = one metre). Size unknown: tiling 1 and a note |
| Decal | Albedo + opacity composed into one RGBA texture on a Decal Projector prefab sized from the scan area; the decal's normal / roughness / height maps are reported as not projected |
| Atlas | Cut-out two-sided material; no slicing into elements |
| Brush | Textures copied as single-channel; no brush asset type exists |

Textures are copied as they are (no recompression). Import settings are written per map: sRGB for albedo and emission,
linear for the rest, normal-map kind (BC5), single-channel kind (BC4) for roughness / metallic / AO / opacity / height,
BC7 for packed data, mips on, `max_size` from the dialog (default 4096; with only 8K files the 8K file is copied and
downscaled by the texture pipeline).

Output, per asset, under `<target>/<asset>/`: `models/`, `textures/`, `<set>.material`, `<variant>.prefab`,
`import_report.txt` (mapped / approximated / unsupported / notes). If the folder exists: keep both (`name_2`), skip, or
overwrite same-named files (existing `.meta` ids are kept so references hold).

## Fab and other downloads

Any folder or zip with FBX / glTF models (OBJ, USD, Alembic, Blender and Max files are listed as unsupported) and textures.
Textures are classified from the end of the file name (resolution tokens like `4K` and `2048` removed):

- Megascans: `Albedo, Basecolor, Normal, Roughness, Gloss, AO, Displacement, Opacity, Translucency, Specular, Cavity, Bump, Metalness, Fuzz`
- Unreal: `T_Name_BaseColor`, `_ORM`, `_N` (DirectX), `_D`, `_E`
- Substance / Sketchfab: `_Base_color`, `_Normal_OpenGL`, `_Normal_DirectX`, `_Roughness`, `_Metallic`, `_Height`, `_AO`, `_Emissive`
- glTF: `_baseColor`, `_metallicRoughness`, `_normal`, `_occlusion`, `_emissive`
- Unity: `_MainTex`, `_BumpMap` (a normal map), `_MetallicGlossMap`, `_OcclusionMap`, `_MaskMap`

What is left of the name is the material prefix: textures with the same prefix make one material, matched to the model's
material names (equal, then contains, then the only set). Names with no readable role go to an `Unsorted` set with role
`Ignore`; give them a role in the dialog. UDIM tiles (`.1001`) are recognised in the name but only the tile files you
select roles for are used; TIFF / PSD / DDS textures are reported as unreadable (convert to png or jpg).

## MetaHuman packages (`.mhpkg`)

Recognised only. The file is a stored zip with `Manifest.json`, `FileList.json` and Unreal `.uasset` files. The dialog shows
the asset name and type (`Character`, `Outfit`, ...), engine version, object path, size, dependent packages, the file list,
and what the manifest counters say it contains (LODs and vertex count, materials, grooms and strands, clothing, physics,
hair cards). It then explains how to get usable content: in Unreal Engine open it with the MetaHuman plugin, export the
skeletal mesh as FBX (all LODs and the skeleton) and each texture as PNG / TGA via `Asset Actions > Export`, grooms only
export as Alembic (not read, use the hair cards), then import that folder with this dialog. `Open folder` opens the
package's folder. No `.uasset` is parsed. Check the MetaHuman licence terms before using exported content.

Real sample used in the tests (read only): a one-character package `asi20.mhpkg` (Character, Unreal 5.8, 4 `.uasset`
files, counters all zero because it only holds head textures).

## Safety

Archives are untrusted. `pack_zip.rs` rejects `..`, absolute and drive paths and backslash tricks, skips symlinks,
encrypted and repeated (also case-only different) names, limits entries (50 000), a single entry (4 GiB), the total
(24 GiB) and the compression ratio (1000x for entries over 1 MiB), and counts the bytes actually written rather than
trusting the header. Folder scans never follow symlinks and stop at 100 000 files.

## Not done

- Translucency and fuzz maps have no shader term; they are reported (`Not supported yet`) and dropped.
- Atlases are not sliced; displacement scale is a fixed default, the JSON min / max intensity is not read.
- A LOD Group is only wired for single-part models.
- The watcher's on/off state is not saved between sessions.
- Visual results (how a converted material and the dialog look) were not checked in a running editor.
