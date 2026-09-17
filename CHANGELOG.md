# Changelog

## v0.4.0 - 2026-09-17 (Pre-Release)

- Add `linux2apk.py` as the common entry point for ARM64 deb and relocatable tar distributions.
- Support `.tar.xz`, `.tar.gz`, `.tar.bz2`, and uncompressed `.tar` inputs.
- Audit archive paths, member types, symlinks, executable ELF architecture, and source SHA256 before image creation.
- Extract PNG application icons from tar distributions and record their provenance.
- Add a local WSL `erofs-utils` backend alongside the rooted Android/ADB backend.
- Add an offline artifact verifier for source, APK, EROFS, icon, package, and callback metadata.
- Add a Zotero 10 ARM64 example configuration with `zotero://` callback handling.
- Keep every release marked as Pre-Release until the project is declared production-ready.

The Zotero APK in this release passed offline image, signature, alignment, manifest, and integrity checks. Device installation and runtime compatibility have not yet been tested.
