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
};

struct _GdkIOSCairoContextClass
{
  GdkCairoContextClass parent_class;
};

G_DEFINE_TYPE (GdkIOSCairoContext, gdk_ios_cairo_context, GDK_TYPE_CAIRO_CONTEXT)

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

  /* Repaint the full surface each frame; the whole image becomes the
   * layer contents. Partial-damage upload is a later optimization. */
  cairo_rectangle_int_t bounds = { 0, 0, surface->width, surface->height };
  cairo_region_union_rectangle (region, &bounds);

  self->active_surface =
    cairo_image_surface_create (CAIRO_FORMAT_ARGB32, pixel_w, pixel_h);
  cairo_surface_set_device_scale (self->active_surface, scale, scale);

  *out_color_state = GDK_COLOR_STATE_SRGB;
  *out_depth = gdk_color_state_get_depth (GDK_COLOR_STATE_SRGB);
}

static void
release_cairo_surface (void *info, const void *data, size_t size)
{
  cairo_surface_destroy ((cairo_surface_t *) info);
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
      g_clear_pointer (&self->active_surface, cairo_surface_destroy);
      return;
    }

  /* Hand pixel ownership to the CGImage; the release callback destroys
   * the cairo surface when CoreAnimation is done with the frame. */
  CGDataProviderRef provider =
    CGDataProviderCreateWithData (self->active_surface, data,
                                  (size_t) stride * height,
                                  release_cairo_surface);
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

  /* Ownership moved into the CGImage's data provider. */
  self->active_surface = NULL;
}

static void
gdk_ios_cairo_context_empty_frame (GdkDrawContext *draw_context)
{
}

static void
gdk_ios_cairo_context_surface_resized (GdkDrawContext *draw_context)
{
  /* Next begin_frame allocates at the new size. */
}

static void
gdk_ios_cairo_context_class_init (GdkIOSCairoContextClass *klass)
{
  GdkDrawContextClass *draw_context_class = GDK_DRAW_CONTEXT_CLASS (klass);
  GdkCairoContextClass *cairo_context_class = GDK_CAIRO_CONTEXT_CLASS (klass);

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
