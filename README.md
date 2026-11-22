<p align="center">
  <a href="https://sachi5908.github.io/AquaProv_Documentation/">
    <img src="https://res.cloudinary.com/hz875hgf/image/upload/v1794292717/aquaprov/docs/76cf0a128aa2d58f/assets/images/Logo.png" alt="AquaProv logo" width="460">
  </a>
</p>

<h1 align="center">AquaProv</h1>

<p align="center">
  <strong>Water chemistry, statistics and spatial analysis in one desktop workspace.</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/aquaprov/"><img src="https://img.shields.io/pypi/v/aquaprov?label=PyPI&color=0a7d8c" alt="PyPI version"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-3776ab" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/platform-Windows%20x64-0078d4" alt="Windows x64">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPL--3.0-2e7d32" alt="GPL-3.0 license"></a>
</p>

<p align="center">
  <a href="https://sachi5908.github.io/AquaProv_Documentation/">Documentation</a> &middot;
  <a href="https://sachi5908.github.io/AquaProv_Documentation/manual.html">User manual</a> &middot;
  <a href="https://sachi5908.github.io/AquaProv_Documentation/example-gallery.html">Examples</a> &middot;
  <a href="https://player.cloudinary.com/embed/?cloud_name=hz875hgf&public_id=AquaProv_Showcase_Final">Video tour</a> &middot;
  <a href="https://github.com/sachi5908/AquaProv/issues">Report an issue</a>
</p>

**AquaProv** (Aquatic Geochemistry & Provenance) is an open-source desktop
application for water-chemistry analysis, geochemical diagrams, multivariate
statistics, spatial mapping, mineral saturation and interactive 3D
visualization. Data, analysis settings, figure styling and numerical results
stay together in one project, for research, teaching and publication.

## Video tour

<p align="center">
  <a href="https://player.cloudinary.com/embed/?cloud_name=hz875hgf&public_id=AquaProv_Showcase_Final">
    <img src="https://res.cloudinary.com/hz875hgf/video/upload/so_5,w_960/AquaProv_Showcase_Final.jpg" alt="AquaProv showcase video: import a workbook, generate figures and explore the results" width="800">
  </a>
  <br>
  <a href="https://player.cloudinary.com/embed/?cloud_name=hz875hgf&public_id=AquaProv_Showcase_Final"><strong>▶ Watch the AquaProv showcase</strong></a>
</p>

## Quick start

On Windows x64 with 64-bit Python 3.10 or newer:

```powershell
python -m pip install aquaprov
aquaprov
```

