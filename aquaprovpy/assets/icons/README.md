# AquaProv logo and desktop action icons

`Logo.png` is the full AquaProv wordmark supplied by the user, used in the startup
banner, main sidebar, module top bar and standalone workbench branding.

`icon.png` is the square AquaProv icon supplied by the user. Application and
window icons use this image. Both original
assets are retained; their paths and matching interface colors live in
`aquaprovpy/ui/branding.py`.

The `module_*.svg` files are local vector icons for the four Home launch buttons.

`tab.png`, supplied by the user, is the module toolbar's View options icon.
It appears beside a dropdown chevron for panel and camera options.

`bin.png`, supplied by the user, is the Projects page's Delete project icon.
The action opens a warning before deleting project files.

`export.png`, supplied by the user, is used for figure and Results & methods
export actions. Figure button labels follow the selected file format.

The other PNG files were copied, at the user's request, from the local FracSTAT 2.0
`application resources/images` folder. AquaProv loads these bundled copies;
it does not read the FracSTAT installation at runtime.

The source application's supplied license is retained in
`FRACSTAT-LICENSE.txt` (copyright 2026 Sachida Nanda Mahanta).
The icon names and their action mappings are defined in `ui/icons.py`.

The Support & Resources page also uses `github-sign.png`, `pdf-file.png` and
`bug.png` from the same local FracSTAT image folder.
