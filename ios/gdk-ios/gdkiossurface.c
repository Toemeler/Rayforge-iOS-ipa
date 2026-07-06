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

  g_message ("gdk-ios: attach_layer surface=%p type=%s layer=%p root=%p "
             "root.bounds=%.0fx%.0f root.sublayers=%lu scale=%.2f",
             (void *) self,
             GDK_IS_TOPLEVEL (self) ? "toplevel"
               : (GDK_IS_POPUP (self) ? "popup" : "other"),
             (__bridge void *) layer, (__bridge void *) root,
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

  gboolean changed = (x != surface->x || y != surface->y ||
                      width != surface->width || height != surface->height);

  surface->x = x;
  surface->y = y;
  surface->width = width;
  surface->height = height;

  if (self->layer != NULL)
    {
      CALayer *layer = (__bridge CALayer *) self->layer;
      if (!CGRectEqualToRect (layer.frame,
                              CGRectMake (x, y, width, height)))
        {
          [CATransaction begin];
          [CATransaction setDisableActions:YES];
          layer.frame = CGRectMake (x, y, width, height);
          [CATransaction commit];

          g_message ("gdk-ios: apply_frame surface=%p req=(%d,%d,%dx%d) "
                     "layer.frame=(%.0f,%.0f,%.0fx%.0f)",
                     (void *) self, x, y, width, height,
                     (double) layer.frame.origin.x,
                     (double) layer.frame.origin.y,
                     (double) layer.frame.size.width,
                     (double) layer.frame.size.height);
        }
    }

  /* Only kick GTK when the geometry really changed — compute_size runs
   * this on every layout pass, and unconditionally requesting another
   * layout from here would spin the layout loop forever. */
  if (changed)
    {
      _gdk_surface_update_size (surface);
      gdk_surface_invalidate_rect (surface, NULL);
      gdk_surface_request_layout (surface);
    }
}