If Python's `Scripts` folder is not on your PATH, launch with `python -m aquaprov`.
Then import a CSV or Excel workbook, choose a plot and click **Generate**.
Other ways to install are described under [Installation](#installation).

## At a glance

| | |
| --- | --- |
| **Version** | 1.0 |
| **Workspaces** | Groundwater, Statistics, Maps, 3D visualization, Assessment, WQI & DWQI, PHREEQC Mineral SI |
| **Plots** | 80 analysis and figure types |
| **Inputs** | CSV and Excel workbooks |
| **Outputs** | PNG, TIFF, JPG, PDF and SVG figures; CSV, Excel, Word and PDF results |
| **Project format** | `.aquaprov` (embedded data and settings) |
| **Built with** | Python 3.10+, PySide6 (Qt), Matplotlib |
| **License** | GNU General Public License, version 3 (GPL-3.0) |

All data processing and scientific calculations run locally. Internet access
is only used for the online documentation and optional map backgrounds.

## Analysis workspaces

### Groundwater & contamination

Geochemical classification and irrigation assessment:

- Triangle, rectangle, colour-coded and contour-filled Piper diagrams
- Durov, Stiff, Chernoff face and Schoeller diagrams
- Gibbs, Chadha, Gaillardet and HFE-D diagrams
- USSL and Wilcox irrigation assessments
- Plot-specific inputs, unit selection, styling and figure export

### Statistics

Exploratory and multivariate analysis:

- Pearson and Spearman correlation
- PCA scores, loadings, scree plots and correlation circles, with optional Varimax rotation
- Ward clustering, sample heatmaps and scatter matrices
- Boxplots, observed time series and bootstrap intervals
- Numerical results with the recorded analysis settings

### Maps, kriging & contours

Spatial exploration and interpolation:

- Sample-location maps with optional OpenStreetMap backgrounds
- Explicit source coordinate-system selection
- Ordinary kriging with prediction variance
- IDW using all samples or a configurable nearest-neighbour count, including distance ties
- Automatic WGS84-to-UTM/UPS conversion in either hemisphere, or a custom metre-based projected CRS
- Grid resolution or square cell spacing, with filled contours or classified raster cells
- Equal intervals, quantiles, Natural Breaks or custom thresholds, with recorded class boundaries
- Boundary layers, map styling and figure export

For longitude/latitude data, **IDW contours → Apply WGS84 local IDW preset**
sets power 2, 12 neighbours, automatic UTM/UPS, 20-metre cells and five Natural
Breaks classes. These are starting settings, not a claim of predictive accuracy.
See the [spatial mapping guide](https://sachi5908.github.io/AquaProv_Documentation/maps.html) for coordinate
handling, study-area coverage, classification and reproducible exports.

### 3D visualization

Interactive views of measurements and multivariate structure:

- XYZ sample scatter and linearly interpolated XYZ surfaces
- PCA sample scores and component loadings in three dimensions
- Isometric, XY, XZ and YZ camera presets
- Automatic rotation, perspective or orthographic projection and exact camera angles
- Coordinate guides and export of the current camera view

### Assessment & uncertainty

Measurement-quality review and analysis under declared assumptions:

- Measurement-quality and charge-balance checks
- Uncertainty propagation, sensitivity scenarios and chemical screening
- Detection-limit and censored-measurement controls
- Follow-up assay priorities and decision-model scenarios
- Compositional PCA, cluster stability, spatial validation and repeated-well analysis

Definitions, input requirements and limitations are in the
[online module guides](https://sachi5908.github.io/AquaProv_Documentation/introduction.html).

### Water quality indices (WQI & DWQI)

Weighted-arithmetic, groundwater and CCME WQI methods, plus weighted and custom
DWQI, with editable standards, parameter weights, ideal values and
classifications. Results can be shown as IDW or ordinary-kriging maps, 3D
surfaces, contours, class zones, sample values, distributions, seasonal
comparisons and compliance charts.

The WHO 2026 chemical guidelines are transcribed from the official edition. BIS
acceptable and permissible limits carry separate provenance fields; amendment
values that are not available remain unset until reviewed limits are imported.
See the [WQI/DWQI methods guide](https://sachi5908.github.io/AquaProv_Documentation/water-quality-indices.html) for formulas,
CCME sampling requirements, standard updates and limitations.

### PHREEQC mineral saturation

Import saturation indices from CSV/Excel, or calculate aqueous speciation
locally with the bundled USGS IPhreeqc engine and `phreeqc.dat`, `wateq4f.dat`
or an embedded custom database. Compare Calcite, Dolomite, Gypsum, Anhydrite,
Halite, Quartz, Fluorite, Goethite, Hematite and other phases with bar charts,
heatmaps, box and violin plots, classification distributions, scatter plots and
IDW or kriging maps.

Chemistry mappings, analytical bases, units, temperature, density and redox
assumptions are recorded with every activity-based SI, together with
charge-balance diagnostics and mineral statistics. Numerical results and full
calculation provenance export to CSV/Excel. See the
[mineral saturation guide](https://sachi5908.github.io/AquaProv_Documentation/mineral-saturation.html).

## Installation

| Option | Best for | Requires |
| --- | --- | --- |
| [Python package](#python-package-pypi) | Most users, and scripting with `aquaprovpy` | 64-bit Python 3.10+ |
| [Windows installer](#standalone-windows-application) | Users without Python | Nothing else |
| [From source](#run-from-source) | Development and contributions | Python 3.10+ and Git |

### Python package (PyPI)

```powershell
python -m pip install aquaprov
aquaprov
```

`python -m aquaprov` and `python -m aquaprovpy` launch the same application.
`aquaprov --version` prints the installed version. Open a saved project
directly with `aquaprov "C:\path\to\study.aquaprov"`. Scientific modules can be
imported in Python, for example `from aquaprovpy import triangle_piper`.

The package includes the Windows x64 PHREEQC engine and its databases, so no
separate PHREEQC installation is needed. To upgrade, run
`python -m pip install --upgrade aquaprov`.

### Standalone Windows application

Download **`AquaProv-Setup-1.0-x64.exe`** from the
[latest release](https://github.com/sachi5908/AquaProv/releases/latest), run
the installer and launch AquaProv from the Start menu. The application includes
its own Python runtime and dependencies.

### Run from source

Clone or download the [repository](https://github.com/sachi5908/AquaProv), then
run these commands from the project root:

```powershell
python -m pip install -r requirements.txt
python main.py
```

To open a saved project at startup:

```powershell
python main.py "C:\path\to\study.aquaprov"
```

The main dependencies are **PySide6, NumPy, pandas, SciPy, Matplotlib,
scikit-learn, Shapely, pyproj, openpyxl, xlrd, python-docx, ReportLab and
defusedxml**. See [requirements.txt](requirements.txt) for the complete list.

### System requirements

| Component | Requirement |
| --- | --- |
| **Operating system** | Windows x64 (macOS, Linux and Windows ARM64 are not supported by the bundled PHREEQC engine) |
| **Python** | 64-bit Python 3.10 or newer for the PyPI package or source; not needed for the standalone application |
| **Display** | At least 1024 × 700; 1920 × 1080 recommended |
| **Graphics** | CPU-based Matplotlib rendering, including 3D; no dedicated GPU required |
| **Internet** | Only for hosted documentation and online map backgrounds |

Processing time and memory use depend on dataset size, interpolation settings
and the number of uncertainty simulations.

## Using AquaProv

1. Create or open a project from **Home** or **Projects**.
2. Import a **CSV or Excel workbook** and review its columns and units in **Data**.
3. Choose an analysis in the **Plot library** and set its inputs under **Settings**.
4. Click **Generate**. Turn on **Auto update** to refresh the plot as settings change.
5. Review the figure and numerical results. Adjust labels, colours, fonts and size under **Style**.
6. Use **Export** for figures, results and methods, and **Save project** to keep everything together.

All modules share the imported dataset, while each plot keeps its own analysis,
appearance and export settings. Saved projects embed the data, so they reopen
without the original CSV or workbook.

### Preparing data

- Use one row per sample or observation, with a header row of column names.
- Common laboratory column names are recognised and mapped automatically.
- Blank cells are treated as missing, not zero. Review units, missing-data
  policies and detection-limit handling before interpreting a result.

Incomplete chemistry tables can still be used. The plot library marks diagrams
that need more data and selects an available overview after import. Schoeller
shows the measured ions with gaps; Gibbs and Gaillardet use each panel's
available samples; Durov requires the major ions, with optional pH and TDS
panels. Missing sample labels are generated from row numbers, and input coverage
and excluded samples are reported with each plot.

For example, `Data/data_Liu_et_al_2021.csv` produces Schoeller, Gibbs and
Gaillardet plots without CO3. Piper, Chadha, HFE-D and Durov still need CO3 for
their anion totals, and the irrigation diagrams need measured EC. AquaProv never
substitutes zero for an unreported ion or estimates EC from TDS.

## Outputs and reproducibility

| Output | Formats | Contents |
| --- | --- | --- |
| **Figures** | PNG, TIFF, JPG, PDF, SVG | The rendered plot, including camera view, labels, legend and colour scale |
| **Results and methods** | CSV + JSON, Excel, Word, PDF | Numerical tables, methods, warnings and provenance |
| **Projects** | `.aquaprov` | Embedded dataset with all workspace and plot settings |

Figure exports use the last rendered result, so apply pending settings first.
3D images keep the current camera view. PDF and SVG exports are vector artwork,
although online map tiles remain raster images.

For publication, keep the numerical results and methods alongside each figure,
and report the AquaProv version, build type (PyPI, installer or source), input
units, variable selection, preprocessing, coordinate system and uncertainty
assumptions. Irrigation-diagram boundaries include documented approximations,
and spatial and uncertainty results depend on the selected models. Consult the
[scientific references](https://sachi5908.github.io/AquaProv_Documentation/references.html)
and the relevant method guide when interpreting results.

## Documentation

Full documentation is hosted at
**[AquaProv Documentation](https://sachi5908.github.io/AquaProv_Documentation/)**;
no local files are needed to install or run the software.

| Resource | Contents |
| --- | --- |
| [Getting started](https://sachi5908.github.io/AquaProv_Documentation/quickstart.html) | Create a project, import data, generate a plot and export it. |
| [Workspace guide](https://sachi5908.github.io/AquaProv_Documentation/workspace.html) | Navigation, saved projects, analysis settings and figure styling. |
| [Illustrated workflows](https://sachi5908.github.io/AquaProv_Documentation/plot-workflows.html) | Step-by-step plotting routes with screenshots and settings. |
| [Datasets](https://sachi5908.github.io/AquaProv_Documentation/datasets.html) | Example inputs and their sources. |
| [Example gallery](https://sachi5908.github.io/AquaProv_Documentation/example-gallery.html) | Geochemical, statistical, spatial and 3D examples. |
| [Methods and publication](https://sachi5908.github.io/AquaProv_Documentation/publication.html) | Figure exports, numerical outputs and reproducibility guidance. |
| [References](https://sachi5908.github.io/AquaProv_Documentation/references.html) | Scientific methods, citations and attribution. |
| [Complete user manual](https://sachi5908.github.io/AquaProv_Documentation/manual.html) | The full manual; print or save it as PDF from your browser. |

The in-app **Support & Resources** page links to the documentation, manual,
repository and issue tracker. These links are configured in
[`resource_links.json`](aquaprovpy/assets/resource_links.json).

## Applications

- Groundwater chemistry and hydrogeology
- Water-quality assessment and contamination studies
- Irrigation-water evaluation
- Mineral saturation and geochemical equilibrium screening
- Multivariate exploration of environmental measurements
- Spatial analysis of monitoring networks
- Teaching quantitative water analysis

## Project structure

```text
AquaProv/
├── main.py                   # Desktop entry point
├── aquaprovpy/
│   ├── __init__.py           # Application and package version
│   ├── cli.py                # `aquaprov` console command
│   ├── core/                 # Data, projects, plot jobs and exports
│   ├── ui/                   # Desktop interface and shared controls
│   ├── modules/              # The seven analysis workspaces
│   ├── assessment/           # Assessment and uncertainty calculations
│   ├── water_quality/        # WQI and DWQI methods and standards
│   ├── saturation/           # PHREEQC engine, databases and SI workflow
│   └── assets/               # Icons, colour scales and resource links
├── Data/                     # Data template, example datasets and benchmarks
├── requirements.txt          # Runtime dependencies
├── CITATION.cff              # Citation metadata
├── LICENSE                   # GNU GPL version 3
└── README.md
```

Start with `Data/AquaProv_Data_Template.xlsx` to prepare your own dataset, or
try one of the example files in `Data/`.

## Contributing

Bug reports and suggestions are welcome through the
[issue tracker](https://github.com/sachi5908/AquaProv/issues). Please include
the AquaProv version, the module and plot, the steps to reproduce and any error
message. A small anonymised input file helps with data-dependent issues.

To run the automated tests from the project root:

```powershell
python -m pip install pytest
$env:QT_QPA_PLATFORM = 'offscreen'; $env:QT_QPA_FONTDIR = 'C:\Windows\Fonts'; $env:MPLBACKEND = 'Agg'
python -m pytest tests -q
```

These settings run the interface without opening windows. Use a new terminal
for a normal desktop launch afterwards.

When changing behaviour, test the affected workflow with representative data,
keep the attribution of scientific methods, and update the hosted documentation.

## Citing AquaProv

> Mahanta, S. N., Phukan, B., & Selvakumar, S. *AquaProv* (Version 1.0) [Computer software]. https://github.com/sachi5908/AquaProv

Machine-readable metadata is in [CITATION.cff](CITATION.cff). Please also cite
the original scientific methods used in your analysis.

## License and acknowledgments

AquaProv is distributed under the **GNU General Public License, version 3**;
see [LICENSE](LICENSE). The startup and project interface draw inspiration from
**FracSTAT**. Bundled third-party resources, including the USGS PHREEQC engine
and PhreeqPy, retain their original notices. Maps using OpenStreetMap must
preserve contributor attribution.

## Authors and contact

| Author | Contact |
| --- | --- |
| **Sachida Nanda Mahanta** | [sachida5908@gmail.com](mailto:sachida5908@gmail.com) |
| **Bristi Phukan** | [bristi.87.hn.24@gmail.com](mailto:bristi.87.hn.24@gmail.com) |
| **Dr. S. Selvakumar** | [geoselvas@gmail.com](mailto:geoselvas@gmail.com) |
