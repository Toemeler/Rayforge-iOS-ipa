/*
 * main-pygi.c — PyGObject + pycairo iOS self-test (Step 10).
 *
 * Boots UIKit via gdk_ios_main(), starts an AdwApplication via
 * gdk_ios_application_run(), initializes the embedded CPython (BeeWare
 * Python-Apple-support framework), then runs a self-test that exercises
 * the whole binding stack cross-compiled for iOS:
 *   import gi; gi.require_version('Gtk','4.0'); from gi.repository import
 *   Gtk, Adw, GLib, Gio; import cairo; and instantiates GObjects FROM
 *   PYTHON (Gtk.Label / Adw.WindowTitle) — that round-trip through
 *   libgirepository + libffi is the real proof that PyGObject works, not
 *   just that the .so loads.
 *
 * "PYGOBJECT OK" on stdout/os_log is the success marker. The Adw window
 * is shown for the screenshot; the description reflects the test result.
 *
 * GI_TYPELIB_PATH must point at the bundled typelibs BEFORE Python (and
 * thus girepository) initializes — iOS apps start with an empty
 * environment. The extension modules (gi, cairo) live in
 * python/lib/pythonX.Y/site-packages, added to the module search path
 * below.
 *
 * SPDX-License-Identifier: LGPL-2.1-or-later
 */

#include <adwaita.h>
#include <gdk/ios/gdkios.h>
#include <CoreFoundation/CoreFoundation.h>
#include <Python.h>
#include <limits.h>

static char *
bundle_resource_path (void)
{
  CFBundleRef bundle = CFBundleGetMainBundle ();
  CFURLRef url = CFBundleCopyResourcesDirectoryURL (bundle);
  char buf[PATH_MAX];

  if (url == NULL ||
      !CFURLGetFileSystemRepresentation (url, true, (UInt8 *) buf, sizeof buf))
    {
      if (url != NULL)
        CFRelease (url);
      return g_strdup (".");
    }
  CFRelease (url);
  return g_strdup (buf);
}

/* The self-test program. Kept in C as a literal so the whole thing can be
 * iterated without shipping a script; prints a single PYGOBJECT OK line on
 * success and a PYGOBJECT FAIL line (plus traceback) otherwise. */
static const char *SELFTEST =
  "import sys\n"
  "print('py', sys.version.replace(chr(10), ' '), 'platform', sys.platform)\n"
  "print('sys.path =', sys.path)\n"
  "import os\n"
  "print('GI_TYPELIB_PATH =', os.environ.get('GI_TYPELIB_PATH'))\n"
  "try:\n"
  "    import gi\n"
  "    print('gi from', gi.__file__)\n"
  "    gi.require_version('Gtk', '4.0')\n"
  "    gi.require_version('Adw', '1')\n"
  "    from gi.repository import GLib, GObject, Gio, Gtk, Adw\n"
  "    import cairo\n"
  "    print('cairo from', cairo.__file__, 'version', cairo.version)\n"
  "    # Instantiate GObjects from Python: this round-trips through\n"
  "    # libgirepository + libffi (constructor marshalling), the real test.\n"
  "    label = Gtk.Label(label='hello from python')\n"
  "    print('Gtk.Label ->', label, 'text=', label.get_text())\n"
  "    title = Adw.WindowTitle(title='T', subtitle='S')\n"
  "    print('Adw.WindowTitle ->', title, 'title=', title.get_title())\n"
  "    # A tiny cairo surface exercises the pycairo C extension too.\n"
  "    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 8, 8)\n"
  "    ctx = cairo.Context(surf)\n"
  "    ctx.rectangle(0, 0, 8, 8)\n"
  "    ctx.fill()\n"
  "    print('cairo surface ->', surf.get_width(), 'x', surf.get_height())\n"
  "    print('PYGOBJECT OK')\n"
  "except Exception:\n"
  "    import traceback\n"
  "    traceback.print_exc()\n"
  "    print('PYGOBJECT FAIL')\n";

