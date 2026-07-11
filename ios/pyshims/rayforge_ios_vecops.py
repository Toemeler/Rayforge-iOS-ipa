"""Live vector toolpath overlay for the 2D canvas (iOS).

Replaces WorkPieceElement's raster ops compositing with direct cairo
strokes of the step's Ops geometry whenever the command count is
moderate. Result: toolpaths stay pixel-crisp at EVERY zoom level and
remain visible DURING pan/zoom gestures (the raster path hides them
while interacting).

Raster steps (scanline engraves) and very large jobs fall back to the
upstream bitmap pipeline automatically, as does any error.

Coordinate math: Ops are in workpiece-local mm (Y-up); the element's
draw() context is local 1x1 Y-up, so normalized = mm / generation_size.
"""

import logging

import numpy as np

logger = logging.getLogger(__name__)

MAX_VECTOR_COMMANDS = 20000
LINEARIZE_TOLERANCE_MM = 0.05

# raygeo Ops.to_numpy_arrays command type codes (verified empirically:
# move_to -> 1, line_to -> 2)
_T_MOVE = 1
_T_LINE = 2


def build_vec_paths(ops, gen_size, max_cmds=MAX_VECTOR_COMMANDS):
    """Convert an Ops object into normalized drawable arrays.

    Returns (types, points) as numpy arrays with points normalized to
    the unit square, or None if this ops should use the raster path
    (scanlines present, too many commands, or unsupported commands).
    """
    try:
        sc = getattr(ops, "scanline_count", 0)
        if callable(sc):
            sc = sc()
        if sc and int(sc) > 0:
            return None
    except Exception:
        pass
    try:
        n = ops.len()
    except Exception:
        n = None
    if n is not None and n > max_cmds:
        return None

    work = ops.copy()
    for attempt in (
        lambda: work.linearize_all(LINEARIZE_TOLERANCE_MM),
        lambda: work.linearize_all(),
        lambda: work.linearize_arcs(LINEARIZE_TOLERANCE_MM),
        lambda: None,
    ):
        try:
            attempt()
            break
        except TypeError:
            continue
        except AttributeError:
            continue

    arrs = work.to_numpy_arrays()
    types = np.asarray(arrs["types"])
    pts = np.asarray(arrs["endpoints"], dtype=np.float64)
    if len(types) > max_cmds:
        return None

    draw_mask = (types == _T_MOVE) | (types == _T_LINE)
    # Non-geometric commands (state markers etc.) are skippable, but
    # arcs/beziers that survived linearization are not representable.
    if arrs["arc_map"].size and (np.asarray(arrs["arc_map"]) >= 0).any():
        return None
    if (
        arrs["bezier_map"].size
        and (np.asarray(arrs["bezier_map"]) >= 0).any()
    ):
        return None
    if (
        arrs["scanline_map"].size
        and (np.asarray(arrs["scanline_map"]) >= 0).any()
    ):
        return None

    gw, gh = gen_size
    if gw <= 1e-9 or gh <= 1e-9:
        return None
    norm = pts[:, :2].copy()
    norm[:, 0] /= gw
    norm[:, 1] /= gh
    return types[draw_mask], norm[draw_mask]


def draw_vec_paths(ctx, types, points, rgba, px_width=1.2):
    """Stroke normalized paths on a local-1x1 Y-up cairo context."""
    if len(types) == 0:
        return
    lw = abs(ctx.device_to_user_distance(px_width, 0)[0]) or 0.001
    ctx.save()
    try:
        ctx.set_line_width(lw)
        ctx.set_source_rgba(*rgba)
        have_current = False
        for i in range(len(types)):
            x = float(points[i, 0])
            y = float(points[i, 1])
            if types[i] == _T_MOVE:
                if have_current:
                    ctx.stroke()
                    have_current = False
                ctx.move_to(x, y)
                have_current = True
            else:
                if not have_current:
                    ctx.move_to(x, y)
                    have_current = True
                else:
                    ctx.line_to(x, y)
        if have_current:
            ctx.stroke()
    finally:
        ctx.restore()


def _hex_to_rgba(hex_color, alpha=1.0):
    try:
        h = hex_color.lstrip("#")
        if len(h) >= 6:
            return (
                int(h[0:2], 16) / 255.0,
                int(h[2:4], 16) / 255.0,
                int(h[4:6], 16) / 255.0,
                alpha,
            )
    except Exception:
        pass
    return (1.0, 0.0, 1.0, alpha)  # rayforge magenta fallback


def install(ioslog=lambda m: None):
    """Wrap WorkPieceElement.draw with the vector-first strategy."""
    from rayforge.ui_gtk.canvas2d.elements.workpiece import (
        WorkPieceElement,
    )

    orig_draw = WorkPieceElement.draw

    def _vec_state(self):
        st = self.__dict__.get("_ios_vec")
        if st is None:
            st = {"cache": {}, "warned": False}
            self.__dict__["_ios_vec"] = st
        return st

    def _try_vector_ops(self, ctx):
        """Returns True if ops were drawn as vectors."""
        layer = self.data.layer
        if not layer or not layer.workflow:
            return False
        vm = getattr(self, "view_manager", None)
        if vm is None:
            return False
        handles = getattr(vm, "_source_artifact_handles", None)
        store = getattr(vm, "store", None)
        if handles is None or store is None:
            return False

        st = _vec_state(self)
        cache = st["cache"]
        drew_any = False
        rgba = _hex_to_rgba(getattr(layer, "color", "#ff00ff"), 0.9)

        for step in layer.workflow.steps:
            uid = step.uid
            if not self._ops_visibility.get(uid, True):
                continue
            handle = handles.get((self.data.uid, uid))
            if handle is None:
                return False  # not generated yet: let raster path run
            key = getattr(handle, "shm_name", None)
            entry = cache.get(uid)
            if entry is None or entry[0] != key:
                try:
                    artifact = store.get(handle)
                except Exception:
                    return False
                ops = getattr(artifact, "ops", None)
                gen = getattr(artifact, "generation_size", None)
                if ops is None or not gen:
                    return False
                paths = build_vec_paths(ops, gen)
                cache[uid] = (key, paths)
                entry = cache[uid]
            paths = entry[1]
            if paths is None:
                return False  # raster fallback (scanlines / too big)
            draw_vec_paths(ctx, paths[0], paths[1], rgba)
            drew_any = True
        return drew_any

    def draw(self, ctx):
        try:
            # Replicate upstream base-image guards, then try vectors.
            provider_hidden = False
            if self.data.geometry_provider_uid and self.data.doc:
                provider = self.data.doc.get_asset_by_uid(
                    self.data.geometry_provider_uid
                )
                if provider and provider.hidden:
                    provider_hidden = True
            if self._base_image_visible and not provider_hidden:
                super(WorkPieceElement, self).draw(ctx)

            # Vector ops draw even while interacting (that's the point).
            if _try_vector_ops(self, ctx):
                return
        except Exception:
            st = _vec_state(self)
            if not st["warned"]:
                st["warned"] = True
                logger.exception(
                    "vector toolpath draw failed; raster fallback"
                )
        # Fallback: the untouched upstream path (base drawn twice is
        # avoided because orig_draw draws base again — accept the cost,
        # it is a cheap cached surface paint).
        orig_draw(self, ctx)

    WorkPieceElement.draw = draw
    ioslog("vector toolpath overlay installed")
    return True
