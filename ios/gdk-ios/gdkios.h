/*
 * gdkios.h — public entry point of the GDK iOS backend.
 *
 * iOS applications cannot own main(): UIKit must run UIApplicationMain on
 * the main thread. GTK applications therefore enter through
 * gdk_ios_main(), which boots UIKit, then invokes the supplied callback
 * (where the application calls gtk_init() and builds its UI) once the
 * platform shell is ready. The GLib main context is pumped from the UIKit
 * run loop, so everything runs on the main thread.
 *
 * SPDX-License-Identifier: LGPL-2.1-or-later
 */

#pragma once

#include <glib.h>

G_BEGIN_DECLS

typedef void (*GdkIOSMainFunc) (gpointer user_data);

int gdk_ios_main (int argc, char **argv,
                  GdkIOSMainFunc main_func, gpointer user_data);

G_END_DECLS
