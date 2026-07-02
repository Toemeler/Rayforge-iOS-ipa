/*
 * gdkiosdisplay.c — GdkDisplay, GdkMonitor, GdkDevice and GdkKeymap
 * implementations for the iOS backend. Pure C (no UIKit here); all
 * platform specifics are reached through the shell helpers declared in
 * gdkiosprivate.h and implemented in gdkiosmain.m.
 *
 * SPDX-License-Identifier: LGPL-2.1-or-later
 */

#include "config.h"

#include "gdkiosprivate.h"

static GdkIOSDisplay *the_display = NULL;

GdkIOSDisplay *
gdk_ios_display_get_instance (void)
{
  return the_display;
}

/* ============================================================== Monitor == */

struct _GdkIOSMonitor
{
  GdkMonitor parent_instance;
};

struct _GdkIOSMonitorClass
{
  GdkMonitorClass parent_class;
};

G_DEFINE_TYPE (GdkIOSMonitor, gdk_ios_monitor, GDK_TYPE_MONITOR)

static void
gdk_ios_monitor_class_init (GdkIOSMonitorClass *klass)
{
}

static void
gdk_ios_monitor_init (GdkIOSMonitor *self)
{
}

static GdkIOSMonitor *
gdk_ios_monitor_new (GdkDisplay *display)
{
  GdkIOSMonitor *self = g_object_new (GDK_TYPE_IOS_MONITOR,
                                      "display", display,
                                      NULL);
  int width = 0, height = 0;
  gdk_ios_shell_get_bounds (&width, &height);

  GdkRectangle geometry = { 0, 0, width, height };
  gdk_monitor_set_geometry (GDK_MONITOR (self), &geometry);
  gdk_monitor_set_scale (GDK_MONITOR (self), gdk_ios_shell_get_scale ());
  gdk_monitor_set_connector (GDK_MONITOR (self), "ios-0");
  gdk_monitor_set_model (GDK_MONITOR (self), "iPad display");
  gdk_monitor_set_manufacturer (GDK_MONITOR (self), "Apple");
  return self;
}

/* =============================================================== Device == */

struct _GdkIOSDevice
{
  GdkDevice parent_instance;
};

struct _GdkIOSDeviceClass
{
  GdkDeviceClass parent_class;
};

G_DEFINE_TYPE (GdkIOSDevice, gdk_ios_device, GDK_TYPE_DEVICE)

static void
gdk_ios_device_set_surface_cursor (GdkDevice  *device,
                                   GdkSurface *surface,
                                   GdkCursor  *cursor)
{
  /* v1: no cursor styling on iOS */
}

static GdkGrabStatus
gdk_ios_device_grab (GdkDevice    *device,
                     GdkSurface   *surface,
                     gboolean      owner_events,
                     GdkEventMask  event_mask,
                     GdkSurface   *confine_to,
                     GdkCursor    *cursor,
                     guint32       time_)
{
  /* Single-app fullscreen environment: grabs trivially succeed. */
  return GDK_GRAB_SUCCESS;
}

static void
gdk_ios_device_ungrab (GdkDevice *device,
                       guint32    time_)
{
}

static GdkSurface *
gdk_ios_device_surface_at_position (GdkDevice *device,
                                    double    *win_x,
                                    double    *win_y,
                                    GdkModifierType *mask)
{
  GdkIOSDisplay *display = the_display;
  if (display == NULL)
    return NULL;
  if (mask)
    *mask = 0;
  /* v1: report the most recently presented toplevel at 0,0.
   * Precise picking happens in the event path instead. */
  if (display->toplevels)
    {
      if (win_x) *win_x = 0;
      if (win_y) *win_y = 0;
      return GDK_SURFACE (display->toplevels->data);
    }
  return NULL;
}

static void
gdk_ios_device_class_init (GdkIOSDeviceClass *klass)
{
  GdkDeviceClass *device_class = GDK_DEVICE_CLASS (klass);

  device_class->set_surface_cursor = gdk_ios_device_set_surface_cursor;
  device_class->grab = gdk_ios_device_grab;
  device_class->ungrab = gdk_ios_device_ungrab;
  device_class->surface_at_position = gdk_ios_device_surface_at_position;
}

static void
gdk_ios_device_init (GdkIOSDevice *self)
{
}

/* =============================================================== Keymap == */

/* Identity keymap in the style of the broadway backend: the event
 * translation layer (gdkiosmain.m) computes final GDK keyvals from UIKit
 * key events, and keycode == keyval throughout. */

struct _GdkIOSKeymap
{
  GdkKeymap parent_instance;
};

struct _GdkIOSKeymapClass
{
  GdkKeymapClass parent_class;
};

G_DEFINE_TYPE (GdkIOSKeymap, gdk_ios_keymap, GDK_TYPE_KEYMAP)

static PangoDirection
gdk_ios_keymap_get_direction (GdkKeymap *keymap)
{
  return PANGO_DIRECTION_NEUTRAL;
}

static gboolean
gdk_ios_keymap_have_bidi_layouts (GdkKeymap *keymap)
{
  return FALSE;
}

