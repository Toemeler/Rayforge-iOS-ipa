#!/usr/bin/env bash
# build-base-stack.sh — builds the proven iOS arm64 base stack into $PREFIX:
#   glib -> pixman -> libpng -> freetype(x2)/harfbuzz -> fribidi -> expat
#   -> fontconfig -> cairo -> pango
#
# This encodes every fix discovered in Steps 1-2:
#   * brew meson/ninja (PEP 668)
#   * pkg_config_libdir isolation for GLib; prefix pkg-config for the rest
#   * PKG_CONFIG_SYSROOT_DIR= (empty) so prefix .pc -I paths aren't
#     SDK-prefixed
#   * SDK zlib via synthesized zlib.pc (GLib bundled zlib broken on iOS)
#   * libpng via CMake (no meson build upstream)
#   * freetype<->harfbuzz circular dep via 3-pass build
#   * fontconfig >= 2.17 (pango 1.58 requirement)
#   * cairo quartz backend disabled (macOS-only appleframeworks)
#   * pango --wrap-mode=nofallback
#
# Required env:
#   PREFIX       install prefix (created if missing)
#   CROSS_ISO    path to write the isolation cross-file (for GLib)
#   CROSS_PFX    path to write the prefix-aware cross-file (for the rest)
#   IOS_MIN      minimum iOS version (e.g. 17.0)
#   SCRIPT_DIR   directory containing gen-cross-file.sh
# Optional env (defaults are the proven-good pins):
#   GLIB_VERSION PIXMAN_VERSION LIBPNG_VERSION FREETYPE_VERSION
#   HARFBUZZ_VERSION FRIBIDI_VERSION EXPAT_VERSION FONTCONFIG_VERSION
#   CAIRO_VERSION PANGO_VERSION
set -euxo pipefail

: "${PREFIX:?PREFIX required}"
: "${CROSS_ISO:?CROSS_ISO required}"
: "${CROSS_PFX:?CROSS_PFX required}"
: "${IOS_MIN:?IOS_MIN required}"
: "${SCRIPT_DIR:?SCRIPT_DIR required}"

GLIB_VERSION="${GLIB_VERSION:-2.84.4}"
PIXMAN_VERSION="${PIXMAN_VERSION:-0.44.2}"
LIBPNG_VERSION="${LIBPNG_VERSION:-1.6.44}"
FREETYPE_VERSION="${FREETYPE_VERSION:-2.13.3}"
HARFBUZZ_VERSION="${HARFBUZZ_VERSION:-14.2.1}"
FRIBIDI_VERSION="${FRIBIDI_VERSION:-1.0.16}"
EXPAT_VERSION="${EXPAT_VERSION:-2.6.4}"
FONTCONFIG_VERSION="${FONTCONFIG_VERSION:-2.17.1}"
CAIRO_VERSION="${CAIRO_VERSION:-1.18.4}"
PANGO_VERSION="${PANGO_VERSION:-1.58.0}"

SDK="$(xcrun --sdk iphoneos --show-sdk-path)"
WORK="$(pwd)"

log() { echo "[base-stack] $*"; }

# ---------------------------------------------------------------- cross files
"${SCRIPT_DIR}/gen-cross-file.sh" "${CROSS_ISO}" "${IOS_MIN}"
mkdir -p "${PREFIX}/lib/pkgconfig"
"${SCRIPT_DIR}/gen-cross-file.sh" "${CROSS_PFX}" "${IOS_MIN}" "${PREFIX}/lib/pkgconfig"

# pkg-config env for everything after GLib.
export PKG_CONFIG_PATH="${PREFIX}/lib/pkgconfig"
export PKG_CONFIG_LIBDIR="${PREFIX}/lib/pkgconfig"
export PKG_CONFIG_SYSROOT_DIR=

# ---------------------------------------------------------------- zlib.pc
ZPC="${PREFIX}/lib/pkgconfig/zlib.pc"
: > "$ZPC"
printf 'prefix=%s/usr\n' "$SDK" >> "$ZPC"
printf 'exec_prefix=${prefix}\n' >> "$ZPC"
printf 'libdir=${exec_prefix}/lib\n' >> "$ZPC"
printf 'includedir=${prefix}/include\n' >> "$ZPC"
printf '\n' >> "$ZPC"
printf 'Name: zlib\n' >> "$ZPC"
printf 'Description: zlib compression library (iOS SDK)\n' >> "$ZPC"
printf 'Version: 1.2.12\n' >> "$ZPC"
printf 'Libs: -L${libdir} -lz\n' >> "$ZPC"
printf 'Cflags: -I${includedir}\n' >> "$ZPC"
pkg-config --exists zlib && log "zlib.pc OK"

# ---------------------------------------------------------------- glib
log "glib ${GLIB_VERSION}"
MAJMIN="$(echo "${GLIB_VERSION}" | cut -d. -f1,2)"
curl -fL --retry 3 -o glib.tar.xz \
  "https://download.gnome.org/sources/glib/${MAJMIN}/glib-${GLIB_VERSION}.tar.xz"