static void
gdk_ios_surface_hide (GdkSurface *surface)
{
  GdkIOSSurface *self = GDK_IOS_SURFACE (surface);
  GdkIOSDisplay *display = GDK_IOS_DISPLAY (gdk_surface_get_display (surface));

  g_message ("gdk-ios: hide surface=%p type=%s", (void *) self,
             GDK_IS_TOPLEVEL (self) ? "toplevel"
               : (GDK_IS_POPUP (self) ? "popup" : "other"));

  if (GDK_IS_POPUP (self))
    display->popups = g_list_remove (display->popups, self);

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

  g_message ("gdk-ios: destroy surface=%p type=%s foreign=%d", (void *) self,
             GDK_IS_TOPLEVEL (self) ? "toplevel"
               : (GDK_IS_POPUP (self) ? "popup" : "other"),
             foreign_destroy);
  display->toplevels = g_list_remove (display->toplevels, self);
  display->popups = g_list_remove (display->popups, self);
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

/* Window-manager contract, run at present time and on every subsequent
 * layout pass (compute_size):
 *
 *   1. For the primary window (no transient parent), make sure GTK knows
 *      it is MAXIMIZED *before* asking it for a size — gtk_window's
 *      compute-size handler only requests the full monitor bounds when it
 *      believes it is maximized (and then also drops the CSD shadow).
 *   2. Ask GTK what size it wants, giving the screen as the bounds
 *      (this also yields GTK's min size).
 *   3. Primary window: force the full screen size, like a real WM does
 *      on maximize — compute_size only reports GTK's *preference* and
 *      never widens to bounds by itself; GTK reflows to the size we
 *      report via gtk_window_native_layout(). Dialogs: grant exactly
 *      what GTK asked, clamped to the screen.
 *   4. Place it: primary at the origin, transient dialogs centred.
 *
 * Renegotiating on every layout pass lets height-for-width content (e.g.
 * wrapped dialog text) converge instead of being frozen at first guess. */
static void
gdk_ios_toplevel_configure (GdkIOSToplevel *self)
{
  GdkSurface *surface = GDK_SURFACE (self);
  GdkIOSSurface *surface_impl = GDK_IOS_SURFACE (self);

  int bounds_w = 0, bounds_h = 0;
  gdk_ios_shell_get_bounds (&bounds_w, &bounds_h);
  if (bounds_w <= 0 || bounds_h <= 0)
    return;

  gboolean is_dialog = (surface->transient_for != NULL);

  if (!is_dialog &&
      (surface->state & GDK_TOPLEVEL_STATE_MAXIMIZED) == 0)
    gdk_synthesize_surface_state (surface, 0, GDK_TOPLEVEL_STATE_MAXIMIZED);

  GdkToplevelSize size;
  gdk_toplevel_size_init (&size, bounds_w, bounds_h);
  gdk_toplevel_notify_compute_size (GDK_TOPLEVEL (self), &size);

  int win_w, win_h;
  if (!is_dialog)
    {
      /* Maximized primary: a real WM forces the workarea size regardless
       * of the window's preference (compute_size only reports GTK's
       * *preferred* size — gtk_window_compute_default_size never widens
       * to bounds on its own, it just clamps the natural size). GTK then
       * reflows to whatever we report via gtk_window_native_layout().
       * Deliberately ignore GTK's min size here: Rayforge's min width
       * (1115pt) exceeds the iPad portrait width (1032pt), and honoring
       * it hung ~83pt of UI off the right edge. Granting the screen size
       * keeps everything on-screen; GTK squeezes below min gracefully. */
      /* If GTK's minimum width exceeds the screen, granting less makes
       * GTK lay out at its minimum anyway and clip both sides. Instead
       * tell the shell the minimum: it scales the whole coordinate space
       * down (fit-to-width) so the virtual screen is at least min wide,
       * then grant those virtual bounds. Landscape: scale is 1.0. */
      gdk_ios_shell_set_min_width (size.min_width);
      gdk_ios_shell_get_bounds (&bounds_w, &bounds_h);
      win_w = bounds_w;
      win_h = bounds_h;
    }
  else
    {
      /* Dialogs get exactly the size GTK asked for, clamped to screen. */
      win_w = size.width > 0 ? MIN (size.width, bounds_w) : bounds_w;
      win_h = size.height > 0 ? MIN (size.height, bounds_h) : bounds_h;
    }
  int win_x = is_dialog ? (bounds_w - win_w) / 2 : 0;
  int win_y = is_dialog ? (bounds_h - win_h) / 2 : 0;

  if (win_w != surface->width || win_h != surface->height ||
      win_x != surface->x || win_y != surface->y)
    g_message ("gdk-ios: configure transient=%d granted=%dx%d at (%d,%d) "
               "(gtk asked %dx%d, bounds %dx%d)",
               (int) is_dialog, win_w, win_h, win_x, win_y,
               size.width, size.height, bounds_w, bounds_h);

  gdk_ios_surface_apply_frame (surface_impl, win_x, win_y, win_w, win_h);
}

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

  gdk_ios_surface_attach_layer (surface_impl);
  surface_impl->visible = TRUE;

  if (!g_list_find (display->toplevels, self))
    display->toplevels = g_list_prepend (display->toplevels, self);

  CALayer *layer = (__bridge CALayer *) surface_impl->layer;
  layer.hidden = NO;

  gdk_surface_set_is_mapped (surface, TRUE);
  gdk_ios_toplevel_configure (self);
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

static gboolean
gdk_ios_toplevel_compute_size (GdkSurface *surface)
{
  /* GTK queues a compute-size on every layout pass. Run the full
   * window-manager contract (state -> ask GTK with *screen* bounds ->
   * grant clamped -> place) so the surface always matches what GTK laid
   * out. NB: bounds must be the screen, not the current surface size —
   * feeding the surface size back in freezes the window at its first
   * guess and clips height-for-width content like wrapped dialog text. */
  gdk_ios_toplevel_configure (GDK_IOS_TOPLEVEL (surface));
  return GDK_SURFACE_CLASS (gdk_ios_toplevel_parent_class)->compute_size (surface);
}

static void
gdk_ios_toplevel_class_init (GdkIOSToplevelClass *klass)
{
  GObjectClass *object_class = G_OBJECT_CLASS (klass);
  GdkSurfaceClass *surface_class = GDK_SURFACE_CLASS (klass);

  object_class->finalize = gdk_ios_toplevel_finalize;
  object_class->get_property = gdk_ios_toplevel_get_property;
  object_class->set_property = gdk_ios_toplevel_set_property;

  surface_class->compute_size = gdk_ios_toplevel_compute_size;

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

  /* Register for event routing: popups stack above toplevels and must
   * receive the taps that land on them (hit-tested in surface_at). */
  if (g_list_find (display->popups, surface_impl) == NULL)
    display->popups = g_list_prepend (display->popups, surface_impl);

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
