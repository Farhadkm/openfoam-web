from __future__ import annotations

import os
import json
from collections import OrderedDict
from pathlib import Path
import traceback
import asyncio

import vtkmodules.vtkRenderingOpenGL2  # noqa: F401 (VTK factory init)
from vtkmodules.vtkCommonDataModel import vtkDataObject
from vtkmodules.vtkFiltersCore import vtkTubeFilter, vtkVectorNorm
from vtkmodules.vtkFiltersModeling import vtkOutlineFilter
from vtkmodules.vtkFiltersSources import vtkPointSource
from vtkmodules.vtkIOXML import vtkXMLGenericDataObjectReader
from vtkmodules.vtkIOLegacy import vtkGenericDataObjectReader
from vtkmodules.vtkRenderingCore import vtkActor, vtkDataSetMapper, vtkRenderer, vtkRenderWindow
from vtkmodules.vtkFiltersFlowPaths import vtkStreamTracer
from vtkmodules.vtkCommonMath import vtkRungeKutta4

from aiohttp import web

from trame.app import get_server
from trame.ui.vuetify3 import VAppLayout
from trame.widgets import html, vtk, vuetify3
from trame_vtk.modules import vtk as vtk_module


JOBS_ROOT = Path(os.environ.get("JOBS_ROOT", "/jobs")).resolve()
# Default extra delay (seconds) between frames during Play; also the initial `play_interval_sec`
# (overridable from the job toolbar). Actual sleep is max(VIEWER_PLAY_MIN_INTERVAL, play_interval_sec).
VIEWER_PLAY_INTERVAL = max(0.0, float(os.environ.get("VIEWER_PLAY_INTERVAL", "0")))
# Floor for that sleep. Must be >0 so the event loop can drain WebSocket buffers
# and process incoming messages (like Pause). Too low = buffer overflow → connection death.
VIEWER_PLAY_MIN_INTERVAL = max(0.25, float(os.environ.get("VIEWER_PLAY_MIN_INTERVAL", "0.25")))
# When only VTK time changes, keep the camera (faster + less jumpy during Play).
_camera_reset_key: tuple[str, str, str] | None = None
# Client-side geometry cache namespace (VtkLocalView contextName): stable across time steps.
_vtk_ns_key: tuple[str, str, str] | None = None
# Server-side LRU of path -> vtkDataObject (0 disables). Revisiting a time skips disk read only.
VIEWER_VTK_DATASET_CACHE = max(0, int(os.environ.get("VIEWER_VTK_DATASET_CACHE", "24")))
_dataset_cache: OrderedDict[str, vtkDataObject] = OrderedDict()
_dataset_cache_job: str | None = None


def _openfoam_case_root(extract_dir: Path) -> Path:
    """ZIP extract root may wrap the case (e.g. DPMFoam/Goldschmidt). Prefer root if it is the case."""
    if not extract_dir.is_dir():
        return extract_dir
    if (extract_dir / "system" / "controlDict").is_file():
        return extract_dir
    candidates: list[tuple[int, Path]] = []
    try:
        for p in extract_dir.rglob("controlDict"):
            if p.parent.name != "system" or not p.is_file():
                continue
            root = p.parent.parent
            try:
                depth = len(root.relative_to(extract_dir).parts)
            except ValueError:
                continue
            candidates.append((depth, root))
    except OSError:
        return extract_dir
    if not candidates:
        return extract_dir
    candidates.sort(key=lambda x: (x[0], str(x[1])))
    return candidates[0][1]


def _safe_job_id(raw: str) -> str:
    if not raw or ".." in raw or "/" in raw or "\\" in raw:
        return ""
    return raw


def _list_times(case_dir: Path) -> list[str]:
    if not case_dir.is_dir():
        return []
    of_root = _openfoam_case_root(case_dir)
    # OpenFOAM foamToVTK outputs are usually under <case>/VTK/
    vtk_dir = of_root / "VTK"
    if not vtk_dir.is_dir():
        return []

    # If VTK has per-region outputs (foamToVTK -allRegions), we list times from the selected region.
    region = (state.region or "").strip()
    if region:
        region_dir = vtk_dir / region
        if region_dir.is_dir():
            folders = [p.name for p in region_dir.iterdir() if p.is_dir() and p.name.startswith("case_")]
            folders.sort(key=lambda s: float(s.split("_", 1)[1]) if "_" in s else 0.0)
            # map time string -> folder name (case_200)
            state.time_to_folder = {f.split("_", 1)[1] if "_" in f else f: f for f in folders}
            return sorted(state.time_to_folder.keys(), key=lambda s: float(s))

    # Prefer ParaView-style series file if available: case.vtm.series
    series = vtk_dir / "case.vtm.series"
    if series.is_file():
        try:
            data = json.loads(series.read_text(encoding="utf-8", errors="replace"))
            files = data.get("files", [])
            # Store mapping time -> folder prefix (case_XX)
            mapping = {}
            for f in files:
                name = f.get("name", "")
                t = f.get("time", None)
                if not isinstance(name, str) or t is None:
                    continue
                # name is like case_17.vtm -> folder is case_17
                stem = name.rsplit(".", 1)[0]
                mapping[str(t)] = stem
            state.time_to_folder = mapping
            # return sorted times as strings
            times = sorted(mapping.keys(), key=lambda s: float(s))
            return times
        except Exception:
            pass

    # Fallback: list case_* folders
    folders = [p.name for p in vtk_dir.iterdir() if p.is_dir() and p.name.startswith("case_")]
    folders.sort()
    state.time_to_folder = {f: f for f in folders}
    return folders


