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

  g_message ("gdk-ios: attach_layer surface=%p layer=%p root=%p "
             "root.bounds=%.0fx%.0f root.sublayers=%lu scale=%.2f",
             (void *) self, (__bridge void *) layer, (__bridge void *) root,
             (double) root.bounds.size.width,
             (double) root.bounds.size.height,
             (unsigned long) root.sublayers.count, (double) self->scale);
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

      g_message ("gdk-ios: apply_frame surface=%p req=(%d,%d,%dx%d) "
                 "layer.frame=(%.0f,%.0f,%.0fx%.0f)",
                 (void *) self, x, y, width, height,
                 (double) layer.frame.origin.x, (double) layer.frame.origin.y,
                 (double) layer.frame.size.width,
                 (double) layer.frame.size.height);
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
  GdkIOSSurface *self = GDK_IOS_SURFACE (surface);
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
  GdkSurface *surface = GDK_SURFACE (object);
  GdkFrameClock *frame_clock;

  self->scale = gdk_ios_shell_get_scale ();

  /* Every surface needs a frame clock before gtk_native_realize();
   * same pattern as the android backend (idle clock driven by the
   * GLib main context, which our CADisplayLink pumps). */
  frame_clock = _gdk_frame_clock_idle_new ();
  gdk_surface_set_frame_clock (surface, frame_clock);
  g_object_unref (frame_clock);

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
  char *title;
};

enum
{
  IOS_TOPLEVEL_N_PROPERTIES = 1, /* prop ids start at 1 */
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

  g_message ("gdk-ios: toplevel_present shell_bounds=%dx%d", bounds_w, bounds_h);

  GdkToplevelSize size;
  gdk_toplevel_size_init (&size, bounds_w, bounds_h);
  gdk_toplevel_notify_compute_size (toplevel, &size);

  /* The main window (no transient parent) owns the whole screen. A
   * transient dialog (Adw.MessageDialog, preferences, machine settings,
   * ...) is given the natural size GTK just negotiated and centred,
   * rather than being stretched to fullscreen — stretching a small
   * dialog to 1032x1376 is what made its contents overflow. */
  int win_w = bounds_w, win_h = bounds_h, win_x = 0, win_y = 0;
  if (surface->transient_for != NULL)
    {
      if (size.width > 0 && size.width < bounds_w)
        {
          win_w = size.width;
          win_x = (bounds_w - win_w) / 2;
        }
      if (size.height > 0 && size.height < bounds_h)
        {
          win_h = size.height;
          win_y = (bounds_h - win_h) / 2;
        }
    }
  g_message ("gdk-ios: present placement transient=%d natural=%dx%d "
             "-> frame=(%d,%d,%dx%d)",
             (int) (surface->transient_for != NULL),
             size.width, size.height, win_x, win_y, win_w, win_h);

  gdk_ios_surface_attach_layer (surface_impl);
  surface_impl->visible = TRUE;

  if (!g_list_find (display->toplevels, self))
    display->toplevels = g_list_prepend (display->toplevels, self);

  CALayer *layer = (__bridge CALayer *) surface_impl->layer;
  layer.hidden = NO;

  gdk_surface_set_is_mapped (surface, TRUE);
  gdk_ios_surface_apply_frame (surface_impl, win_x, win_y, win_w, win_h);
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
  g_clear_pointer (&self->title, g_free);
  G_OBJECT_CLASS (gdk_ios_toplevel_parent_class)->finalize (object);
}

static void
gdk_ios_toplevel_get_property (GObject    *object,
                               guint       prop_id,
                               GValue     *value,
                               GParamSpec *pspec)
{
  GdkIOSToplevel *self = GDK_IOS_TOPLEVEL (object);
  GdkSurface *surface = (GdkSurface *) self;

  switch (prop_id)
    {
    case IOS_TOPLEVEL_N_PROPERTIES + GDK_TOPLEVEL_PROP_STATE:
      g_value_set_flags (value, surface->state);
      break;

    case IOS_TOPLEVEL_N_PROPERTIES + GDK_TOPLEVEL_PROP_TITLE:
      g_value_set_string (value, self->title);
      break;

    case IOS_TOPLEVEL_N_PROPERTIES + GDK_TOPLEVEL_PROP_STARTUP_ID:
      g_value_set_string (value, "");
      break;

    case IOS_TOPLEVEL_N_PROPERTIES + GDK_TOPLEVEL_PROP_TRANSIENT_FOR:
      g_value_set_object (value, surface->transient_for);
      break;

    case IOS_TOPLEVEL_N_PROPERTIES + GDK_TOPLEVEL_PROP_MODAL:
      g_value_set_boolean (value, surface->modal_hint);
      break;

    case IOS_TOPLEVEL_N_PROPERTIES + GDK_TOPLEVEL_PROP_ICON_LIST:
      g_value_set_pointer (value, NULL);
      break;

    case IOS_TOPLEVEL_N_PROPERTIES + GDK_TOPLEVEL_PROP_DECORATED:
      g_value_set_boolean (value, FALSE);
      break;

    case IOS_TOPLEVEL_N_PROPERTIES + GDK_TOPLEVEL_PROP_DELETABLE:
      g_value_set_boolean (value, FALSE);
      break;

    case IOS_TOPLEVEL_N_PROPERTIES + GDK_TOPLEVEL_PROP_FULLSCREEN_MODE:
      g_value_set_enum (value, surface->fullscreen_mode);
      break;

    case IOS_TOPLEVEL_N_PROPERTIES + GDK_TOPLEVEL_PROP_SHORTCUTS_INHIBITED:
      g_value_set_boolean (value, FALSE);
      break;

    case IOS_TOPLEVEL_N_PROPERTIES + GDK_TOPLEVEL_PROP_CAPABILITIES:
      g_value_set_flags (value, 0);
      break;

    case IOS_TOPLEVEL_N_PROPERTIES + GDK_TOPLEVEL_PROP_GRAVITY:
      g_value_set_enum (value, GDK_GRAVITY_NORTH_WEST);
      break;

    default:
      G_OBJECT_WARN_INVALID_PROPERTY_ID (object, prop_id, pspec);
      break;
    }
}

