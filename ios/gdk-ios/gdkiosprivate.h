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
 * Types are declared manually (android-backend style) rather than with
 * G_DECLARE_*: several parents (GdkKeymap, GdkCairoContext) are private
 * GDK classes without autoptr support, which G_DECLARE_FINAL_TYPE
 * requires of the parent.
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

typedef struct _GdkIOSDisplay GdkIOSDisplay;
typedef struct _GdkIOSDisplayClass GdkIOSDisplayClass;
#define GDK_TYPE_IOS_DISPLAY (gdk_ios_display_get_type ())
#define GDK_IOS_DISPLAY(o) (G_TYPE_CHECK_INSTANCE_CAST ((o), GDK_TYPE_IOS_DISPLAY, GdkIOSDisplay))
#define GDK_IS_IOS_DISPLAY(o) (G_TYPE_CHECK_INSTANCE_TYPE ((o), GDK_TYPE_IOS_DISPLAY))
GType gdk_ios_display_get_type (void);
void _gdk_ios_display_bounds_changed (void);

typedef struct _GdkIOSMonitor GdkIOSMonitor;
typedef struct _GdkIOSMonitorClass GdkIOSMonitorClass;
#define GDK_TYPE_IOS_MONITOR (gdk_ios_monitor_get_type ())
#define GDK_IOS_MONITOR(o) (G_TYPE_CHECK_INSTANCE_CAST ((o), GDK_TYPE_IOS_MONITOR, GdkIOSMonitor))
#define GDK_IS_IOS_MONITOR(o) (G_TYPE_CHECK_INSTANCE_TYPE ((o), GDK_TYPE_IOS_MONITOR))
GType gdk_ios_monitor_get_type (void);

typedef struct _GdkIOSDevice GdkIOSDevice;
typedef struct _GdkIOSDeviceClass GdkIOSDeviceClass;
#define GDK_TYPE_IOS_DEVICE (gdk_ios_device_get_type ())
#define GDK_IOS_DEVICE(o) (G_TYPE_CHECK_INSTANCE_CAST ((o), GDK_TYPE_IOS_DEVICE, GdkIOSDevice))
#define GDK_IS_IOS_DEVICE(o) (G_TYPE_CHECK_INSTANCE_TYPE ((o), GDK_TYPE_IOS_DEVICE))
GType gdk_ios_device_get_type (void);

typedef struct _GdkIOSKeymap GdkIOSKeymap;
typedef struct _GdkIOSKeymapClass GdkIOSKeymapClass;
#define GDK_TYPE_IOS_KEYMAP (gdk_ios_keymap_get_type ())
#define GDK_IOS_KEYMAP(o) (G_TYPE_CHECK_INSTANCE_CAST ((o), GDK_TYPE_IOS_KEYMAP, GdkIOSKeymap))
#define GDK_IS_IOS_KEYMAP(o) (G_TYPE_CHECK_INSTANCE_TYPE ((o), GDK_TYPE_IOS_KEYMAP))
GType gdk_ios_keymap_get_type (void);

typedef struct _GdkIOSSurface GdkIOSSurface;
typedef struct _GdkIOSSurfaceClass GdkIOSSurfaceClass;
#define GDK_TYPE_IOS_SURFACE (gdk_ios_surface_get_type ())
#define GDK_IOS_SURFACE(o) (G_TYPE_CHECK_INSTANCE_CAST ((o), GDK_TYPE_IOS_SURFACE, GdkIOSSurface))
#define GDK_IS_IOS_SURFACE(o) (G_TYPE_CHECK_INSTANCE_TYPE ((o), GDK_TYPE_IOS_SURFACE))
GType gdk_ios_surface_get_type (void);