def _list_vtk_files(case_dir: Path, time: str) -> list[str]:
    of_root = _openfoam_case_root(case_dir)
    vtk_dir = of_root / "VTK"
    if not vtk_dir.is_dir():
        return []
    folder = (state.time_to_folder or {}).get(time, time)
    if state.region:
        vtk_time = vtk_dir / state.region / folder
    else:
        vtk_time = vtk_dir / folder
    if not vtk_time.is_dir():
        return []
    out: list[str] = []
    internal = vtk_time / "internal.vtu"
    if internal.is_file():
        out.append("internal.vtu")
    boundary = vtk_time / "boundary"
    if boundary.is_dir():
        for p in boundary.iterdir():
            if p.is_file() and p.name.lower().endswith(".vtp"):
                out.append(f"boundary/{p.name}")
    return out


def _pick_scalar(preferred: str, scalars: list[str]) -> str:
    """Resolve coloring when the exact key is missing (common across VTK time steps).

    foamToVTK may attach the same physical field on point data at one time and cell data
    at another, or omit optional arrays at t=0. Without this, Play resets to solid color.
    """
    if not scalars:
        return "Solid Color"
    pref = (preferred or "").strip()
    if pref in scalars:
        return pref
    if pref in ("", "Solid Color"):
        return "Solid Color"
    if ":" not in pref:
        return "Solid Color"
    mode, name = pref.split(":", 1)
    name = name.strip()
    if not name:
        return "Solid Color"
    alt_mode = "cell" if mode == "point" else "point"
    alt = f"{alt_mode}:{name}"
    if alt in scalars:
        return alt
    name_lower = name.lower()
    for s in scalars:
        if ":" not in s:
            continue
        _, sn = s.split(":", 1)
        if sn == name or sn.lower() == name_lower:
            return s
    return "Solid Color"


def _read_dataset(path: Path) -> vtkDataObject | None:
    if not path.is_file():
        return None
    suffix = path.suffix.lower()
    if suffix in (".vtp", ".vtu", ".vts", ".vti"):
        r = vtkXMLGenericDataObjectReader()
        r.SetFileName(str(path))
        r.Update()
        return r.GetOutputDataObject(0)
    if suffix == ".vtk":
        r = vtkGenericDataObjectReader()
        r.SetFileName(str(path))
        r.Update()
        return r.GetOutput()
    return None


def _preload_file_bytes(path: Path) -> bytes | None:
    """Read raw file bytes in a thread so the event loop stays responsive for WS pings."""
    try:
        return path.read_bytes()
    except OSError:
        return None


def _dataset_cache_clear_if_new_job(job_id: str) -> None:
    global _dataset_cache_job, _dataset_cache
    if not job_id:
        return
    if _dataset_cache_job != job_id:
        _dataset_cache.clear()
        _dataset_cache_job = job_id


def _dataset_cache_get(path_key: str) -> vtkDataObject | None:
    if VIEWER_VTK_DATASET_CACHE <= 0:
        return None
    got = _dataset_cache.get(path_key)
    if got is not None:
        _dataset_cache.move_to_end(path_key)
    return got


def _dataset_cache_put(path_key: str, obj: vtkDataObject) -> None:
    if VIEWER_VTK_DATASET_CACHE <= 0:
        return
    _dataset_cache[path_key] = obj
    _dataset_cache.move_to_end(path_key)
    while len(_dataset_cache) > VIEWER_VTK_DATASET_CACHE:
        _dataset_cache.popitem(last=False)


def _sync_geometry_namespace(job_id: str) -> None:
    """Trame client uses contextName to namespace vtk.js geometry caches; keep stable while only time changes."""
    global _vtk_ns_key
    if not job_id:
        return
    key = (job_id, str(state.region or ""), str(state.vtk_file or ""))
    if key == _vtk_ns_key:
        return
    _vtk_ns_key = key
    raw = f"{job_id}_{state.region or '_'}_{state.vtk_file or '_'}"
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in raw)[:220]
    state.vtk_cache_ns = safe or "default"


server = get_server("openfoam-trame-viewer")
state, ctrl = server.state, server.controller


def _has_active_client() -> bool:
    """True when at least one wslink WebSocket session is alive."""
    return server.protocol is not None


@ctrl.add("on_server_bind")
def _openfoam_on_server_bind(wslink_server, **_kwargs):
    aio_app = getattr(wslink_server, "app", None)
    if aio_app is None or getattr(aio_app, "_openfoam_routes_done", False):
        return
    aio_app._openfoam_routes_done = True

    async def _noop_paraview(_request):
        return web.Response(status=204)

    async def _serve_fullbleed_js(_request):
        return web.Response(text=_VIZ_FULL_BLEED_JS, content_type="application/javascript")

    async def _serve_bridge_js(_request):
        return web.Response(text=_EMBED_BRIDGE_JS, content_type="application/javascript")

    r = aio_app.router
    r.add_post("/paraview/", _noop_paraview)
    r.add_post("/paraview", _noop_paraview)
    r.add_get("/openfoam-fullbleed.js", _serve_fullbleed_js)
    r.add_get("/openfoam-bridge.js", _serve_bridge_js)


vtk_module.setup(server)