/* Returns a newly allocated status string for the UI. */
static char *
init_python (void)
{
  PyStatus status;
  PyPreConfig preconfig;
  PyConfig config;
  char *res = bundle_resource_path ();
  char *home = g_build_filename (res, "python", NULL);
  char *stdlib_path = g_strdup_printf ("%s/lib/python%d.%d", home,
                                       PY_MAJOR_VERSION, PY_MINOR_VERSION);
  char *dynload_path = g_strdup_printf ("%s/lib-dynload", stdlib_path);
  char *sitepkg_path = g_strdup_printf ("%s/site-packages", stdlib_path);
  char *typelib_path = g_build_filename (res, "lib", "girepository-1.0", NULL);
  char *result = NULL;
  wchar_t *w;

  /* girepository reads GI_TYPELIB_PATH at init; set before Py starts. */
  g_setenv ("GI_TYPELIB_PATH", typelib_path, TRUE);
  g_message ("GI_TYPELIB_PATH: %s", typelib_path);
  g_message ("python home: %s", home);
  g_message ("site-packages: %s", sitepkg_path);

  PyConfig_InitIsolatedConfig (&config);

  PyPreConfig_InitIsolatedConfig (&preconfig);
  preconfig.utf8_mode = 1;
  status = Py_PreInitialize (&preconfig);
  if (PyStatus_Exception (status))
    goto fail;

  status = PyConfig_SetBytesString (&config, &config.home, home);
  if (PyStatus_Exception (status))
    goto fail;

  /* Explicit module search path (isolated config does not autocompute
   * reliably on iOS): stdlib, lib-dynload, then our site-packages. */
  config.module_search_paths_set = 1;
  w = Py_DecodeLocale (stdlib_path, NULL);
  status = PyWideStringList_Append (&config.module_search_paths, w);
  PyMem_RawFree (w);
  if (PyStatus_Exception (status))
    goto fail;
  w = Py_DecodeLocale (dynload_path, NULL);
  status = PyWideStringList_Append (&config.module_search_paths, w);
  PyMem_RawFree (w);
  if (PyStatus_Exception (status))
    goto fail;
  w = Py_DecodeLocale (sitepkg_path, NULL);
  status = PyWideStringList_Append (&config.module_search_paths, w);
  PyMem_RawFree (w);
  if (PyStatus_Exception (status))
    goto fail;

  config.buffered_stdio = 0;

  status = Py_InitializeFromConfig (&config);
  if (PyStatus_Exception (status))
    goto fail;

  PyConfig_Clear (&config);

  if (PyRun_SimpleString (SELFTEST) != 0)
    {
      result = g_strdup ("Python self-test raised at top level (see log)");
      goto out;
    }

  result = g_strdup_printf ("PyGObject self-test ran (CPython %s) — "
                            "see console for PYGOBJECT OK/FAIL",
                            Py_GetVersion ());
  goto out;

fail:
  g_critical ("python init failed: %s",
              status.err_msg != NULL ? status.err_msg : "unknown");
  result = g_strdup_printf ("Python init FAILED: %s",
                            status.err_msg != NULL ? status.err_msg : "?");
  PyConfig_Clear (&config);

out:
  g_free (res);
  g_free (home);
  g_free (stdlib_path);
  g_free (dynload_path);
  g_free (sitepkg_path);
  g_free (typelib_path);
  return result;
}

static void
activate_cb (GApplication *app,
             gpointer      user_data)
{
  GtkWidget *window = adw_application_window_new (GTK_APPLICATION (app));
  gtk_window_set_title (GTK_WINDOW (window), "Rayforge iOS");

  GtkWidget *toolbar_view = adw_toolbar_view_new ();
  GtkWidget *header = adw_header_bar_new ();
  adw_header_bar_set_title_widget (ADW_HEADER_BAR (header),
                                   adw_window_title_new ("PyGObject on iOS",
                                                         "gi + cairo bound to the iOS GTK stack"));
  adw_toolbar_view_add_top_bar (ADW_TOOLBAR_VIEW (toolbar_view), header);

  GtkWidget *page = adw_status_page_new ();
  adw_status_page_set_title (ADW_STATUS_PAGE (page),
                             "PyGObject running natively on iOS");

  char *pystatus = init_python ();
  adw_status_page_set_description (ADW_STATUS_PAGE (page), pystatus);
  g_free (pystatus);

  adw_toolbar_view_set_content (ADW_TOOLBAR_VIEW (toolbar_view), page);
  adw_application_window_set_content (ADW_APPLICATION_WINDOW (window),
                                      toolbar_view);
  gtk_window_present (GTK_WINDOW (window));

  g_message ("pygobject self-test UI presented");
}

static void
build_app (gpointer user_data)
{
  AdwApplication *app = adw_application_new ("org.rayforge.pygitest",
                                             G_APPLICATION_DEFAULT_FLAGS);
  g_signal_connect (app, "activate", G_CALLBACK (activate_cb), NULL);
  gdk_ios_application_run (G_APPLICATION (app));
}

int
main (int argc, char **argv)
{
  return gdk_ios_main (argc, argv, build_app, NULL);
}