mkdir -p glib-src && tar xf glib.tar.xz --strip-components=1 -C glib-src
meson setup glib-build glib-src \
  --cross-file="${CROSS_ISO}" \
  --default-library=static --prefix="${PREFIX}" --buildtype=release \
  --force-fallback-for=pcre2,libffi \
  -Dtests=false -Dintrospection=disabled -Dlibmount=disabled \
  -Dselinux=disabled -Dxattr=false -Dman-pages=disabled -Dnls=disabled \
  -Dpcre2:jit=disabled \
  2>&1 | tee glib-setup.log
ninja -C glib-build install 2>&1 | tee glib-install.log

# ---------------------------------------------------------------- pixman
log "pixman ${PIXMAN_VERSION}"
curl -fL --retry 3 -o pixman.tar.gz \
  "https://www.cairographics.org/releases/pixman-${PIXMAN_VERSION}.tar.gz"
mkdir -p pixman-src && tar xf pixman.tar.gz --strip-components=1 -C pixman-src
meson setup pixman-build pixman-src \
  --cross-file="${CROSS_PFX}" \
  --default-library=static --prefix="${PREFIX}" --buildtype=release \
  -Dtests=disabled -Ddemos=disabled -Dgtk=disabled \
  2>&1 | tee pixman.log
ninja -C pixman-build install 2>&1 | tee -a pixman.log

# ---------------------------------------------------------------- libpng
log "libpng ${LIBPNG_VERSION}"
curl -fL --retry 3 -o libpng.tar.xz \
  "https://download.sourceforge.net/libpng/libpng-${LIBPNG_VERSION}.tar.xz"
mkdir -p libpng-src && tar xf libpng.tar.xz --strip-components=1 -C libpng-src
cmake -S libpng-src -B libpng-build \
  -DCMAKE_SYSTEM_NAME=iOS -DCMAKE_OSX_ARCHITECTURES=arm64 \
  -DCMAKE_OSX_SYSROOT="$SDK" -DCMAKE_OSX_DEPLOYMENT_TARGET="${IOS_MIN}" \
  -DCMAKE_INSTALL_PREFIX="${PREFIX}" \
  -DPNG_SHARED=OFF -DPNG_STATIC=ON -DPNG_FRAMEWORK=OFF \
  -DPNG_TESTS=OFF -DPNG_TOOLS=OFF -Dld-version-script=OFF \
  -DZLIB_LIBRARY="${SDK}/usr/lib/libz.tbd" \
  -DZLIB_INCLUDE_DIR="${SDK}/usr/include" \
  2>&1 | tee libpng.log
cmake --build libpng-build --config Release 2>&1 | tee -a libpng.log
cmake --install libpng-build --config Release 2>&1 | tee -a libpng.log

# ------------------------------------------- freetype x2 + harfbuzz sandwich
log "freetype ${FREETYPE_VERSION} pass 1"
curl -fL --retry 3 -o freetype.tar.xz \
  "https://download.savannah.gnu.org/releases/freetype/freetype-${FREETYPE_VERSION}.tar.xz"
mkdir -p freetype-src && tar xf freetype.tar.xz --strip-components=1 -C freetype-src
meson setup ft-build1 freetype-src \
  --cross-file="${CROSS_PFX}" \
  --default-library=static --prefix="${PREFIX}" --buildtype=release \
  -Dharfbuzz=disabled -Dbrotli=disabled -Dbzip2=disabled -Dpng=enabled \
  2>&1 | tee freetype1.log
ninja -C ft-build1 install 2>&1 | tee -a freetype1.log

log "harfbuzz ${HARFBUZZ_VERSION}"
curl -fL --retry 3 -o harfbuzz.tar.xz \
  "https://github.com/harfbuzz/harfbuzz/releases/download/${HARFBUZZ_VERSION}/harfbuzz-${HARFBUZZ_VERSION}.tar.xz"
mkdir -p harfbuzz-src && tar xf harfbuzz.tar.xz --strip-components=1 -C harfbuzz-src
meson setup hb-build harfbuzz-src \
  --cross-file="${CROSS_PFX}" \
  --default-library=static --prefix="${PREFIX}" --buildtype=release \
  -Dtests=disabled -Ddocs=disabled -Dutilities=disabled \
  -Dfreetype=enabled -Dglib=enabled -Dgobject=enabled -Dcairo=disabled \
  2>&1 | tee harfbuzz.log
ninja -C hb-build install 2>&1 | tee -a harfbuzz.log

log "freetype ${FREETYPE_VERSION} pass 2 (with harfbuzz)"
meson setup ft-build2 freetype-src \
  --cross-file="${CROSS_PFX}" \
  --default-library=static --prefix="${PREFIX}" --buildtype=release \
  -Dharfbuzz=enabled -Dbrotli=disabled -Dbzip2=disabled -Dpng=enabled \
  2>&1 | tee freetype2.log
ninja -C ft-build2 install 2>&1 | tee -a freetype2.log