typedef struct _GdkIOSToplevel GdkIOSToplevel;
typedef struct _GdkIOSToplevelClass GdkIOSToplevelClass;
#define GDK_TYPE_IOS_TOPLEVEL (gdk_ios_toplevel_get_type ())
#define GDK_IOS_TOPLEVEL(o) (G_TYPE_CHECK_INSTANCE_CAST ((o), GDK_TYPE_IOS_TOPLEVEL, GdkIOSToplevel))
#define GDK_IS_IOS_TOPLEVEL(o) (G_TYPE_CHECK_INSTANCE_TYPE ((o), GDK_TYPE_IOS_TOPLEVEL))
GType gdk_ios_toplevel_get_type (void);

typedef struct _GdkIOSPopup GdkIOSPopup;
typedef struct _GdkIOSPopupClass GdkIOSPopupClass;
#define GDK_TYPE_IOS_POPUP (gdk_ios_popup_get_type ())
#define GDK_IOS_POPUP(o) (G_TYPE_CHECK_INSTANCE_CAST ((o), GDK_TYPE_IOS_POPUP, GdkIOSPopup))
#define GDK_IS_IOS_POPUP(o) (G_TYPE_CHECK_INSTANCE_TYPE ((o), GDK_TYPE_IOS_POPUP))
GType gdk_ios_popup_get_type (void);

typedef struct _GdkIOSCairoContext GdkIOSCairoContext;
typedef struct _GdkIOSCairoContextClass GdkIOSCairoContextClass;
#define GDK_TYPE_IOS_CAIRO_CONTEXT (gdk_ios_cairo_context_get_type ())
#define GDK_IOS_CAIRO_CONTEXT(o) (G_TYPE_CHECK_INSTANCE_CAST ((o), GDK_TYPE_IOS_CAIRO_CONTEXT, GdkIOSCairoContext))
#define GDK_IS_IOS_CAIRO_CONTEXT(o) (G_TYPE_CHECK_INSTANCE_TYPE ((o), GDK_TYPE_IOS_CAIRO_CONTEXT))
GType gdk_ios_cairo_context_get_type (void);

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

struct _GdkIOSDisplayClass
{
  GdkDisplayClass parent_class;
};

/* Derivable: toplevel and popup subclass this, so instance and class
 * structs are visible here. Backend data lives directly in the instance
 * struct (no gobject private needed with manual declarations). */
struct _GdkIOSSurface
{
  GdkSurface parent_instance;

  gpointer layer;            /* CALayer*, owned (bridged retained) */
  double scale;              /* backing scale factor */
  gboolean visible;
};

struct _GdkIOSSurfaceClass
{
  GdkSurfaceClass parent_class;
};

/* ------------------------------------------------------------ entrypoints */

GdkDisplay *_gdk_ios_display_open (const char *display_name);

/* internal helpers shared between compilation units */
GdkIOSDisplay *gdk_ios_display_get_instance (void);

void gdk_ios_surface_attach_layer (GdkIOSSurface *self);
void gdk_ios_surface_detach_layer (GdkIOSSurface *self);
void gdk_ios_surface_apply_frame  (GdkIOSSurface *self,
                                   int x, int y, int width, int height);

/* UIKit shell (gdkiosmain.c) */
gboolean   gdk_ios_shell_is_ready (void);
gpointer   gdk_ios_shell_get_root_layer (void);  /* CALayer* of the root view */
double     gdk_ios_shell_get_scale (void);
void       gdk_ios_shell_get_bounds (int *width, int *height); /* points */
double     gdk_ios_shell_get_fit_scale (void);
void       gdk_ios_shell_set_min_width (int min_width);
void       gdk_ios_shell_get_pointer_position (double *x, double *y,
                                               GdkModifierType *mask);

/* Event helpers (gdkiosmain.c -> display) */
void gdk_ios_display_deliver_event (GdkIOSDisplay *display, GdkEvent *event);
GdkIOSSurface *gdk_ios_display_surface_at (GdkIOSDisplay *display,
                                           double x, double y,
                                           double *local_x, double *local_y);

G_END_DECLS