static gboolean
gdk_ios_keymap_get_caps_lock_state (GdkKeymap *keymap)
{
  return FALSE;
}

static gboolean
gdk_ios_keymap_get_num_lock_state (GdkKeymap *keymap)
{
  return FALSE;
}

static gboolean
gdk_ios_keymap_get_scroll_lock_state (GdkKeymap *keymap)
{
  return FALSE;
}

static gboolean
gdk_ios_keymap_get_entries_for_keyval (GdkKeymap *keymap,
                                       guint      keyval,
                                       GArray    *keys)
{
  GdkKeymapKey key = { .keycode = keyval, .group = 0, .level = 0 };
  g_array_append_val (keys, key);
  return TRUE;
}

static gboolean
gdk_ios_keymap_get_entries_for_keycode (GdkKeymap     *keymap,
                                        guint          hardware_keycode,
                                        GdkKeymapKey **keys,
                                        guint        **keyvals,
                                        int           *n_entries)
{
  if (n_entries)
    *n_entries = 1;
  if (keys)
    {
      *keys = g_new0 (GdkKeymapKey, 1);
      (*keys)[0].keycode = hardware_keycode;
    }
  if (keyvals)
    {
      *keyvals = g_new0 (guint, 1);
      (*keyvals)[0] = hardware_keycode;
    }
  return TRUE;
}

static guint
gdk_ios_keymap_lookup_key (GdkKeymap          *keymap,
                           const GdkKeymapKey *key)
{
  return key->keycode;
}

static gboolean
gdk_ios_keymap_translate_keyboard_state (GdkKeymap       *keymap,
                                         guint            hardware_keycode,
                                         GdkModifierType  state,
                                         int              group,
                                         guint           *keyval,
                                         int             *effective_group,
                                         int             *level,
                                         GdkModifierType *consumed_modifiers)
{
  if (keyval)
    *keyval = hardware_keycode;
  if (effective_group)
    *effective_group = 0;
  if (level)
    *level = 0;
  if (consumed_modifiers)
    *consumed_modifiers = 0;
  return TRUE;
}

static void
gdk_ios_keymap_class_init (GdkIOSKeymapClass *klass)
{
  GdkKeymapClass *keymap_class = GDK_KEYMAP_CLASS (klass);

  keymap_class->get_direction = gdk_ios_keymap_get_direction;
  keymap_class->have_bidi_layouts = gdk_ios_keymap_have_bidi_layouts;
  keymap_class->get_caps_lock_state = gdk_ios_keymap_get_caps_lock_state;
  keymap_class->get_num_lock_state = gdk_ios_keymap_get_num_lock_state;
  keymap_class->get_scroll_lock_state = gdk_ios_keymap_get_scroll_lock_state;
  keymap_class->get_entries_for_keyval = gdk_ios_keymap_get_entries_for_keyval;
  keymap_class->get_entries_for_keycode = gdk_ios_keymap_get_entries_for_keycode;
  keymap_class->lookup_key = gdk_ios_keymap_lookup_key;
  keymap_class->translate_keyboard_state = gdk_ios_keymap_translate_keyboard_state;
}

static void
gdk_ios_keymap_init (GdkIOSKeymap *self)
{
}

/* ============================================================== Display == */

G_DEFINE_TYPE (GdkIOSDisplay, gdk_ios_display, GDK_TYPE_DISPLAY)

static const char *
gdk_ios_display_get_name (GdkDisplay *display)
{
  return "ios";
}

static void
gdk_ios_display_beep (GdkDisplay *display)
{
}

static void
gdk_ios_display_sync (GdkDisplay *display)
{
}

static void
gdk_ios_display_flush (GdkDisplay *display)
{
}

static void
gdk_ios_display_queue_events (GdkDisplay *display)
{
  /* Events are delivered synchronously from the UIKit main thread via
   * gdk_ios_display_deliver_event(); nothing to drain here. */
}

static gulong
gdk_ios_display_get_next_serial (GdkDisplay *display)
{
  GdkIOSDisplay *self = GDK_IOS_DISPLAY (display);
  return ++self->next_serial;
}

static void
gdk_ios_display_notify_startup_complete (GdkDisplay *display,
                                         const char *startup_notification_id)
{
}

static GdkKeymap *
gdk_ios_display_get_keymap (GdkDisplay *display)
{
  GdkIOSDisplay *self = GDK_IOS_DISPLAY (display);
  return self->keymap;
}

static GdkSeat *
gdk_ios_display_get_default_seat (GdkDisplay *display)
{
  GdkIOSDisplay *self = GDK_IOS_DISPLAY (display);
  return self->seat;
}

static GListModel *
gdk_ios_display_get_monitors (GdkDisplay *display)
{
  GdkIOSDisplay *self = GDK_IOS_DISPLAY (display);
  return G_LIST_MODEL (self->monitors);
}

