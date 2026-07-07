/*
 * gdkioscairocontext.m — cairo draw context for the iOS backend.
 *
 * begin_frame: allocates a cairo image surface at backing-pixel size with
 * the surface's device scale, so GSK's cairo renderer paints at native
 * (retina) resolution. end_frame: wraps the pixels in a CGImage and sets
 * it as the surface CALayer's contents.
 *
 * cairo CAIRO_FORMAT_ARGB32 on little-endian arm64 is BGRA premultiplied,
 * which is exactly CGImage with (kCGBitmapByteOrder32Little |
 * kCGImageAlphaPremultipliedFirst) — no pixel conversion needed.
 *
 * SPDX-License-Identifier: LGPL-2.1-or-later
 */

#import <QuartzCore/QuartzCore.h>
#import <CoreGraphics/CoreGraphics.h>

#include <cairo.h>

#include "gdkiosprivate.h"
#include "gdkcolorstateprivate.h"

struct _GdkIOSCairoContext
{
  GdkCairoContext parent_instance;
  cairo_surface_t *active_surface; /* valid between begin and end frame */
  cairo_surface_t *persistent;     /* backing buffer, survives frames */
  int persistent_w;                /* pixel size of the persistent buffer */
  int persistent_h;
};

struct _GdkIOSCairoContextClass
{
  GdkCairoContextClass parent_class;
};

G_DEFINE_TYPE (GdkIOSCairoContext, gdk_ios_cairo_context, GDK_TYPE_CAIRO_CONTEXT)

/* Per-frame diagnostics write 3 lines per frame to the on-device log
 * FILE (stdout is redirected) at up to 120 fps - measurable jank. Gate
 * them behind GDK_IOS_TRACE; lifecycle logs elsewhere stay unconditional. */
static gboolean
gdk_ios_trace_frames (void)
{
  static int t = -1;
  if (t < 0)
    t = g_getenv ("GDK_IOS_TRACE") != NULL ? 1 : 0;
  return t;
}

static cairo_t *
gdk_ios_cairo_context_cairo_create (GdkCairoContext *cairo_context)
{
  GdkIOSCairoContext *self = GDK_IOS_CAIRO_CONTEXT (cairo_context);
  return self->active_surface ? cairo_create (self->active_surface) : NULL;
}

static void
gdk_ios_cairo_context_begin_frame (GdkDrawContext *draw_context,
                                   gpointer        context_data,
                                   GdkMemoryDepth  depth,
                                   cairo_region_t *region,
                                   GdkColorState **out_color_state,
                                   GdkMemoryDepth *out_depth)
{
  GdkIOSCairoContext *self = GDK_IOS_CAIRO_CONTEXT (draw_context);
  GdkSurface *surface = gdk_draw_context_get_surface (draw_context);
  double scale = gdk_surface_get_scale (surface);

  int pixel_w = (int) ceil (surface->width * scale);
  int pixel_h = (int) ceil (surface->height * scale);

  if (gdk_ios_trace_frames ())
    g_message ("gdk-ios: begin_frame surface=%dx%d scale=%.2f pixels=%dx%d",
               surface->width, surface->height, (double) scale, pixel_w, pixel_h);

  /* GTK only repaints the *damaged* region each frame. The buffer must
   * therefore persist across frames (like the X window does for the X11
   * backend); a fresh transparent buffer every frame left everything
   * outside the damage transparent — the view background bled through as
   * white blocks over previously painted content.
   *
   * NOTE the region handed to this vfunc is already in PIXEL coordinates
   * (gdk_draw_context_begin_frame_full applies scale_grow before calling
   * us), and gdk_cairo_context_cairo_create clips to it in pixel space
   * before applying cairo_scale. Any rect we union in must be pixels. */
  if (self->persistent == NULL ||
      self->persistent_w != pixel_w || self->persistent_h != pixel_h)
    {
      g_clear_pointer (&self->persistent, cairo_surface_destroy);
      self->persistent =
        cairo_image_surface_create (CAIRO_FORMAT_ARGB32, pixel_w, pixel_h);
      /* The buffer is backing-pixel sized, but GdkCairoContext.cairo_create
       * already applies cairo_scale(surface_scale) to the context it hands
       * to GSK. Leave the device scale at 1.0 (as the X11/Wayland cairo
       * backends do) — setting it to `scale` applied HiDPI twice. */
      cairo_surface_set_device_scale (self->persistent, 1.0, 1.0);
      self->persistent_w = pixel_w;
      self->persistent_h = pixel_h;

      /* New (empty) buffer: everything must be repainted. Pixel coords! */
      cairo_rectangle_int_t all = { 0, 0, pixel_w, pixel_h };
      cairo_region_union_rectangle (region, &all);
    }
  else
    {
      /* Reused buffer: clear just the damaged region to transparent so the
       * renderer composites onto a clean slate there, like a fresh paint
       * surface would be. Retained pixels elsewhere stay valid. */
      cairo_t *cr = cairo_create (self->persistent);
      gdk_cairo_region (cr, region);
      cairo_clip (cr);
      cairo_set_operator (cr, CAIRO_OPERATOR_CLEAR);
      cairo_paint (cr);
      cairo_destroy (cr);
    }

  self->active_surface = cairo_surface_reference (self->persistent);

  *out_color_state = GDK_COLOR_STATE_SRGB;
  *out_depth = gdk_color_state_get_depth (GDK_COLOR_STATE_SRGB);
}