static void
gdk_ios_toplevel_set_property (GObject      *object,
                               guint         prop_id,
                               const GValue *value,
                               GParamSpec   *pspec)
{
  GdkIOSToplevel *self = GDK_IOS_TOPLEVEL (object);
  GdkSurface *surface = (GdkSurface *) self;

  switch (prop_id)
    {
    case IOS_TOPLEVEL_N_PROPERTIES + GDK_TOPLEVEL_PROP_TITLE:
      g_clear_pointer (&self->title, g_free);
      self->title = g_value_dup_string (value);
      g_object_notify_by_pspec (G_OBJECT (surface), pspec);
      break;

    case IOS_TOPLEVEL_N_PROPERTIES + GDK_TOPLEVEL_PROP_STARTUP_ID:
      break;

    case IOS_TOPLEVEL_N_PROPERTIES + GDK_TOPLEVEL_PROP_TRANSIENT_FOR:
      g_clear_object (&surface->transient_for);
      surface->transient_for = g_value_dup_object (value);
      g_object_notify_by_pspec (G_OBJECT (surface), pspec);
      break;

    case IOS_TOPLEVEL_N_PROPERTIES + GDK_TOPLEVEL_PROP_MODAL:
      surface->modal_hint = g_value_get_boolean (value);
      g_object_notify_by_pspec (G_OBJECT (surface), pspec);
      break;

    case IOS_TOPLEVEL_N_PROPERTIES + GDK_TOPLEVEL_PROP_ICON_LIST:
      break;

    case IOS_TOPLEVEL_N_PROPERTIES + GDK_TOPLEVEL_PROP_DECORATED:
      break;

    case IOS_TOPLEVEL_N_PROPERTIES + GDK_TOPLEVEL_PROP_DELETABLE:
      break;

    case IOS_TOPLEVEL_N_PROPERTIES + GDK_TOPLEVEL_PROP_FULLSCREEN_MODE:
      surface->fullscreen_mode = g_value_get_enum (value);
      g_object_notify_by_pspec (G_OBJECT (surface), pspec);
      break;

    case IOS_TOPLEVEL_N_PROPERTIES + GDK_TOPLEVEL_PROP_SHORTCUTS_INHIBITED:
      break;

    case IOS_TOPLEVEL_N_PROPERTIES + GDK_TOPLEVEL_PROP_GRAVITY:
      break;

    default:
      G_OBJECT_WARN_INVALID_PROPERTY_ID (object, prop_id, pspec);
      break;
    }
}

static void
gdk_ios_toplevel_class_init (GdkIOSToplevelClass *klass)
{
  GObjectClass *object_class = G_OBJECT_CLASS (klass);

  object_class->finalize = gdk_ios_toplevel_finalize;
  object_class->get_property = gdk_ios_toplevel_get_property;
  object_class->set_property = gdk_ios_toplevel_set_property;

  gdk_toplevel_install_properties (object_class, IOS_TOPLEVEL_N_PROPERTIES);
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

enum
{
  IOS_POPUP_N_PROPERTIES = 1, /* prop ids start at 1 */
};

static void
gdk_ios_popup_get_property (GObject    *object,
                            guint       prop_id,
                            GValue     *value,
                            GParamSpec *pspec)
{
  GdkSurface *surface = GDK_SURFACE (object);

  switch (prop_id)
    {
    case IOS_POPUP_N_PROPERTIES + GDK_POPUP_PROP_PARENT:
      g_value_set_object (value, surface->parent);
      break;

    case IOS_POPUP_N_PROPERTIES + GDK_POPUP_PROP_AUTOHIDE:
      g_value_set_boolean (value, surface->autohide);
      break;

    default:
      G_OBJECT_WARN_INVALID_PROPERTY_ID (object, prop_id, pspec);
      break;
    }
}

static void
gdk_ios_popup_set_property (GObject      *object,
                            guint         prop_id,
                            const GValue *value,
                            GParamSpec   *pspec)
{
  GdkSurface *surface = (GdkSurface *) object;

  switch (prop_id)
    {
    case IOS_POPUP_N_PROPERTIES + GDK_POPUP_PROP_PARENT:
      surface->parent = g_value_dup_object (value);
      if (surface->parent != NULL)
        surface->parent->children = g_list_prepend (surface->parent->children, surface);
      break;

    case IOS_POPUP_N_PROPERTIES + GDK_POPUP_PROP_AUTOHIDE:
      surface->autohide = g_value_get_boolean (value);
      break;

    default:
      G_OBJECT_WARN_INVALID_PROPERTY_ID (object, prop_id, pspec);
      break;
    }
}

static void
gdk_ios_popup_class_init (GdkIOSPopupClass *klass)
{
  GObjectClass *object_class = G_OBJECT_CLASS (klass);

  object_class->get_property = gdk_ios_popup_get_property;
  object_class->set_property = gdk_ios_popup_set_property;

  gdk_popup_install_properties (object_class, IOS_POPUP_N_PROPERTIES);
}

static void
gdk_ios_popup_init (GdkIOSPopup *self)
{
}
