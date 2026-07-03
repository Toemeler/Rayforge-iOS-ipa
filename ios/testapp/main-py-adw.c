/*
 * main-py-adw.c — CPython + Libadwaita iOS smoke test (Step 8).
 *
 * Boots UIKit via gdk_ios_main(), starts an AdwApplication via
 * gdk_ios_application_run(), then initializes an embedded CPython
 * (BeeWare Python-Apple-support framework, PYTHONHOME inside the app
 * bundle at Resources/python) and shows sys.version in the UI. Python
 * output goes to stdout, which the CI captures via simctl launch
 * --stdout, so "PYTHON OK" in app-console.log is the success marker.
 *
 * Pure C: the bundle path comes from CoreFoundation (no ObjC needed).
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

/* Returns a newly allocated status string for the UI. */
static char *
init_python (void)
{
  PyStatus status;
  PyConfig config;
  char *res = bundle_resource_path ();
  char *home = g_build_filename (res, "python", NULL);
  char *result;

  g_message ("python home: %s", home);

  PyConfig_InitIsolatedConfig (&config);
  status = PyConfig_SetBytesString (&config, &config.home, home);
  if (PyStatus_Exception (status))
    goto fail;

  /* stdout/stderr unbuffered so the CI log capture sees prints. */
  config.buffered_stdio = 0;

  status = Py_InitializeFromConfig (&config);
  if (PyStatus_Exception (status))
    goto fail;

  PyConfig_Clear (&config);

  PyRun_SimpleString (
    "import sys\n"
    "print('PYTHON OK', sys.version.replace('\\n', ' '))\n"
    "print('sys.platform =', sys.platform)\n"
    "print('sys.path =', sys.path)\n");

  result = g_strdup_printf ("CPython %s initialized", Py_GetVersion ());
  g_free (res);
  g_free (home);
  return result;

fail:
  g_critical ("python init failed: %s",
              status.err_msg != NULL ? status.err_msg : "unknown");
  result = g_strdup_printf ("Python init FAILED: %s",
                            status.err_msg != NULL ? status.err_msg : "?");
  PyConfig_Clear (&config);
  g_free (res);
  g_free (home);
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
                                   adw_window_title_new ("CPython on iOS",
                                                         "GTK 4 + Adwaita + Python, native"));
  adw_toolbar_view_add_top_bar (ADW_TOOLBAR_VIEW (toolbar_view), header);

  GtkWidget *page = adw_status_page_new ();
  adw_status_page_set_title (ADW_STATUS_PAGE (page),
                             "Python running natively on iOS");

  char *pystatus = init_python ();
  adw_status_page_set_description (ADW_STATUS_PAGE (page), pystatus);
  g_free (pystatus);

  adw_toolbar_view_set_content (ADW_TOOLBAR_VIEW (toolbar_view), page);
  adw_application_window_set_content (ADW_APPLICATION_WINDOW (window),
                                      toolbar_view);
  gtk_window_present (GTK_WINDOW (window));

  g_message ("python smoke test UI presented");
}

static void
build_app (gpointer user_data)
{
  AdwApplication *app = adw_application_new ("org.rayforge.pytest",
                                             G_APPLICATION_DEFAULT_FLAGS);
  g_signal_connect (app, "activate", G_CALLBACK (activate_cb), NULL);
  gdk_ios_application_run (G_APPLICATION (app));
}

int
main (int argc, char **argv)
{
  return gdk_ios_main (argc, argv, build_app, NULL);
}