state.jobId = _safe_job_id(os.environ.get("DEFAULT_JOB_ID", ""))
state.vtk_time = ""
state.vtk_file = ""
state.status = "Select a job with VTK outputs."
state.time_to_folder = {}
state.region = ""
state.regions = []
state.times = []
state.files = []
state.scalar = "Solid Color"
state.scalars = ["Solid Color"]
state.vtk_playing = False
state.show_streamlines = False
state.play_interval_sec = VIEWER_PLAY_INTERVAL
state.play_stride = 1.0
state.vtk_cache_ns = "default"
# JSON bridge for parent ↔ Python state (no visible form chrome; VTK only).
state.bridge_json = ""
state.bridge_out_json = "{}"
# Trame client sets trame_error_report_msg on connection close/error, but never
# pre-registers the key. Without a server-side init, the Vue customRef watcher
# doesn't exist and the dirty-state handler throws "n[s[a]] is not a function".
state.trame_error_report_msg = ""

renderer = vtkRenderer()
render_window = vtkRenderWindow()
render_window.AddRenderer(renderer)
# Headless Docker: avoid binding to X11. Off-screen uses OSMesa/EGL when available.
render_window.SetOffScreenRendering(1)

# Use VtkLocalView for browser-side rendering (vtk.js). Important: the widget
# must be created inside the UI/layout context so it can bind to the server/state.
local_view = None
_play_task: asyncio.Task | None = None

# Persistent actor/mapper reused across play-mode frames to avoid full scene
# rebuild on every tick.  Swapping only the mapper's input data means vtk.js
# receives a much smaller delta, eliminating the white-flash problem.
_play_mapper: vtkDataSetMapper | None = None
_play_actor: vtkActor | None = None


def _time_index() -> int:
    try:
        return list(state.times).index(state.vtk_time)
    except Exception:
        return -1


def _advance_time(step: int) -> None:
    times = list(state.times or [])
    if not times:
        return
    i = _time_index()
    if i < 0:
        state.vtk_time = times[-1]
        return
    state.vtk_time = times[(i + step) % len(times)]


def _parse_time_floats(times: list) -> list[float]:
    out: list[float] = []
    for t in times:
        try:
            out.append(float(t))
        except (TypeError, ValueError):
            continue
    return out


def _min_time_gap() -> float:
    nums = _parse_time_floats(list(state.times or []))
    if len(nums) < 2:
        return 1.0
    gaps = [nums[i + 1] - nums[i] for i in range(len(nums) - 1)]
    pos = [g for g in gaps if g > 1e-30]
    return min(pos) if pos else 1.0


def _time_step_choices() -> list[float]:
    """Multiples of the smallest gap between consecutive VTK times (matches frontend)."""
    nums = _parse_time_floats(list(state.times or []))
    if len(nums) < 2:
        return []
    mg = _min_time_gap()
    span = float(nums[-1] - nums[0])
    raw_vals: list[float] = []
    for m in (1, 2, 3, 5, 10, 20, 50, 100):
        raw = m * mg
        if raw > 0 and raw <= span + mg * 0.5:
            steps = round(raw / mg)
            raw_vals.append(float(steps * mg))
    raw_vals.append(float(mg))
    dedup: list[float] = []
    for v in sorted(set(raw_vals)):
        if not dedup or abs(v - dedup[-1]) > 1e-9 * max(abs(v), 1.0):
            dedup.append(v)
    return dedup


def _snap_play_stride_to_choices() -> None:
    choices = _time_step_choices()
    if not choices:
        state.play_stride = float(max(_min_time_gap(), 1e-12))
        return
    try:
        cur = float(state.play_stride)
    except (TypeError, ValueError):
        state.play_stride = choices[0]
        return
    if cur <= 0 or cur < choices[0] * 0.5:
        state.play_stride = choices[0]
        return
    nearest = min(choices, key=lambda c: abs(c - cur))
    state.play_stride = float(nearest)


def _advance_time_play_step(delta: float) -> None:
    """Move vtk_time forward by `delta` in parsed simulation-time units; wrap to first after last."""
    times = list(state.times or [])
    if len(times) < 2 or delta <= 0:
        return
    try:
        cur = float(state.vtk_time)
    except (TypeError, ValueError):
        state.vtk_time = times[0]
        return
    target = cur + float(delta)
    eps = max(1e-30, 1e-9 * max(abs(target), abs(cur), 1.0))
    for t in times:
        try:
            n = float(t)
        except (TypeError, ValueError):
            continue
        if n + eps >= target:
            state.vtk_time = t
            return
    state.vtk_time = times[0]


def _update_lists():
    job_id = _safe_job_id(state.jobId)
    case_dir = JOBS_ROOT / job_id / "case"
    of_root = _openfoam_case_root(case_dir)
    vtk_dir = of_root / "VTK"

    # Detect per-region VTK folders produced by `foamToVTK -allRegions`
    regions: list[str] = []
    if vtk_dir.is_dir():
        for p in vtk_dir.iterdir():
            if not p.is_dir():
                continue
            if p.name.startswith("case_"):
                continue
            # a region folder typically contains case_* subfolders
            if any(c.is_dir() and c.name.startswith("case_") for c in p.iterdir()):
                regions.append(p.name)
    regions.sort()
    state.regions = regions
    if regions and state.region not in regions:
        # default to first region (usually domain0)
        state.region = regions[0]

    times = _list_times(case_dir)
    state.times = times
    if not times:
        state.vtk_time = ""
        state.files = []
        state.vtk_file = ""
        state.status = "No VTK outputs found. Generate them by running `foamToVTK` in the case, then refresh."
        _publish_bridge_state()
        return
    if state.vtk_time not in times:
        state.vtk_time = times[-1]
    files = _list_vtk_files(case_dir, state.vtk_time)
    state.files = files
    if state.vtk_file not in files:
        # prefer internal mesh if present
        pick = next((f for f in files if "internal" in f.lower()), files[0] if files else "")
        state.vtk_file = pick
    _snap_play_stride_to_choices()
    _publish_bridge_state()


