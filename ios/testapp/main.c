/*
 * main.c — Rayforge iOS backend smoke test.
 *
 * Boots UIKit through gdk_ios_main(), then creates a plain GtkWindow with
 * visible content. Deliberately avoids g_application_run(): its blocking
 * GLib loop would stall the UIKit run loop. The backend's CADisplayLink
 * pump drives the GLib default context instead, so after gtk_init() +
 * gtk_window_present() everything is event-driven.
 *
 * SPDX-License-Identifier: LGPL-2.1-or-later
 */

#include <gtk/gtk.h>
#include <gdk/ios/gdkios.h>

static void
build_ui (gpointer user_data)
{
  gtk_init ();

  GtkWidget *window = gtk_window_new ();
  gtk_window_set_title (GTK_WINDOW (window), "Rayforge iOS");

  GtkWidget *box = gtk_box_new (GTK_ORIENTATION_VERTICAL, 24);
  gtk_widget_set_halign (box, GTK_ALIGN_CENTER);
  gtk_widget_set_valign (box, GTK_ALIGN_CENTER);

  GtkWidget *label = gtk_label_new (NULL);
  gtk_label_set_markup (GTK_LABEL (label),
                        "<span size='xx-large' weight='bold'>"
                        "GTK 4 running natively on iOS</span>");
  gtk_box_append (GTK_BOX (box), label);

  GtkWidget *button = gtk_button_new_with_label ("Click me (mouse works)");
  gtk_box_append (GTK_BOX (box), button);

  GtkWidget *entry = gtk_entry_new ();
  gtk_entry_set_placeholder_text (GTK_ENTRY (entry),
                                  "Type here (hardware keyboard works)");
  gtk_box_append (GTK_BOX (box), entry);

  gtk_window_set_child (GTK_WINDOW (window), box);
  gtk_window_present (GTK_WINDOW (window));

  g_message ("smoke test UI presented");
}

int
main (int argc, char **argv)
{
  return gdk_ios_main (argc, argv, build_ui, NULL);
}
