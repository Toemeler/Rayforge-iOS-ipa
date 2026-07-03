/*
 * main-adw.c — Libadwaita iOS smoke test.
 *
 * Exercises the full Application path Rayforge needs: AdwApplication is
 * created inside the gdk_ios_main() callback and started with
 * gdk_ios_application_run() (NOT g_application_run(), whose blocking
 * loop would stall the UIKit run loop — the backend's CADisplayLink
 * pump is the main loop). ::startup triggers adw_init() (stylesheet,
 * style manager), ::activate builds an AdwApplicationWindow with
 * headerbar, toast overlay and typical Adwaita widgets.
 *
 * SPDX-License-Identifier: LGPL-2.1-or-later
 */

#include <adwaita.h>
#include <gdk/ios/gdkios.h>

static AdwToastOverlay *toast_overlay = NULL;

static void
button_clicked_cb (GtkButton *button,
                   gpointer   user_data)
{
  adw_toast_overlay_add_toast (toast_overlay,
                               adw_toast_new ("Toast from Libadwaita on iOS"));
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
                                   adw_window_title_new ("Libadwaita on iOS",
                                                         "GTK 4 + Adwaita, native"));
  adw_toolbar_view_add_top_bar (ADW_TOOLBAR_VIEW (toolbar_view), header);

  GtkWidget *overlay = adw_toast_overlay_new ();
  toast_overlay = ADW_TOAST_OVERLAY (overlay);

  GtkWidget *page = adw_preferences_page_new ();
  GtkWidget *group = adw_preferences_group_new ();
  adw_preferences_group_set_title (ADW_PREFERENCES_GROUP (group),
                                   "Libadwaita running natively on iOS");
  adw_preferences_group_set_description (ADW_PREFERENCES_GROUP (group),
                                         "AdwApplication started via gdk_ios_application_run()");

  GtkWidget *row1 = adw_switch_row_new ();
  adw_preferences_row_set_title (ADW_PREFERENCES_ROW (row1), "Switch row");
  adw_switch_row_set_active (ADW_SWITCH_ROW (row1), TRUE);
  adw_preferences_group_add (ADW_PREFERENCES_GROUP (group), row1);

  GtkWidget *row2 = adw_entry_row_new ();
  adw_preferences_row_set_title (ADW_PREFERENCES_ROW (row2), "Entry row");
  adw_preferences_group_add (ADW_PREFERENCES_GROUP (group), row2);

  GtkWidget *row3 = adw_action_row_new ();
  adw_preferences_row_set_title (ADW_PREFERENCES_ROW (row3), "Show a toast");
  GtkWidget *button = gtk_button_new_with_label ("Toast");
  gtk_widget_set_valign (button, GTK_ALIGN_CENTER);
  g_signal_connect (button, "clicked", G_CALLBACK (button_clicked_cb), NULL);
  adw_action_row_add_suffix (ADW_ACTION_ROW (row3), button);
  adw_preferences_group_add (ADW_PREFERENCES_GROUP (group), row3);

  adw_preferences_page_add (ADW_PREFERENCES_PAGE (page),
                            ADW_PREFERENCES_GROUP (group));

  adw_toast_overlay_set_child (ADW_TOAST_OVERLAY (overlay), page);
  adw_toolbar_view_set_content (ADW_TOOLBAR_VIEW (toolbar_view), overlay);
  adw_application_window_set_content (ADW_APPLICATION_WINDOW (window),
                                      toolbar_view);

  gtk_window_present (GTK_WINDOW (window));

  g_message ("adw smoke test UI presented");
}

static void
build_app (gpointer user_data)
{
  AdwApplication *app = adw_application_new ("org.rayforge.adwtest",
                                             G_APPLICATION_DEFAULT_FLAGS);
  g_signal_connect (app, "activate", G_CALLBACK (activate_cb), NULL);

  int status = gdk_ios_application_run (G_APPLICATION (app));
  g_message ("adw smoke test: gdk_ios_application_run -> %d", status);
}

int
main (int argc, char **argv)
{
  return gdk_ios_main (argc, argv, build_app, NULL);
}