def _publish_bridge_state() -> None:
    try:
        snap = {
            "jobId": state.jobId or "",
            "region": state.region or "",
            "time": state.vtk_time or "",
            "file": state.vtk_file or "",
            "scalar": state.scalar or "",
            "playing": bool(state.vtk_playing),
            "show_streamlines": bool(state.show_streamlines),
            "play_interval_sec": float(state.play_interval_sec or 0),
            "play_stride": float(state.play_stride or _min_time_gap()),
            "status": state.status or "",
            "times": list(state.times or []),
            "regions": list(state.regions or []),
            "files": list(state.files or []),
            "scalars": list(state.scalars or []),
        }
        new_json = json.dumps(snap, sort_keys=True)
        if new_json != state.bridge_out_json:
            state.bridge_out_json = new_json
    except Exception:
        pass


def _apply_viewer_patch_dict(patch: dict) -> None:
    if "jobId" in patch and patch["jobId"] is not None:
        state.jobId = _safe_job_id(str(patch["jobId"]))
    if "region" in patch and patch["region"] is not None:
        state.region = str(patch["region"])
    if "time" in patch and patch["time"] is not None:
        state.vtk_time = str(patch["time"])
    if "file" in patch and patch["file"] is not None:
        state.vtk_file = str(patch["file"])
    if "scalar" in patch and patch["scalar"] is not None:
        state.scalar = str(patch["scalar"])
    if "show_streamlines" in patch:
        state.show_streamlines = bool(patch["show_streamlines"])
    if "play_interval_sec" in patch and patch["play_interval_sec"] is not None:
        try:
            state.play_interval_sec = float(patch["play_interval_sec"])
        except (TypeError, ValueError):
            pass
    if "play_stride" in patch and patch["play_stride"] is not None:
        try:
            state.play_stride = float(patch["play_stride"])
            _snap_play_stride_to_choices()
        except (TypeError, ValueError):
            pass
    if "playing" in patch:
        state.vtk_playing = bool(patch["playing"])
    _update_lists()


@ctrl.add("openfoam_bridge_consume_json")
def openfoam_bridge_consume_json(**_):
    _consume_bridge_json((state.bridge_json or "").strip())


@state.change("bridge_json")
def _on_bridge_json_change(bridge_json, **_):
    _consume_bridge_json((bridge_json or "").strip())


def _consume_bridge_json(raw: str) -> None:
    state.bridge_json = ""
    if not raw:
        _publish_bridge_state()
        return
    try:
        patch = json.loads(raw)
    except json.JSONDecodeError:
        state.status = "Invalid JSON for viewer bridge"
        _publish_bridge_state()
        return
    if not isinstance(patch, dict):
        state.status = "Viewer bridge expects a JSON object"
        _publish_bridge_state()
        return
    patch.pop("_ts", None)
    _apply_viewer_patch_dict(patch)
    if bool(patch.get("doLoad")):
        openfoam_vtk_load()
    else:
        _publish_bridge_state()


@state.change("jobId")
def _on_job_change(jobId, **_):
    state.jobId = _safe_job_id(jobId)
    _update_lists()


@state.change("vtk_time")
def _on_time_change(**_):
    _update_lists()

@state.change("region")
def _on_region_change(**_):
    _update_lists()


@ctrl.add("openfoam_refresh_lists")
def openfoam_refresh_lists():
    """Re-scan VTK folders on disk and reload the current scene (not only dropdown lists)."""
    _update_lists()
    if state.vtk_time and state.vtk_file:
        openfoam_vtk_load()