static gboolean
gdk_ios_display_get_setting (GdkDisplay *display,
                             const char *name,
                             GValue     *value)
{
  /* Sensible fixed defaults for a touch-capable tablet with pointer. */
  if (g_strcmp0 (name, "gtk-double-click-time") == 0)
    {
      g_value_set_int (value, 400);
      return TRUE;
    }
  return FALSE;
}

void
gdk_ios_display_deliver_event (GdkIOSDisplay *self,
                               GdkEvent      *event)
{
  GList *node = _gdk_event_queue_append (GDK_DISPLAY (self), event);
  _gdk_windowing_got_event (GDK_DISPLAY (self), node, event,
                            ++self->next_serial);
}

GdkIOSSurface *
gdk_ios_display_surface_at (GdkIOSDisplay *self,
                            double x, double y,
                            double *local_x, double *local_y)
{
  /* Iterate surfaces most-recent-first; coordinates are root points. */
  for (GList *l = self->toplevels; l; l = l->next)
    {
      GdkSurface *surface = GDK_SURFACE (l->data);
      if (!GDK_SURFACE_IS_MAPPED (surface))
        continue;
      if (x >= surface->x && y >= surface->y &&
          x < surface->x + surface->width &&
          y < surface->y + surface->height)
        {
          if (local_x) *local_x = x - surface->x;
          if (local_y) *local_y = y - surface->y;
          return GDK_IOS_SURFACE (l->data);
        }
    }
  return NULL;
}

static void
gdk_ios_display_finalize (GObject *object)
{
  GdkIOSDisplay *self = GDK_IOS_DISPLAY (object);

  g_clear_object (&self->monitors);
  g_clear_object (&self->keymap);
  g_list_free (self->toplevels);
  if (the_display == self)
    the_display = NULL;

  G_OBJECT_CLASS (gdk_ios_display_parent_class)->finalize (object);
}

static void
gdk_ios_display_class_init (GdkIOSDisplayClass *klass)
{
  GObjectClass *object_class = G_OBJECT_CLASS (klass);
  GdkDisplayClass *display_class = GDK_DISPLAY_CLASS (klass);

  object_class->finalize = gdk_ios_display_finalize;

  display_class->toplevel_type = GDK_TYPE_IOS_TOPLEVEL;
  display_class->popup_type = GDK_TYPE_IOS_POPUP;
  display_class->cairo_context_type = GDK_TYPE_IOS_CAIRO_CONTEXT;

  display_class->get_name = gdk_ios_display_get_name;
  display_class->beep = gdk_ios_display_beep;
  display_class->sync = gdk_ios_display_sync;
  display_class->flush = gdk_ios_display_flush;
  display_class->queue_events = gdk_ios_display_queue_events;
  display_class->get_next_serial = gdk_ios_display_get_next_serial;
  display_class->notify_startup_complete = gdk_ios_display_notify_startup_complete;
  display_class->get_keymap = gdk_ios_display_get_keymap;
  display_class->get_default_seat = gdk_ios_display_get_default_seat;
  display_class->get_monitors = gdk_ios_display_get_monitors;
  display_class->get_setting = gdk_ios_display_get_setting;
  /* init_gl deliberately not set: GL is unavailable, GSK falls back to
   * the cairo renderer. */
}

static void
gdk_ios_display_init (GdkIOSDisplay *self)
{
  self->monitors = g_list_store_new (GDK_TYPE_MONITOR);
}

GdkDisplay *
_gdk_ios_display_open (const char *display_name)
{
  if (!gdk_ios_shell_is_ready ())
    {
      g_warning ("GDK iOS backend: UIKit shell not initialized. "
                 "Applications must enter through gdk_ios_main() "
                 "(see gdkios.h) so UIApplication exists before "
                 "gdk_display_open().");
      return NULL;
    }

  if (the_display != NULL)
    return g_object_ref (GDK_DISPLAY (the_display));

  GdkIOSDisplay *self = g_object_new (GDK_TYPE_IOS_DISPLAY, NULL);
  the_display = self;

  self->keymap = g_object_new (GDK_TYPE_IOS_KEYMAP, "display", self, NULL);

  self->monitor = gdk_ios_monitor_new (GDK_DISPLAY (self));
  g_list_store_append (self->monitors, self->monitor);
  g_object_unref (self->monitor);

  self->core_pointer = g_object_new (GDK_TYPE_IOS_DEVICE,
                                     "name", "iOS pointer",
                                     "source", GDK_SOURCE_MOUSE,
                                     "has-cursor", TRUE,
                                     "display", self,
                                     NULL);
  self->core_keyboard = g_object_new (GDK_TYPE_IOS_DEVICE,
                                      "name", "iOS keyboard",
                                      "source", GDK_SOURCE_KEYBOARD,
                                      "has-cursor", FALSE,
                                      "display", self,
                                      NULL);
  self->seat = gdk_seat_default_new_for_logical_pair (self->core_pointer,
                                                      self->core_keyboard);
  gdk_display_add_seat (GDK_DISPLAY (self), self->seat);

  g_signal_emit_by_name (self, "opened");

  return GDK_DISPLAY (self);
}
