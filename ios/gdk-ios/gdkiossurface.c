/*
 * gdkiossurface.m — GdkSurface / GdkToplevel / GdkPopup for the iOS
 * backend. Every surface is one CALayer composited into the fullscreen
 * root UIView. Toplevels occupy the full screen (iPad app model); popups
 * are positioned sublayers laid out with gdk_surface_layout_popup_helper.
 *
 * SPDX-License-Identifier: LGPL-2.1-or-later
 */

#import <QuartzCore/QuartzCore.h>
#import <Foundation/Foundation.h>

#include "gdkiosprivate.h"

/* ======================================================== Surface (base) == */

G_DEFINE_TYPE (GdkIOSSurface, gdk_ios_surface, GDK_TYPE_SURFACE)

void
gdk_ios_surface_attach_layer (GdkIOSSurface *self)
{
  if (self->layer != NULL)
    return;

  CALayer *layer = [[CALayer alloc] init];
  layer.anchorPoint = CGPointMake (0, 0);
  layer.contentsScale = self->scale;
  layer.opaque = NO;
  layer.magnificationFilter = kCAFilterNearest;
  self->layer = (__bridge_retained gpointer) layer;

  CALayer *root = (__bridge CALayer *) gdk_ios_shell_get_root_layer ();
  [CATransaction begin];
  [CATransaction setDisableActions:YES];
  [root addSublayer:layer];
  [CATransaction commit];
}

void
gdk_ios_surface_detach_layer (GdkIOSSurface *self)
{
  if (self->layer == NULL)
    return;
  CALayer *layer = (__bridge_transfer CALayer *) self->layer;
  self->layer = NULL;
  [CATransaction begin];
  [CATransaction setDisableActions:YES];
  [layer removeFromSuperlayer];
  [CATransaction commit];
}

void
gdk_ios_surface_apply_frame (GdkIOSSurface *self,
                             int x, int y, int width, int height)
{
  GdkSurface *surface = GDK_SURFACE (self);

  surface->x = x;
  surface->y = y;
  surface->width = width;
  surface->height = height;

  if (self->layer != NULL)
    {
      CALayer *layer = (__bridge CALayer *) self->layer;
      [CATransaction begin];
      [CATransaction setDisableActions:YES];
      layer.frame = CGRectMake (x, y, width, height);
      [CATransaction commit];
    }

  _gdk_surface_update_size (surface);
  gdk_surface_invalidate_rect (surface, NULL);
  gdk_surface_request_layout (surface);
}

static void
gdk_ios_surface_hide (GdkSurface *surface)
{
  GdkIOSSurface *self = GDK_IOS_SURFACE (surface);

  self->visible = FALSE;
  if (self->layer != NULL)
    {
      CALayer *layer = (__bridge CALayer *) self->layer;
      [CATransaction begin];
      [CATransaction setDisableActions:YES];
      layer.hidden = YES;
      [CATransaction commit];
    }
  gdk_surface_set_is_mapped (surface, FALSE);
}

static void
gdk_ios_surface_get_geometry (GdkSurface *surface,
                              int *x, int *y, int *width, int *height)
{
  if (x) *x = surface->x;
  if (y) *y = surface->y;
  if (width) *width = surface->width;
  if (height) *height = surface->height;
}

static void
gdk_ios_surface_get_root_coords (GdkSurface *surface,
                                 int x, int y,
                                 int *root_x, int *root_y)
{
  if (root_x) *root_x = surface->x + x;
  if (root_y) *root_y = surface->y + y;
}

static gboolean
gdk_ios_surface_get_device_state (GdkSurface *surface,
                                  GdkDevice *device,
                                  double *x, double *y,
                                  GdkModifierType *mask)
{
  double rx = 0, ry = 0;
  GdkModifierType m = 0;
  gdk_ios_shell_get_pointer_position (&rx, &ry, &m);
  if (x) *x = rx - surface->x;
  if (y) *y = ry - surface->y;
  if (mask) *mask = m;
  return TRUE;
}

static void
gdk_ios_surface_set_input_region (GdkSurface *surface,
                                  cairo_region_t *region)
{
  /* v1: full-surface input */
}

static void
gdk_ios_surface_destroy (GdkSurface *surface,
                         gboolean    foreign_destroy)
{
  GdkIOSSurface *self = GDK_IOS_SURFACE (surface);
  GdkIOSDisplay *display = GDK_IOS_DISPLAY (gdk_surface_get_display (surface));

  display->toplevels = g_list_remove (display->toplevels, self);
  gdk_ios_surface_detach_layer (self);
}

static double
gdk_ios_surface_get_scale (GdkSurface *surface)
{
  GdkIOSSurfacePrivate *priv =
    gdk_ios_surface_get_private (GDK_IOS_SURFACE (surface));
  return self->scale > 0 ? self->scale : 1.0;
}

