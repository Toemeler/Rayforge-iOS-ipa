/*
 * appstream-stub.c — implementation of the minimal appstream stub for
 * the iOS libadwaita build (see appstream.h in this directory).
 *
 * Semantics were chosen against libadwaita's actual call sites so that
 * adw_about_*_new_from_appdata() completes without crashing or calling
 * g_error():
 *  - as_metadata_parse_file() must SUCCEED (a FALSE return makes
 *    libadwaita call g_error(), which aborts).
 *  - as_metadata_get_component() must return non-NULL (same reason).
 *  - as_component_get_id() must return a non-NULL string (result is
 *    g_strdup'd and fed to g_str_has_suffix()).
 *  - release lists are shared empty GPtrArrays; libadwaita only reads
 *    them ("->len", find, index) and never frees them.
 *  - everything else may return NULL: all those results are
 *    NULL-checked by libadwaita before use.
 *
 * SPDX-License-Identifier: LGPL-2.1-or-later
 */

#include "appstream.h"

/* AsMetadata must be a real GObject: libadwaita g_object_unref()s it. */
AsMetadata *
as_metadata_new (void)
{
  return (AsMetadata *) g_object_new (G_TYPE_OBJECT, NULL);
}

gboolean
as_metadata_parse_file (AsMetadata    *metadata,
                        GFile         *file,
                        AsFormatKind   format,
                        GError       **error)
{
  (void) metadata; (void) file; (void) format; (void) error;
  g_message ("appstream-stub: metainfo parsing is stubbed out on iOS; "
             "about dialog fields from appdata will be empty");
  return TRUE;
}

/* Non-NULL opaque token; never dereferenced by libadwaita, only passed
 * back into the as_component_* accessors below. */
AsComponent *
as_metadata_get_component (AsMetadata *metadata)
{
  static int dummy_component;
  (void) metadata;
  return (AsComponent *) &dummy_component;
}

const gchar *
as_component_get_id (AsComponent *component)
{
  (void) component;
  return "org.rayforge.app";
}

const gchar *
as_component_get_name (AsComponent *component)
{
  (void) component;
  return NULL;
}

const gchar *
as_component_get_project_license (AsComponent *component)
{
  (void) component;
  return NULL;
}

const gchar *
as_component_get_url (AsComponent *component,
                      AsUrlKind    kind)
{
  (void) component; (void) kind;
  return NULL;
}

const gchar *
as_component_get_developer_name (AsComponent *component)
{
  (void) component;
  return NULL;
}

AsDeveloper *
as_component_get_developer (AsComponent *component)
{
  (void) component;
  return NULL;
}

const gchar *
as_developer_get_name (AsDeveloper *developer)
{
  (void) developer;
  return NULL;
}

AsLaunchable *
as_component_get_launchable (AsComponent      *component,
                             AsLaunchableKind  kind)
{
  (void) component; (void) kind;
  return NULL;
}

/* Never reached (get_launchable returns NULL and libadwaita checks),
 * but must exist for the link. */
GPtrArray *
as_launchable_get_entries (AsLaunchable *launchable)
{
  (void) launchable;
  return NULL;
}

static GPtrArray *
empty_release_array (void)
{
  static GPtrArray *empty = NULL;
  if (g_once_init_enter (&empty))
    g_once_init_leave (&empty, g_ptr_array_new ());
  return empty;
}

AsReleaseList *
as_component_get_releases_plain (AsComponent *component)
{
  static int dummy_list;
  (void) component;
  return (AsReleaseList *) &dummy_list;
}

GPtrArray *
as_release_list_get_entries (AsReleaseList *list)
{
  (void) list;
  return empty_release_array ();
}

GPtrArray *
as_component_get_releases (AsComponent *component)
{
  (void) component;
  return empty_release_array ();
}

const gchar *
as_release_get_version (AsRelease *release)
{
  (void) release;
  return NULL;
}

const gchar *
as_release_get_description (AsRelease *release)
{
  (void) release;
  return NULL;
}