static void
gdk_ios_cairo_context_end_frame (GdkDrawContext *draw_context,
                                 gpointer        context_data,
                                 cairo_region_t *painted)
{
  GdkIOSCairoContext *self = GDK_IOS_CAIRO_CONTEXT (draw_context);
  GdkSurface *surface = gdk_draw_context_get_surface (draw_context);
  GdkIOSSurface *surface_impl = GDK_IOS_SURFACE (surface);

  if (self->active_surface == NULL)
    return;

  cairo_surface_flush (self->active_surface);

  int width = cairo_image_surface_get_width (self->active_surface);
  int height = cairo_image_surface_get_height (self->active_surface);
  int stride = cairo_image_surface_get_stride (self->active_surface);
  unsigned char *data = cairo_image_surface_get_data (self->active_surface);

  if (width <= 0 || height <= 0 || data == NULL || surface_impl->layer == NULL)
    {
      g_message ("gdk-ios: end_frame ABORT w=%d h=%d data=%p layer=%p",
                 width, height, (void *) data,
                 (void *) surface_impl->layer);
      g_clear_pointer (&self->active_surface, cairo_surface_destroy);
      return;
    }

  /* Sample the cairo buffer itself (premultiplied BGRA). This is the
   * ground-truth test: if these are non-zero the app IS painting and any
   * black screen is a presentation/geometry bug; if they are 0x00000000
   * the paint never reached this surface. */
  if (gdk_ios_trace_frames ())
  {
    const guint32 *px = (const guint32 *) data;
    int row = stride / 4;
    guint32 center = px[(height / 2) * row + (width / 2)];
    guint32 tl = px[0];
    guint32 tr = px[width - 1];
    guint32 bl = px[(height - 1) * row];
    guint32 br = px[(height - 1) * row + (width - 1)];
    g_message ("gdk-ios: end_frame %dx%d stride=%d data=%p layer=%p "
               "center=0x%08X tl=0x%08X tr=0x%08X bl=0x%08X br=0x%08X",
               width, height, stride, (void *) data,
               (void *) surface_impl->layer,
               center, tl, tr, bl, br);
  }

  /* The backing buffer persists and is mutated next frame, so the CGImage
   * must own a COPY of the pixels (CFData copies on create). */
  CFDataRef pixels =
    CFDataCreate (NULL, (const UInt8 *) data, (CFIndex) stride * height);
  CGDataProviderRef provider = CGDataProviderCreateWithCFData (pixels);
  CFRelease (pixels);
  CGColorSpaceRef colorspace = CGColorSpaceCreateDeviceRGB ();
  CGImageRef image =
    CGImageCreate (width, height,
                   8, 32, stride, colorspace,
                   (CGBitmapInfo) (kCGBitmapByteOrder32Little |
                                   kCGImageAlphaPremultipliedFirst),
                   provider, NULL, false, kCGRenderingIntentDefault);
  CGColorSpaceRelease (colorspace);
  CGDataProviderRelease (provider);

  CALayer *layer = (__bridge CALayer *) surface_impl->layer;
  [CATransaction begin];
  [CATransaction setDisableActions:YES];
  layer.contents = (__bridge_transfer id) image;
  [CATransaction commit];

  if (gdk_ios_trace_frames ())
    g_message ("gdk-ios: presented layer=%p frame=(%.0f,%.0f,%.0fx%.0f) "
             "contentsScale=%.2f opacity=%.2f hidden=%d super=%p "
             "hasContents=%d",
             (__bridge void *) layer,
             (double) layer.frame.origin.x, (double) layer.frame.origin.y,
             (double) layer.frame.size.width, (double) layer.frame.size.height,
             (double) layer.contentsScale, (double) layer.opacity,
             (int) layer.hidden, (__bridge void *) layer.superlayer,
             (int) (layer.contents != nil));

  g_clear_pointer (&self->active_surface, cairo_surface_destroy);
}

static void
gdk_ios_cairo_context_empty_frame (GdkDrawContext *draw_context)
{
}

static void
gdk_ios_cairo_context_surface_resized (GdkDrawContext *draw_context)
{
  GdkIOSCairoContext *self = GDK_IOS_CAIRO_CONTEXT (draw_context);
  /* Size changed: drop the backing buffer; next begin_frame reallocates
   * and forces a full repaint of the new buffer. */
  g_clear_pointer (&self->persistent, cairo_surface_destroy);
  self->persistent_w = self->persistent_h = 0;
}

static void
gdk_ios_cairo_context_finalize (GObject *object)
{
  GdkIOSCairoContext *self = GDK_IOS_CAIRO_CONTEXT (object);
  g_clear_pointer (&self->active_surface, cairo_surface_destroy);
  g_clear_pointer (&self->persistent, cairo_surface_destroy);
  G_OBJECT_CLASS (gdk_ios_cairo_context_parent_class)->finalize (object);
}

static void
gdk_ios_cairo_context_class_init (GdkIOSCairoContextClass *klass)
{
  GObjectClass *object_class = G_OBJECT_CLASS (klass);
  GdkDrawContextClass *draw_context_class = GDK_DRAW_CONTEXT_CLASS (klass);
  GdkCairoContextClass *cairo_context_class = GDK_CAIRO_CONTEXT_CLASS (klass);

  object_class->finalize = gdk_ios_cairo_context_finalize;

  draw_context_class->begin_frame = gdk_ios_cairo_context_begin_frame;
  draw_context_class->end_frame = gdk_ios_cairo_context_end_frame;
  draw_context_class->empty_frame = gdk_ios_cairo_context_empty_frame;
  draw_context_class->surface_resized = gdk_ios_cairo_context_surface_resized;

  cairo_context_class->cairo_create = gdk_ios_cairo_context_cairo_create;
}

static void
gdk_ios_cairo_context_init (GdkIOSCairoContext *self)
{
}
