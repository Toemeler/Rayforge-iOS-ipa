# gdk/ios/meson.build — GDK iOS backend.
#
# Objective-C is compiled through the C compiler with -xobjective-c, the
# same technique the macos backend uses, so no separate language setup is
# required. ARC is enabled because the backend uses __bridge_retained /
# __bridge_transfer ownership transfers; the flags are scoped to this
# static library only.

gdk_ios_sources = files([
  'gdkiosdisplay.c',
  'gdkiossurface.c',
  'gdkioscairocontext.c',
  'gdkiosmain.c',
])

gdk_ios_public_headers = files([
  'gdkios.h',
])

install_headers(gdk_ios_public_headers, subdir: 'gtk-4.0/gdk/ios/')

# Link the UIKit stack directly instead of probing via the
# 'appleframeworks' dependency machinery, which is unreliable when
# cross-compiling for iOS.
gdk_ios_deps = [
  declare_dependency(link_args: [
    '-framework', 'UIKit',
    '-framework', 'QuartzCore',
    '-framework', 'CoreGraphics',
    '-framework', 'CoreFoundation',
    '-framework', 'Foundation',
  ]),
]

libgdk_ios = static_library('gdk-ios',
  sources: [ gdk_ios_sources, gdk_gen_headers ],
  include_directories: [ confinc, gdkinc, ],
  c_args: [ libgdk_c_args, common_cflags, '-xobjective-c', '-fobjc-arc', ],
  dependencies: [ gdk_deps, gdk_ios_deps, ],
)