static gboolean
gdk_ios_surface_compute_size (GdkSurface *surface)
{
  /* Subclasses handle sizing in present(); nothing async here. */
  return FALSE;
}

static void
gdk_ios_surface_constructed (GObject *object)
{
  GdkIOSSurface *self = GDK_IOS_SURFACE (object);

  self->scale = gdk_ios_shell_get_scale ();

  G_OBJECT_CLASS (gdk_ios_surface_parent_class)->constructed (object);
}

static void
gdk_ios_surface_finalize (GObject *object)
{
  GdkIOSSurface *self = GDK_IOS_SURFACE (object);
  gdk_ios_surface_detach_layer (self);
  G_OBJECT_CLASS (gdk_ios_surface_parent_class)->finalize (object);
}

static void
gdk_ios_surface_class_init (GdkIOSSurfaceClass *klass)
{
  GObjectClass *object_class = G_OBJECT_CLASS (klass);
  GdkSurfaceClass *surface_class = GDK_SURFACE_CLASS (klass);

  object_class->constructed = gdk_ios_surface_constructed;
  object_class->finalize = gdk_ios_surface_finalize;

  surface_class->hide = gdk_ios_surface_hide;
  surface_class->get_geometry = gdk_ios_surface_get_geometry;
  surface_class->get_root_coords = gdk_ios_surface_get_root_coords;
  surface_class->get_device_state = gdk_ios_surface_get_device_state;
  surface_class->set_input_region = gdk_ios_surface_set_input_region;
  surface_class->destroy = gdk_ios_surface_destroy;
  surface_class->get_scale = gdk_ios_surface_get_scale;
  surface_class->compute_size = gdk_ios_surface_compute_size;
}

static void
gdk_ios_surface_init (GdkIOSSurface *self)
{
}

/* ============================================================== Toplevel == */

struct _GdkIOSToplevel
{
  GdkIOSSurface parent_instance;
  GdkToplevelLayout *layout;
};

struct _GdkIOSToplevelClass
{
  GdkIOSSurfaceClass parent_class;
};

static void gdk_ios_toplevel_iface_init (GdkToplevelInterface *iface);

G_DEFINE_TYPE_WITH_CODE (GdkIOSToplevel, gdk_ios_toplevel, GDK_TYPE_IOS_SURFACE,
                         G_IMPLEMENT_INTERFACE (GDK_TYPE_TOPLEVEL,
                                                gdk_ios_toplevel_iface_init))

static void
gdk_ios_toplevel_present (GdkToplevel *toplevel,
                          GdkToplevelLayout *layout)
{
  GdkIOSToplevel *self = GDK_IOS_TOPLEVEL (toplevel);
  GdkIOSSurface *surface_impl = GDK_IOS_SURFACE (self);
  GdkSurface *surface = GDK_SURFACE (self);
  GdkIOSDisplay *display = GDK_IOS_DISPLAY (gdk_surface_get_display (surface));

  if (layout != self->layout)
    {
      g_clear_pointer (&self->layout, gdk_toplevel_layout_unref);
      self->layout = gdk_toplevel_layout_copy (layout);
    }

  /* Respect GTK's size negotiation, then occupy the full screen —
   * the iPad application model is one fullscreen window. */
  int bounds_w = 0, bounds_h = 0;
  gdk_ios_shell_get_bounds (&bounds_w, &bounds_h);

  GdkToplevelSize size;
  gdk_toplevel_size_init (&size, bounds_w, bounds_h);
  gdk_toplevel_notify_compute_size (toplevel, &size);

  gdk_ios_surface_attach_layer (surface_impl);
  surface_impl->visible = TRUE;

  if (!g_list_find (display->toplevels, self))
    display->toplevels = g_list_prepend (display->toplevels, self);

  CALayer *layer = (__bridge CALayer *) surface_impl->layer;
  layer.hidden = NO;

  gdk_surface_set_is_mapped (surface, TRUE);
  gdk_ios_surface_apply_frame (surface_impl, 0, 0, bounds_w, bounds_h);
}

static void
gdk_ios_toplevel_focus (GdkToplevel *toplevel,
                        guint32 timestamp)
{
}

static gboolean
gdk_ios_toplevel_minimize (GdkToplevel *toplevel)
{
  return FALSE;
}

static gboolean
gdk_ios_toplevel_lower (GdkToplevel *toplevel)
{
  return FALSE;
}

static void
gdk_ios_toplevel_begin_resize (GdkToplevel *toplevel,
                               GdkSurfaceEdge edge,
                               GdkDevice *device,
                               int button,
                               double x, double y,
                               guint32 timestamp)
{
}

