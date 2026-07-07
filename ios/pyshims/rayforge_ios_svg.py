"""
iOS SVG rasterizer: svgelements -> cairo.

iOS has neither libvips svgload (pyvips is a Phase-2 stub) nor the Rsvg
GIR, so Rayforge's render_svg_to_cairo() raised 'Namespace Rsvg not
available' on every workpiece render - an endless retry/regenerate loop
(eternal progress bar, half-rendered laser previews).

svgelements (already bundled, pure Python) parses the SVG - including
transforms, shapes-to-paths, and CSS colors - and this module replays
the resulting path segments through pycairo. Coverage: paths, all basic
shapes, fills (with fill-rule), strokes (width, caps, joins), opacity.
Not covered: text, gradients, filters, embedded images - fine for laser
workpieces, and librsvg-for-iOS remains the Phase-2 gold fix.
"""

import io
import logging

logger = logging.getLogger(__name__)


def _rgba(color):
    return (
        color.red / 255.0,
        color.green / 255.0,
        color.blue / 255.0,
        color.alpha / 255.0,
    )


def _draw_path(ctx, path, CubicBezier, QuadraticBezier, Arc, Move, Close):
    for seg in path:
        if isinstance(seg, Move):
            if seg.end is not None:
                ctx.move_to(seg.end.x, seg.end.y)
        elif isinstance(seg, Close):
            ctx.close_path()
        elif isinstance(seg, CubicBezier):
            ctx.curve_to(
                seg.control1.x, seg.control1.y,
                seg.control2.x, seg.control2.y,
                seg.end.x, seg.end.y,
            )
        elif isinstance(seg, QuadraticBezier):
            # elevate quadratic to cubic
            sx, sy = seg.start.x, seg.start.y
            cx, cy = seg.control.x, seg.control.y
            ex, ey = seg.end.x, seg.end.y
            ctx.curve_to(
                sx + 2.0 / 3.0 * (cx - sx), sy + 2.0 / 3.0 * (cy - sy),
                ex + 2.0 / 3.0 * (cx - ex), ey + 2.0 / 3.0 * (cy - ey),
                ex, ey,
            )
        elif isinstance(seg, Arc):
            for cub in seg.as_cubic_curves():
                ctx.curve_to(
                    cub.control1.x, cub.control1.y,
                    cub.control2.x, cub.control2.y,
                    cub.end.x, cub.end.y,
                )
        else:  # Line and anything line-like with an endpoint
            end = getattr(seg, "end", None)
            if end is not None:
                ctx.line_to(end.x, end.y)


def render_svg_to_cairo_ios(svg_data, width, height):
    """Renders SVG bytes to a cairo.ImageSurface of width x height px."""
    import cairo
    from svgelements import (
        SVG, Shape, Path, Move, Close,
        CubicBezier, QuadraticBezier, Arc,
    )

    if not svg_data or width <= 0 or height <= 0:
        return None

    svg = SVG.parse(io.BytesIO(svg_data))

    # Document size in user units, for the scale to the target pixels.
    doc_w = float(svg.width) if svg.width else 0.0
    doc_h = float(svg.height) if svg.height else 0.0
    if doc_w <= 0 or doc_h <= 0:
        vb = getattr(svg, "viewbox", None)
        if vb is not None:
            doc_w = float(vb.width)
            doc_h = float(vb.height)
    if doc_w <= 0 or doc_h <= 0:
        doc_w, doc_h = float(width), float(height)

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(width), int(height))
    ctx = cairo.Context(surface)
    ctx.scale(width / doc_w, height / doc_h)

    for element in svg.elements():
        if not isinstance(element, Shape):
            continue
        if element.values.get("visibility") == "hidden":
            continue
        if element.values.get("display") == "none":
            continue
        try:
            path = abs(Path(element))  # transforms resolved to user space
        except Exception:
            continue
        if len(path) == 0:
            continue

        ctx.new_path()
        try:
            _draw_path(ctx, path, CubicBezier, QuadraticBezier, Arc,
                       Move, Close)
        except Exception:
            logger.debug("iOS svg: segment replay failed", exc_info=True)
            continue

        fill = getattr(element, "fill", None)
        stroke = getattr(element, "stroke", None)
        has_fill = fill is not None and fill.value is not None
        has_stroke = stroke is not None and stroke.value is not None

        if has_fill:
            if element.values.get("fill-rule") == "evenodd":
                ctx.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
            else:
                ctx.set_fill_rule(cairo.FILL_RULE_WINDING)
            ctx.set_source_rgba(*_rgba(fill))
            if has_stroke:
                ctx.fill_preserve()
            else:
                ctx.fill()
        if has_stroke:
            sw = getattr(element, "stroke_width", None)
            try:
                sw = float(sw) if sw is not None else 1.0
            except (TypeError, ValueError):
                sw = 1.0
            if sw <= 0:
                sw = 1.0
            ctx.set_line_width(sw)
            cap = element.values.get("stroke-linecap")
            ctx.set_line_cap(
                cairo.LINE_CAP_ROUND if cap == "round"
                else cairo.LINE_CAP_SQUARE if cap == "square"
                else cairo.LINE_CAP_BUTT
            )
            join = element.values.get("stroke-linejoin")
            ctx.set_line_join(
                cairo.LINE_JOIN_ROUND if join == "round"
                else cairo.LINE_JOIN_BEVEL if join == "bevel"
                else cairo.LINE_JOIN_MITER
            )
            ctx.set_source_rgba(*_rgba(stroke))
            ctx.stroke()
        if not has_fill and not has_stroke:
            # SVG default paint is black fill
            ctx.set_source_rgba(0, 0, 0, 1)
            ctx.fill()

    surface.flush()
    return surface
