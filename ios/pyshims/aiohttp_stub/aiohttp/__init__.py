"""iOS fallback stub for aiohttp (used only if no BeeWare iOS wheel is
available at build time). Rayforge uses aiohttp purely functionally
(async with aiohttp.ClientSession() in network machine drivers and the
updater) — no subclassing — so an import-ok / use-fails stub cleanly
degrades those features to a clear error instead of breaking startup.
"""

__version__ = "0.0.0+ios.stub"


class _AiohttpUnavailable(RuntimeError):
    pass


_MSG = (
    "aiohttp is not available in this iOS build of Rayforge; "
    "network machine drivers and the updater are disabled."
)


def __getattr__(name):
    raise _AiohttpUnavailable(f"{_MSG} (attribute: aiohttp.{name})")