static void
gdk_ios_toplevel_begin_move (GdkToplevel *toplevel,
                             GdkDevice *device,
                             int button,
                             double x, double y,
                             guint32 timestamp)
{
}

static void
gdk_ios_toplevel_iface_init (GdkToplevelInterface *iface)
{
  iface->present = gdk_ios_toplevel_present;
  iface->focus = gdk_ios_toplevel_focus;
  iface->minimize = gdk_ios_toplevel_minimize;
  iface->lower = gdk_ios_toplevel_lower;
  iface->begin_resize = gdk_ios_toplevel_begin_resize;
  iface->begin_move = gdk_ios_toplevel_begin_move;
}

static void
gdk_ios_toplevel_finalize (GObject *object)
{
  GdkIOSToplevel *self = GDK_IOS_TOPLEVEL (object);
  g_clear_pointer (&self->layout, gdk_toplevel_layout_unref);
  G_OBJECT_CLASS (gdk_ios_toplevel_parent_class)->finalize (object);
}

static void
gdk_ios_toplevel_class_init (GdkIOSToplevelClass *klass)
{
  G_OBJECT_CLASS (klass)->finalize = gdk_ios_toplevel_finalize;
}

static void
gdk_ios_toplevel_init (GdkIOSToplevel *self)
{
}

/* ================================================================= Popup == */

struct _GdkIOSPopup
{
  GdkIOSSurface parent_instance;
};

struct _GdkIOSPopupClass
{
  GdkIOSSurfaceClass parent_class;
};

static void gdk_ios_popup_iface_init (GdkPopupInterface *iface);

G_DEFINE_TYPE_WITH_CODE (GdkIOSPopup, gdk_ios_popup, GDK_TYPE_IOS_SURFACE,
                         G_IMPLEMENT_INTERFACE (GDK_TYPE_POPUP,
                                                gdk_ios_popup_iface_init))

static gboolean
gdk_ios_popup_present (GdkPopup *popup,
                       int width,
                       int height,
                       GdkPopupLayout *layout)
{
  GdkIOSSurface *surface_impl = GDK_IOS_SURFACE (popup);
  GdkSurface *surface = GDK_SURFACE (popup);
  GdkIOSDisplay *display = GDK_IOS_DISPLAY (gdk_surface_get_display (surface));

  GdkMonitor *monitor = GDK_MONITOR (display->monitor);
  GdkRectangle bounds;
  gdk_monitor_get_geometry (monitor, &bounds);

  GdkRectangle final_rect;
  gdk_surface_layout_popup_helper (surface,
                                   width, height,
                                   0, 0, 0, 0,
                                   monitor,
                                   &bounds,
                                   layout,
                                   &final_rect);

  /* Popup coordinates from the helper are relative to the parent. */
  int root_x = final_rect.x;
  int root_y = final_rect.y;
  if (surface->parent != NULL)
    {
      root_x += surface->parent->x;
      root_y += surface->parent->y;
    }

  gdk_ios_surface_attach_layer (surface_impl);
  surface_impl->visible = TRUE;

  CALayer *layer = (__bridge CALayer *) surface_impl->layer;
  layer.hidden = NO;
  layer.zPosition = 100; /* above toplevels */

  gdk_surface_set_is_mapped (surface, TRUE);
  gdk_ios_surface_apply_frame (surface_impl,
                               root_x, root_y,
                               final_rect.width, final_rect.height);
  return TRUE;
}

static GdkGravity
gdk_ios_popup_get_surface_anchor (GdkPopup *popup)
{
  return GDK_SURFACE (popup)->popup.surface_anchor;
}

static GdkGravity
gdk_ios_popup_get_rect_anchor (GdkPopup *popup)
{
  return GDK_SURFACE (popup)->popup.rect_anchor;
}

static int
gdk_ios_popup_get_position_x (GdkPopup *popup)
{
  GdkSurface *surface = GDK_SURFACE (popup);
  return surface->x - (surface->parent ? surface->parent->x : 0);
}

static int
gdk_ios_popup_get_position_y (GdkPopup *popup)
{
  GdkSurface *surface = GDK_SURFACE (popup);
  return surface->y - (surface->parent ? surface->parent->y : 0);
}

static void
gdk_ios_popup_iface_init (GdkPopupInterface *iface)
{
  iface->present = gdk_ios_popup_present;
  iface->get_surface_anchor = gdk_ios_popup_get_surface_anchor;
  iface->get_rect_anchor = gdk_ios_popup_get_rect_anchor;
  iface->get_position_x = gdk_ios_popup_get_position_x;
  iface->get_position_y = gdk_ios_popup_get_position_y;
}

static void
gdk_ios_popup_class_init (GdkIOSPopupClass *klass)
{
}

static void
gdk_ios_popup_init (GdkIOSPopup *self)
{
}