@ctrl.add("openfoam_vtk_load")
def openfoam_vtk_load():
    global _camera_reset_key
    try:
        job_id = _safe_job_id(state.jobId)
        if not job_id:
            state.status = "Invalid job id."
            return
        if not state.vtk_time or not state.vtk_file:
            state.status = "Pick a time and a VTK file."
            return

        case_dir = JOBS_ROOT / job_id / "case"
        of_root = _openfoam_case_root(case_dir)
        folder = (state.time_to_folder or {}).get(state.vtk_time, state.vtk_time)
        if state.region:
            p = of_root / "VTK" / state.region / folder / state.vtk_file
        else:
            p = of_root / "VTK" / folder / state.vtk_file

        _dataset_cache_clear_if_new_job(job_id)
        _sync_geometry_namespace(job_id)

        cache_key = str(p.resolve())
        data = _dataset_cache_get(cache_key)
        if data is None:
            data = _read_dataset(p)
            if data is not None:
                _dataset_cache_put(cache_key, data)
        if data is None:
            state.status = f"Could not read: {p}"
            return

        renderer.RemoveAllViewProps()
        renderer.SetBackground(0.08, 0.09, 0.11)

        # OpenFOAM foamToVTK commonly produces UnstructuredGrid (.vtu). Use a mapper
        # that supports any vtkDataSet (polydata/unstructured/structured...).
        mapper = vtkDataSetMapper()
        mapper.SetInputData(data)  # type: ignore[arg-type]

        actor = vtkActor()
        actor.SetMapper(mapper)

        # Optional: show streamlines if U exists and internal mesh is selected.
        streamline_actor = None
        _has_U_vector = False
        if bool(state.show_streamlines) and state.vtk_file == "internal.vtu":
            try:
                for loc in (data.GetPointData(), data.GetCellData()):  # type: ignore[attr-defined]
                    arr = loc.GetArray("U") if loc else None
                    if arr and arr.GetNumberOfComponents() == 3 and arr.GetNumberOfTuples() > 0:
                        _has_U_vector = True
                        break
            except Exception:
                pass
        if _has_U_vector:
            try:
                # Seed points across the domain bounds
                b = data.GetBounds()  # type: ignore[attr-defined]
                cx = (b[0] + b[1]) * 0.5
                cy = (b[2] + b[3]) * 0.5
                cz = (b[4] + b[5]) * 0.5
                dx = (b[1] - b[0]) * 0.45
                dy = (b[3] - b[2]) * 0.45
                dz = (b[5] - b[4]) * 0.45

                seeds = vtkPointSource()
                seeds.SetCenter(cx, cy, cz)
                seeds.SetRadius(max(dx, dy, dz))
                seeds.SetNumberOfPoints(200)

                tracer = vtkStreamTracer()
                tracer.SetInputData(data)  # type: ignore[arg-type]
                tracer.SetSourceConnection(seeds.GetOutputPort())
                tracer.SetIntegrator(vtkRungeKutta4())
                tracer.SetMaximumPropagation(1e6)
                tracer.SetInitialIntegrationStep(0.01)
                tracer.SetIntegrationDirectionToForward()

                # Tube streamlines for visibility
                tubes = vtkTubeFilter()
                tubes.SetInputConnection(tracer.GetOutputPort())
                tubes.SetRadius(max(dx, dy, dz) * 0.002)
                tubes.SetNumberOfSides(12)

                # Compute velocity magnitude for coloring
                norm = vtkVectorNorm()
                norm.SetInputConnection(tubes.GetOutputPort())
                norm.SetInputArrayToProcess(0, 0, 0, 0, "U")

                s_mapper = vtkDataSetMapper()
                s_mapper.SetInputConnection(norm.GetOutputPort())
                s_mapper.ScalarVisibilityOn()
                s_mapper.SetScalarModeToUsePointFieldData()
                s_mapper.SelectColorArray("U")  # vtkVectorNorm overwrites? keep default if present

                streamline_actor = vtkActor()
                streamline_actor.SetMapper(s_mapper)
                streamline_actor.GetProperty().SetOpacity(1.0)
            except Exception:
                streamline_actor = None

        renderer.AddActor(actor)
        if streamline_actor is not None:
            renderer.AddActor(streamline_actor)

        # Build list of available scalar arrays for coloring.
        scalars: list[str] = ["Solid Color"]
        try:
            pd = data.GetPointData()  # type: ignore[attr-defined]
            for i in range(pd.GetNumberOfArrays()):
                name = pd.GetArrayName(i)
                if name:
                    scalars.append(f"point:{name}")
        except Exception:
            pass
        try:
            cd = data.GetCellData()  # type: ignore[attr-defined]
            for i in range(cd.GetNumberOfArrays()):
                name = cd.GetArrayName(i)
                if name:
                    scalars.append(f"cell:{name}")
        except Exception:
            pass
        state.scalars = scalars
        state.scalar = _pick_scalar(state.scalar, scalars)

        if state.scalar != "Solid Color":
            try:
                mode, name = state.scalar.split(":", 1)
                mapper.ScalarVisibilityOn()
                if mode == "cell":
                    mapper.SetScalarModeToUseCellFieldData()
                    loc = data.GetCellData()  # type: ignore[attr-defined]
                else:
                    mapper.SetScalarModeToUsePointFieldData()
                    loc = data.GetPointData()  # type: ignore[attr-defined]
                mapper.SelectColorArray(name)
                mapper.SetColorModeToMapScalars()
                arr = loc.GetArray(name) if loc else None
                if arr:
                    if arr.GetNumberOfComponents() == 1:
                        mapper.SetScalarRange(arr.GetRange())
                    else:
                        mapper.SetScalarRange(arr.GetRange(-1))
                actor.GetProperty().SetOpacity(1.0)
            except Exception:
                mapper.ScalarVisibilityOff()
                actor.GetProperty().SetColor(0.35, 0.75, 0.95)
                actor.GetProperty().SetOpacity(0.35)
        else:
            mapper.ScalarVisibilityOff()
            actor.GetProperty().SetColor(0.35, 0.75, 0.95)
            actor.GetProperty().SetOpacity(0.35)

        # Outline helps empty-looking scalars but vtkOutlineFilter.Update() costs per timestep.
        # Skip it while Play is running so 10→20→30… advances faster; Pause triggers a full reload.
        if not bool(state.vtk_playing):
            try:
                outline = vtkOutlineFilter()
                outline.SetInputData(data)  # type: ignore[arg-type]
                outline.Update()
                outline_mapper = vtkDataSetMapper()
                outline_mapper.SetInputConnection(outline.GetOutputPort())
                outline_actor = vtkActor()
                outline_actor.SetMapper(outline_mapper)
                outline_actor.GetProperty().SetColor(1.0, 1.0, 1.0)
                outline_actor.GetProperty().SetLineWidth(2.0)
                renderer.AddActor(outline_actor)
            except Exception:
                pass

        camera_key = (job_id, str(state.vtk_file), str(state.region))
        if _camera_reset_key != camera_key:
            renderer.ResetCamera()
            # For quasi-2D cases (one axis much thinner than the others),
            # orient the camera perpendicular to the thin axis so the user
            # sees a clean 2D view instead of a confusing 3D slab.
            try:
                b = data.GetBounds()  # type: ignore[attr-defined]
                spans = [b[1] - b[0], b[3] - b[2], b[5] - b[4]]
                min_span = min(spans)
                max_span = max(spans)
                if max_span > 0 and min_span / max_span < 0.05:
                    thin_axis = spans.index(min_span)
                    cam = renderer.GetActiveCamera()
                    cx = (b[0] + b[1]) * 0.5
                    cy = (b[2] + b[3]) * 0.5
                    cz = (b[4] + b[5]) * 0.5
                    cam.SetFocalPoint(cx, cy, cz)
                    if thin_axis == 2:
                        cam.SetPosition(cx, cy, cz + max_span * 2)
                        cam.SetViewUp(0, 1, 0)
                    elif thin_axis == 1:
                        cam.SetPosition(cx, cy + max_span * 2, cz)
                        cam.SetViewUp(0, 0, 1)
                    else:
                        cam.SetPosition(cx + max_span * 2, cy, cz)
                        cam.SetViewUp(0, 1, 0)
                    cam.ParallelProjectionOn()
                    renderer.ResetCamera()
            except Exception:
                pass
            _camera_reset_key = camera_key

        # Helpful debug info to confirm the dataset isn't empty.
        try:
            n_cells = int(data.GetNumberOfCells())  # type: ignore[attr-defined]
            n_pts = int(data.GetNumberOfPoints())  # type: ignore[attr-defined]
            b = data.GetBounds()  # type: ignore[attr-defined]
            state.status = f"Loaded {state.vtk_file} @ {state.vtk_time} (cells={n_cells}, pts={n_pts}, bounds={tuple(float(x) for x in b)})"
        except Exception:
            state.status = f"Loaded {state.vtk_file} @ {state.vtk_time}"

        # Push geometry/state through the widget (requires active websocket).
        if local_view is not None:
            local_view.update()
        else:
            state.status = "Viewer not ready yet. Refresh the page and try again."
        _publish_bridge_state()
    except Exception as e:
        traceback.print_exc()
        state.status = f"Load failed: {e}"
        _publish_bridge_state()