# ---------------------------------------------------------------- fribidi
log "fribidi ${FRIBIDI_VERSION}"
curl -fL --retry 3 -o fribidi.tar.xz \
  "https://github.com/fribidi/fribidi/releases/download/v${FRIBIDI_VERSION}/fribidi-${FRIBIDI_VERSION}.tar.xz"
mkdir -p fribidi-src && tar xf fribidi.tar.xz --strip-components=1 -C fribidi-src
meson setup fribidi-build fribidi-src \
  --cross-file="${CROSS_PFX}" \
  --default-library=static --prefix="${PREFIX}" --buildtype=release \
  -Dtests=false -Ddocs=false -Dbin=false \
  2>&1 | tee fribidi.log
ninja -C fribidi-build install 2>&1 | tee -a fribidi.log

# ---------------------------------------------------------------- expat
log "expat ${EXPAT_VERSION}"
EXPAT_TAG="R_$(echo "${EXPAT_VERSION}" | tr '.' '_')"
curl -fL --retry 3 -o expat.tar.xz \
  "https://github.com/libexpat/libexpat/releases/download/${EXPAT_TAG}/expat-${EXPAT_VERSION}.tar.xz"
mkdir -p expat-src && tar xf expat.tar.xz --strip-components=1 -C expat-src
cmake -S expat-src -B expat-build \
  -DCMAKE_SYSTEM_NAME=iOS -DCMAKE_OSX_ARCHITECTURES=arm64 \
  -DCMAKE_OSX_SYSROOT="$SDK" -DCMAKE_OSX_DEPLOYMENT_TARGET="${IOS_MIN}" \
  -DCMAKE_INSTALL_PREFIX="${PREFIX}" \
  -DEXPAT_SHARED_LIBS=OFF -DEXPAT_BUILD_TOOLS=OFF \
  -DEXPAT_BUILD_EXAMPLES=OFF -DEXPAT_BUILD_TESTS=OFF \
  2>&1 | tee expat.log
cmake --build expat-build --config Release 2>&1 | tee -a expat.log
cmake --install expat-build --config Release 2>&1 | tee -a expat.log

# ---------------------------------------------------------------- fontconfig
log "fontconfig ${FONTCONFIG_VERSION}"
FC_URL1="https://www.freedesktop.org/software/fontconfig/release/fontconfig-${FONTCONFIG_VERSION}.tar.xz"
FC_URL2="https://gitlab.freedesktop.org/api/v4/projects/890/packages/generic/fontconfig/${FONTCONFIG_VERSION}/fontconfig-${FONTCONFIG_VERSION}.tar.xz"
curl -fL --retry 3 -o fontconfig.tar.xz "${FC_URL1}" || \
  curl -fL --retry 3 -o fontconfig.tar.xz "${FC_URL2}"
mkdir -p fontconfig-src && tar xf fontconfig.tar.xz --strip-components=1 -C fontconfig-src
meson setup fc-build fontconfig-src \
  --cross-file="${CROSS_PFX}" \
  --default-library=static --prefix="${PREFIX}" --buildtype=release \
  -Dtests=disabled -Dtools=disabled -Ddoc=disabled -Dnls=disabled \
  2>&1 | tee fontconfig.log
ninja -C fc-build install 2>&1 | tee -a fontconfig.log

# ---------------------------------------------------------------- cairo
log "cairo ${CAIRO_VERSION}"
curl -fL --retry 3 -o cairo.tar.xz \
  "https://www.cairographics.org/releases/cairo-${CAIRO_VERSION}.tar.xz"
mkdir -p cairo-src && tar xf cairo.tar.xz --strip-components=1 -C cairo-src
meson setup cairo-build cairo-src \
  --cross-file="${CROSS_PFX}" \
  --default-library=static --prefix="${PREFIX}" --buildtype=release \
  -Dtests=disabled -Dxlib=disabled -Dxcb=disabled \
  -Dquartz=disabled -Dfreetype=enabled -Dfontconfig=enabled \
  -Dpng=enabled -Dzlib=enabled -Dglib=enabled \
  2>&1 | tee cairo.log
ninja -C cairo-build install 2>&1 | tee -a cairo.log

# ---------------------------------------------------------------- pango
log "pango ${PANGO_VERSION}"
PANGO_MAJMIN="$(echo "${PANGO_VERSION}" | cut -d. -f1,2)"
curl -fL --retry 3 -o pango.tar.xz \
  "https://download.gnome.org/sources/pango/${PANGO_MAJMIN}/pango-${PANGO_VERSION}.tar.xz"
mkdir -p pango-src && tar xf pango.tar.xz --strip-components=1 -C pango-src
meson setup pango-build pango-src \
  --cross-file="${CROSS_PFX}" \
  --default-library=static --prefix="${PREFIX}" --buildtype=release \
  --wrap-mode=nofallback \
  -Dintrospection=disabled -Dgtk_doc=false \
  -Dfontconfig=enabled -Dfreetype=enabled -Dcairo=enabled \
  2>&1 | tee pango.log
ninja -C pango-build install 2>&1 | tee -a pango.log

log "base stack complete in ${PREFIX}"
