/*
 * gdkiosprivate.h — GDK iOS backend, shared private declarations.
 *
 * A minimal GDK backend for iOS/iPadOS: every GdkSurface is a CALayer
 * composited into a single fullscreen UIView; rendering uses the cairo
 * (software) GSK renderer via cairo image surfaces uploaded as layer
 * contents; input is translated from UIKit touch / pointer (trackpad,
 * mouse) / hardware-keyboard events into GDK events, preserving desktop
 * mouse+keyboard semantics 1:1.
 *
 * Modeled closely on the android and broadway backends of GTK 4.22.
 *
 * SPDX-License-Identifier: LGPL-2.1-or-later
 */

#pragma once

#include "config.h"

#include <glib.h>
#include <gdk/gdk.h>

#include "gdkdisplayprivate.h"
#include "gdksurfaceprivate.h"
#include "gdkdeviceprivate.h"
#include "gdkkeysprivate.h"
#include "gdkmonitorprivate.h"
#include "gdkseatdefaultprivate.h"
#include "gdkcairocontextprivate.h"
#include "gdkeventsprivate.h"
#include "gdkframeclockidleprivate.h"
#include "gdktoplevelprivate.h"
#include "gdkpopupprivate.h"
#include "gdktoplevelsizeprivate.h"

G_BEGIN_DECLS

/* ------------------------------------------------------------------ types */

#define GDK_TYPE_IOS_DISPLAY (gdk_ios_display_get_type ())
G_DECLARE_FINAL_TYPE (GdkIOSDisplay, gdk_ios_display, GDK, IOS_DISPLAY, GdkDisplay)

#define GDK_TYPE_IOS_MONITOR (gdk_ios_monitor_get_type ())
G_DECLARE_FINAL_TYPE (GdkIOSMonitor, gdk_ios_monitor, GDK, IOS_MONITOR, GdkMonitor)

#define GDK_TYPE_IOS_DEVICE (gdk_ios_device_get_type ())
G_DECLARE_FINAL_TYPE (GdkIOSDevice, gdk_ios_device, GDK, IOS_DEVICE, GdkDevice)

#define GDK_TYPE_IOS_KEYMAP (gdk_ios_keymap_get_type ())
G_DECLARE_FINAL_TYPE (GdkIOSKeymap, gdk_ios_keymap, GDK, IOS_KEYMAP, GdkKeymap)

#define GDK_TYPE_IOS_SURFACE (gdk_ios_surface_get_type ())
G_DECLARE_DERIVABLE_TYPE (GdkIOSSurface, gdk_ios_surface, GDK, IOS_SURFACE, GdkSurface)

#define GDK_TYPE_IOS_TOPLEVEL (gdk_ios_toplevel_get_type ())
G_DECLARE_FINAL_TYPE (GdkIOSToplevel, gdk_ios_toplevel, GDK, IOS_TOPLEVEL, GdkIOSSurface)

#define GDK_TYPE_IOS_POPUP (gdk_ios_popup_get_type ())
G_DECLARE_FINAL_TYPE (GdkIOSPopup, gdk_ios_popup, GDK, IOS_POPUP, GdkIOSSurface)

#define GDK_TYPE_IOS_CAIRO_CONTEXT (gdk_ios_cairo_context_get_type ())
G_DECLARE_FINAL_TYPE (GdkIOSCairoContext, gdk_ios_cairo_context, GDK, IOS_CAIRO_CONTEXT, GdkCairoContext)

/* ------------------------------------------------------------- structures */

struct _GdkIOSDisplay
{
  GdkDisplay parent_instance;

  GdkIOSMonitor *monitor;
  GListStore *monitors;      /* of GdkMonitor */
  GdkSeat *seat;
  GdkKeymap *keymap;
  GdkDevice *core_pointer;
  GdkDevice *core_keyboard;

  GList *toplevels;          /* of GdkIOSSurface, most recent first */

  guint32 next_serial;
};

struct _GdkIOSSurfaceClass
{
  GdkSurfaceClass parent_class;
};

/* Per-surface backend data lives in a private struct because
 * GdkIOSSurface is derivable (toplevel/popup subclass it). */
typedef struct
{
  gpointer layer;            /* CALayer*, owned (bridged retained) */
  double scale;              /* backing scale factor */
  gboolean visible;
} GdkIOSSurfacePrivate;

GdkIOSSurfacePrivate *gdk_ios_surface_get_private (GdkIOSSurface *self);

/* ------------------------------------------------------------ entrypoints */

GdkDisplay *_gdk_ios_display_open (const char *display_name);

/* internal helpers shared between compilation units */
GdkIOSDisplay *gdk_ios_display_get_instance (void);

void gdk_ios_surface_attach_layer (GdkIOSSurface *self);
void gdk_ios_surface_detach_layer (GdkIOSSurface *self);
void gdk_ios_surface_apply_frame  (GdkIOSSurface *self,
                                   int x, int y, int width, int height);

/* UIKit shell (gdkiosmain.m) */
gboolean   gdk_ios_shell_is_ready (void);
gpointer   gdk_ios_shell_get_root_layer (void);  /* CALayer* of the root view */
double     gdk_ios_shell_get_scale (void);
void       gdk_ios_shell_get_bounds (int *width, int *height); /* points */
void       gdk_ios_shell_get_pointer_position (double *x, double *y,
                                               GdkModifierType *mask);

/* Event helpers (gdkiosmain.m -> display) */
void gdk_ios_display_deliver_event (GdkIOSDisplay *display, GdkEvent *event);
GdkIOSSurface *gdk_ios_display_surface_at (GdkIOSDisplay *display,
                                           double x, double y,
                                           double *local_x, double *local_y);

G_END_DECLS