def _play_fast_load():
    """Optimized frame load for play mode: reuse actor/mapper, only swap data.

    Instead of tearing down the entire scene (RemoveAllViewProps → new mapper →
    new actor → AddActor) every tick, we keep a persistent mapper+actor and just
    call mapper.SetInputData(new_data).  The scene structure stays identical so
    local_view.update() pushes a much smaller delta, eliminating white flashes.
    Falls back to the full openfoam_vtk_load() if anything goes wrong.
    """
    global _play_mapper, _play_actor

    try:
        job_id = _safe_job_id(state.jobId)
        if not job_id or not state.vtk_time or not state.vtk_file:
            return

        case_dir = JOBS_ROOT / job_id / "case"
        of_root = _openfoam_case_root(case_dir)
        folder = (state.time_to_folder or {}).get(state.vtk_time, state.vtk_time)
        if state.region:
            p = of_root / "VTK" / state.region / folder / state.vtk_file
        else:
            p = of_root / "VTK" / folder / state.vtk_file

        _dataset_cache_clear_if_new_job(job_id)
        cache_key = str(p.resolve())
        data = _dataset_cache_get(cache_key)
        if data is None:
            data = _read_dataset(p)
            if data is not None:
                _dataset_cache_put(cache_key, data)
        if data is None:
            openfoam_vtk_load()
            return

        if _play_mapper is None or _play_actor is None:
            openfoam_vtk_load()
            _play_mapper = None
            _play_actor = None
            actors = renderer.GetActors()
            actors.InitTraversal()
            for _ in range(actors.GetNumberOfItems()):
                act = actors.GetNextActor()
                if act is not None:
                    m = act.GetMapper()
                    if isinstance(m, vtkDataSetMapper):
                        _play_mapper = m
                        _play_actor = act
                        break
            return

        _play_mapper.SetInputData(data)

        if state.scalar and state.scalar != "Solid Color":
            try:
                mode, name = state.scalar.split(":", 1)
                if mode == "cell":
                    loc = data.GetCellData()
                else:
                    loc = data.GetPointData()
                arr = loc.GetArray(name) if loc else None
                if arr:
                    if arr.GetNumberOfComponents() == 1:
                        _play_mapper.SetScalarRange(arr.GetRange())
                    else:
                        _play_mapper.SetScalarRange(arr.GetRange(-1))
            except Exception:
                pass

        _play_mapper.Update()

        if local_view is not None:
            local_view.update()
        _publish_bridge_state()
    except Exception:
        traceback.print_exc()
        _play_mapper = None
        _play_actor = None
        openfoam_vtk_load()


# Avoid ctrl names "prev"/"next"/"load"/"refresh" — Trame exposes them on the client where
# they can shadow JS builtins (iterator .next, window load, location.reload, …).
@ctrl.add("step_prev")
def step_prev():
    _advance_time(-1)
    openfoam_vtk_load()


@ctrl.add("step_next")
def step_next():
    _advance_time(1)
    openfoam_vtk_load()


@ctrl.add("openfoam_toggle_play")
def openfoam_toggle_play():
    state.vtk_playing = not bool(state.vtk_playing)
    state.flush()


