/*
 * appstream.h — minimal appstream stub for the iOS libadwaita build.
 *
 * libadwaita uses appstream ONLY inside adw_about_{dialog,window}_
 * new_from_appdata() to parse a metainfo XML into version/name/url
 * fields. Cross-compiling real appstream (libxmlb, libcurl, ...) for
 * iOS is not worth it for that one convenience constructor, so this
 * stub satisfies the compile and returns empty-but-safe values: the
 * about dialog still works, it just starts blank when constructed from
 * appdata (all setters remain fully functional).
 *
 * Every declaration below is matched to the call sites in libadwaita
 * 1.9.x (adw-about-dialog.c / adw-about-window.c).
 *
 * SPDX-License-Identifier: LGPL-2.1-or-later
 */

#pragma once

#include <glib.h>
#include <glib-object.h>
#include <gio/gio.h>

G_BEGIN_DECLS

#define AS_MAJOR_VERSION 1
#define AS_MINOR_VERSION 0
#define AS_MICRO_VERSION 99
/* Always take the modern (>= 1.0) code paths in libadwaita. */
#define AS_CHECK_VERSION(major,minor,micro) \
  ((major) < AS_MAJOR_VERSION || \
   ((major) == AS_MAJOR_VERSION && (minor) < AS_MINOR_VERSION) || \
   ((major) == AS_MAJOR_VERSION && (minor) == AS_MINOR_VERSION && \
    (micro) <= AS_MICRO_VERSION))

typedef struct _AsMetadata    AsMetadata;
typedef struct _AsComponent   AsComponent;
typedef struct _AsRelease     AsRelease;
typedef struct _AsReleaseList AsReleaseList;
typedef struct _AsLaunchable  AsLaunchable;
typedef struct _AsDeveloper   AsDeveloper;

typedef enum {
  AS_FORMAT_KIND_UNKNOWN = 0,
  AS_FORMAT_KIND_XML,
  AS_FORMAT_KIND_YAML
} AsFormatKind;

typedef enum {
  AS_LAUNCHABLE_KIND_UNKNOWN = 0,
  AS_LAUNCHABLE_KIND_DESKTOP_ID
} AsLaunchableKind;

typedef enum {
  AS_URL_KIND_UNKNOWN = 0,
  AS_URL_KIND_HOMEPAGE,
  AS_URL_KIND_BUGTRACKER,
  AS_URL_KIND_FAQ,
  AS_URL_KIND_HELP,
  AS_URL_KIND_DONATION,
  AS_URL_KIND_TRANSLATE,
  AS_URL_KIND_CONTACT,
  AS_URL_KIND_VCS_BROWSER,
  AS_URL_KIND_CONTRIBUTE
} AsUrlKind;

AsMetadata    *as_metadata_new                     (void);
gboolean       as_metadata_parse_file              (AsMetadata    *metadata,
                                                    GFile         *file,
                                                    AsFormatKind   format,
                                                    GError       **error);
AsComponent   *as_metadata_get_component           (AsMetadata    *metadata);

const gchar   *as_component_get_id                 (AsComponent   *component);
const gchar   *as_component_get_name               (AsComponent   *component);
const gchar   *as_component_get_project_license    (AsComponent   *component);
const gchar   *as_component_get_url                (AsComponent   *component,
                                                    AsUrlKind      kind);
const gchar   *as_component_get_developer_name     (AsComponent   *component);
AsDeveloper   *as_component_get_developer          (AsComponent   *component);
AsLaunchable  *as_component_get_launchable         (AsComponent   *component,
                                                    AsLaunchableKind kind);
AsReleaseList *as_component_get_releases_plain     (AsComponent   *component);
GPtrArray     *as_component_get_releases           (AsComponent   *component);

const gchar   *as_developer_get_name               (AsDeveloper   *developer);

GPtrArray     *as_launchable_get_entries           (AsLaunchable  *launchable);

GPtrArray     *as_release_list_get_entries         (AsReleaseList *list);
const gchar   *as_release_get_version              (AsRelease     *release);
const gchar   *as_release_get_description          (AsRelease     *release);

G_END_DECLS