def _restore_outline_on_pause():
    """Re-add the outline actor after Play stops, without tearing down the scene."""
    if _play_mapper is None:
        return
    try:
        data = _play_mapper.GetInput()
        if data is None:
            return
        outline = vtkOutlineFilter()
        outline.SetInputData(data)
        outline.Update()
        outline_mapper = vtkDataSetMapper()
        outline_mapper.SetInputConnection(outline.GetOutputPort())
        outline_actor = vtkActor()
        outline_actor.SetMapper(outline_mapper)
        outline_actor.GetProperty().SetColor(1.0, 1.0, 1.0)
        outline_actor.GetProperty().SetLineWidth(2.0)
        renderer.AddActor(outline_actor)

        if local_view is not None:
            local_view.update()
        _publish_bridge_state()
    except Exception:
        traceback.print_exc()


@state.change("vtk_playing")
def _on_playing_change(vtk_playing, **_):
    global _play_task, _play_mapper, _play_actor
    if _play_task is not None:
        _play_task.cancel()
        _play_task = None
    if not vtk_playing:
        # Add outline back (skipped during Play for speed) without tearing down the scene.
        # A full RemoveAllViewProps → rebuild would flash white because the browser
        # briefly sees an empty scene.
        _restore_outline_on_pause()
        _play_mapper = None
        _play_actor = None
        return

    async def _runner():
        global _play_mapper, _play_actor
        consecutive_errors = 0
        max_consecutive_errors = 5
        try:
            while bool(state.vtk_playing):
                if not _has_active_client():
                    print("Play stopped: no active WebSocket client")
                    break

                try:
                    delta = float(state.play_stride or 0)
                except (TypeError, ValueError):
                    delta = 0.0
                mg = _min_time_gap()
                if delta <= 0:
                    delta = mg
                _advance_time_play_step(delta)

                try:
                    _play_fast_load()
                    consecutive_errors = 0
                except Exception:
                    consecutive_errors += 1
                    if consecutive_errors >= max_consecutive_errors:
                        print(f"Play stopped: {consecutive_errors} consecutive load errors")
                        break

                # Yield to the event loop so it can:
                #  1. Drain outgoing WebSocket buffers (VTK scene data)
                #  2. Process incoming messages (Pause command from bridge)
                await asyncio.sleep(0.1)

                try:
                    interval = max(
                        VIEWER_PLAY_MIN_INTERVAL,
                        float(state.play_interval_sec or 0),
                    )
                except (TypeError, ValueError):
                    interval = VIEWER_PLAY_MIN_INTERVAL
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            pass
        except Exception:
            traceback.print_exc()
        finally:
            _play_mapper = None
            _play_actor = None
            state.vtk_playing = False
            _publish_bridge_state()

    _play_task = asyncio.create_task(_runner())


@ctrl.add("on_server_ready")
def _on_server_ready(**_kwargs):
    """Re-push the last loaded scene when a new client session connects.

    Without this, a page refresh/reconnect sees a white canvas until the bridge
    JS re-sends the jobId (a race that occasionally loses).
    """
    if state.jobId and state.vtk_time and state.vtk_file:
        try:
            openfoam_vtk_load()
        except Exception:
            traceback.print_exc()


# initial list population (times/files initialized with other state above)
_update_lists()


# VTK-only UI: no app bar or form controls. State is driven by the JSON bridge (postMessage / URL jobId).
_VIZ_FULL_BLEED_JS = r"""
(function () {
  if (document.getElementById("openfoam-viz-fullbleed")) return;
  var st = document.createElement("style");
  st.id = "openfoam-viz-fullbleed";
  st.textContent =
    "html,body,#app,.v-application,.v-application__wrap{height:100%!important;margin:0!important;overflow:hidden!important;}" +
    ".v-main{flex:1 1 auto!important;min-height:0!important;padding:0!important;display:flex!important;flex-direction:column!important;}" +
    ".openfoam-vtk-root{flex:1 1 auto!important;min-height:0!important;width:100%!important;position:relative!important;}";
  document.head.appendChild(st);
})();
"""

_EMBED_BRIDGE_JS = r"""
(function () {
  var lastOut = "";
  var sessionStartMs = Date.now();
  function deferUntilSessionLikelyReady(fn) {
    var minDelay = 900;
    var wait = Math.max(0, minDelay - (Date.now() - sessionStartMs));
    return setTimeout(fn, wait);
  }

  function jobIdFromLocation() {
    try {
      var qs = new URLSearchParams(window.location.search).get("jobId");
      if (qs) return String(qs).trim();
      var raw = String(window.location.hash || "").replace(/^#/, "");
      if (!raw) return "";
      var hp = new URLSearchParams(raw);
      var j = hp.get("jobId");
      if (j) return String(j).trim();
    } catch (e5) {}
    return "";
  }

  function bridgeFieldInput(wrap) {
    if (!wrap || !wrap.querySelector) return null;
    return (
      wrap.querySelector(".v-field__input input") ||
      wrap.querySelector(".v-field__input textarea") ||
      wrap.querySelector("input") ||
      wrap.querySelector("textarea")
    );
  }

  function setBridgeJson(obj) {
    var wrap = document.getElementById("openfoam-bridge-json-in");
    var inp = bridgeFieldInput(wrap);
    if (!inp) return false;
    if (typeof obj === "object" && obj !== null) obj._ts = Date.now();
    var s = typeof obj === "string" ? obj : JSON.stringify(obj);
    try {
      var desc = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value");
      if (desc && desc.set) desc.set.call(inp, s);
      else inp.value = s;
    } catch (e0) {
      inp.value = s;
    }
    inp.dispatchEvent(new Event("input", { bubbles: true }));
    inp.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }

  var applyPollId = null;
  var applyDeferTimerId = null;
  var jobApplied = false;
  function scheduleApply(v, autoLoad) {
    if (applyDeferTimerId) { clearTimeout(applyDeferTimerId); applyDeferTimerId = null; }
    if (applyPollId) { clearInterval(applyPollId); applyPollId = null; }
    jobApplied = false;
    applyDeferTimerId = deferUntilSessionLikelyReady(function () {
      applyDeferTimerId = null;
      if (jobApplied) return;
      var n = 0;
      applyPollId = setInterval(function () {
        n++;
        if (setBridgeJson({ jobId: v, doLoad: !!autoLoad }) || n > 120) {
          clearInterval(applyPollId);
          applyPollId = null;
          jobApplied = true;
        }
      }, 200);
    });
  }

  function clickCmd(cmd) {
    var id =
      cmd === "prev"
        ? "openfoam-cmd-prev"
        : cmd === "next"
          ? "openfoam-cmd-next"
          : cmd === "load"
            ? "openfoam-trame-load-btn"
            : cmd === "toggle_play"
              ? "openfoam-cmd-toggle-play"
              : cmd === "refresh"
                ? "openfoam-cmd-refresh"
                : null;
    var b = id ? document.getElementById(id) : null;
    if (b) b.click();
  }

  function readBridgeOut() {
    var wrap = document.getElementById("openfoam-bridge-json-out");
    var inp = bridgeFieldInput(wrap);
    return inp ? String(inp.value || "") : "";
  }

  function parentTargetOrigin() {
    try {
      var u = new URLSearchParams(window.location.search).get("parentOrigin");
      if (u) return u;
    } catch (e0) {}
    if (window.self !== window.top) return "*";
    return window.location.origin;
  }

  function pollOut() {
    try {
      var cur = readBridgeOut();
      if (!cur || cur === lastOut) return;
      var payload = JSON.parse(cur);
      if (!payload || typeof payload !== "object" || Object.keys(payload).length === 0) {
        lastOut = cur;
        return;
      }
      lastOut = cur;
      if (window.parent && window.parent !== window) {
        window.parent.postMessage(
          { type: "openfoam-trame-state", payload: payload },
          parentTargetOrigin()
        );
      }
    } catch (e) {}
  }

  try {
    var q = jobIdFromLocation();
    if (q) scheduleApply(q, true);
  } catch (e) {}
  setInterval(pollOut, 350);

  window.addEventListener("message", function (ev) {
    try {
      if (!ev.data || typeof ev.data.type !== "string") return;
      if (ev.data.type === "openfoam-trame-set-job") {
        var j = String(ev.data.jobId || "").trim();
        if (!j) return;
        scheduleApply(j, !!ev.data.autoLoad);
        return;
      }
      if (ev.data.type === "openfoam-trame-patch-state") {
        var p = ev.data.patch || {};
        if (typeof p !== "object") return;
        deferUntilSessionLikelyReady(function () {
          setBridgeJson(p);
        });
        return;
      }
      if (ev.data.type === "openfoam-trame-cmd") {
        deferUntilSessionLikelyReady(function () {
          clickCmd(String(ev.data.cmd || ""));
        });
        return;
      }
    } catch (e2) {}
  });
})();
"""


state.trame__scripts = list(state.initial.get("trame__scripts", [])) + [
    "/openfoam-fullbleed.js",
    "/openfoam-bridge.js",
]

with VAppLayout(server) as layout:
    with vuetify3.VMain(classes="d-flex flex-column flex-grow-1 pa-0", style="min-height:0;height:100%;"):
        with html.Div(style="display:none", aria_hidden="true"):
            with html.Div(id="openfoam-bridge-json-in"):
                vuetify3.VTextField(v_model=("bridge_json", ""), density="compact", hide_details=True)
            vuetify3.VBtn(
                "bridge consume",
                click=ctrl.openfoam_bridge_consume_json,
                id="openfoam-bridge-consume-btn",
                style="display:none",
            )
            with html.Div(id="openfoam-bridge-json-out"):
                vuetify3.VTextField(
                    v_model=("bridge_out_json", "{}"),
                    density="compact",
                    hide_details=True,
                    readonly=True,
                )
            vuetify3.VBtn(".", click=ctrl.step_prev, id="openfoam-cmd-prev", style="display:none", aria_hidden="true")
            vuetify3.VBtn(".", click=ctrl.step_next, id="openfoam-cmd-next", style="display:none", aria_hidden="true")
            vuetify3.VBtn(".", click=ctrl.openfoam_toggle_play, id="openfoam-cmd-toggle-play", style="display:none", aria_hidden="true")
            vuetify3.VBtn(".", click=ctrl.openfoam_refresh_lists, id="openfoam-cmd-refresh", style="display:none", aria_hidden="true")
            vuetify3.VBtn(".", click=ctrl.openfoam_vtk_load, id="openfoam-trame-load-btn", style="display:none", aria_hidden="true")
        with html.Div(classes="openfoam-vtk-root d-flex flex-column flex-grow-1", style="min-height:0;flex:1;width:100%;"):
            local_view = vtk.VtkLocalView(
                render_window,
                ref="view",
                context_name=("vtk_cache_ns", "default"),
                after_scene_loaded=lambda **_: server.js_call("view", "resetCamera"),
            )


if __name__ == "__main__":
    # Prefer launching via `trame run --server /deploy/app.py ...` (see docker-compose).
    # timeout=0 disables wslink idle shutdown; host/port still come from argv when using `python app.py ...`.
    server.start(timeout=0)

