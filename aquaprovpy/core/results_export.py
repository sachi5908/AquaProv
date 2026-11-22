"""Portable results reports: CSV/JSON, Excel workbooks, Word and PDF."""
from datetime import date, datetime
from html import escape
import json
import math
from pathlib import Path
import re

import numpy as np
import pandas as pd
from .export_files import write_export_files


RESULT_FORMATS = (('CSV + JSON', 'csv'), ('Excel (.xlsx)', 'xlsx'),
                  ('Word (.docx)', 'docx'), ('PDF (.pdf)', 'pdf'))
FORMAT_NAMES = {'csv': 'CSV + JSON', 'xlsx': 'Excel', 'docx': 'Word', 'pdf': 'PDF'}


def validate_export_name(value):
    value = str(value)
    if (not value.strip() or value in ('.', '..') or value != value.rstrip(' .') or
            re.search(r'[<>:"/\\|?*\x00-\x1f]', value) or
            value.upper().split('.')[0] in {'CON', 'PRN', 'AUX', 'NUL',
                *[f'COM{i}' for i in range(1, 10)], *[f'LPT{i}' for i in range(1, 10)]}):
        raise ValueError('Use a valid export file name without path separators.')
    return value


def result_export_paths(result, directory, stem, format='csv'):
    if format not in FORMAT_NAMES:
        raise ValueError('Choose CSV + JSON, Excel, Word or PDF for results export.')
    directory, stem = Path(directory).expanduser().resolve(), validate_export_name(stem)
    if format == 'csv':
        names = [f'{stem}_{validate_export_name(key)}.csv' for key in result.tables]
        names.append(f'{stem}_methods.json')
    else:
        # A figure PDF and a results PDF can coexist without overwriting each other.
        names = [f'{stem}_results.{format}']
    if len({name.casefold() for name in names}) != len(names):
        raise ValueError('Result table names produce duplicate export file names.')
    return [directory / name for name in names]


def text_value(value):
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, (dict, list, tuple, np.ndarray)):
        return json.dumps(value.tolist() if isinstance(value, np.ndarray) else value,
                          ensure_ascii=False, default=str)
    if value is None or pd.isna(value):
        return ''
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def method_rows(metadata, prefix=''):
    for key, value in metadata.items():
        field = f'{prefix}.{key}' if prefix else str(key)
        if isinstance(value, dict) and value:
            yield from method_rows(value, field)
        else:
            yield field, text_value(value)


def table_parts(table, columns_per_page=6):
    """Repeat row identifiers when wide tables need several column sections."""
    groups = [list(range(start, min(start + columns_per_page, len(table.columns))))
              for start in range(0, len(table.columns), columns_per_page)] or [[]]
    index_label = ' / '.join(str(name) for name in table.index.names if name is not None) or 'Index'
    for columns in groups:
        headers = [index_label] + [text_value(table.columns[column]) for column in columns]
        rows = ([text_value(index)] + [text_value(row[column]) for column in columns]
                for index, row in zip(table.index, table.itertuples(index=False, name=None)))
        yield headers, rows


def _excel_value(value):
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, (dict, list, tuple, np.ndarray)):
        return text_value(value)
    if value is None or pd.isna(value):
        return None
    if isinstance(value, int) and not isinstance(value, bool) and abs(value) >= 10 ** 15:
        return str(value)  # Excel cannot retain large integer identifiers as numbers.
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, (str, int, float, bool)):
        return value
    return text_value(value)


def _write_excel(path, result, metadata, title):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    workbook = Workbook()
    workbook.remove(workbook.active)
    used = {'methods', 'warnings'}
    next_rows = {}
    table_names = []
    def sheet_name(name):
        base = re.sub(r'[\\/*?:\[\]\x00-\x1f]', '_', str(name)).strip(" '")[:31] or 'Results'
        candidate, count = base, 2
        while candidate.casefold() in used:
            suffix = f' ({count})'
            candidate, count = base[:31 - len(suffix)] + suffix, count + 1
        used.add(candidate.casefold())
        return candidate
    def append(sheet, row):
        row_number = next_rows.get(sheet.title, 1)
        next_rows[sheet.title] = row_number + 1
        for column, value in enumerate(row, 1):
            value = _excel_value(value)
            if isinstance(value, str) and len(value) > 32767:
                raise ValueError('An Excel cell exceeds 32,767 characters. Use CSV + JSON or a document export.')
            cell = sheet.cell(row_number, column, value)
            if isinstance(value, str):
                # Preserve labels such as '=Sample 1' literally, never as formulas.
                cell.data_type = 's'
    def style(sheet):
        sheet.freeze_panes = 'B2'
        sheet.auto_filter.ref = sheet.dimensions
        for cell in sheet[1]:
            cell.font = Font(name='Calibri', bold=True, color='FFFFFF')
            cell.fill = PatternFill('solid', fgColor='006D75')
            cell.alignment = Alignment(wrap_text=True, vertical='top')
        row_count, column_count = sheet.max_row, sheet.max_column
        for column in range(1, column_count + 1):
            width = max(len(str(sheet.cell(row, column).value or '')) for row in range(1, min(row_count, 100) + 1))
            sheet.column_dimensions[get_column_letter(column)].width = min(44, max(12, width + 2))
    for name, table in result.tables.items():
        if len(table) + 1 > 1048576 or len(table.columns) + 1 > 16384:
            raise ValueError('A result table exceeds Excel worksheet limits. Use CSV + JSON.')
        sheet = workbook.create_sheet(sheet_name(name))
        table_names.append((str(name), sheet.title))
        append(sheet, [table.index.name or 'Index', *map(text_value, table.columns)])
        for index, row in zip(table.index, table.itertuples(index=False, name=None)):
            append(sheet, [index, *row])
        style(sheet)
    methods = workbook.create_sheet('Methods')
    append(methods, ['Field', 'Value'])
    append(methods, ['Report title', title])
    for name, sheet in table_names:
        append(methods, [f'Result table: {name}', sheet])
    for field, value in method_rows(metadata):
        # Long provenance strings are kept in numbered continuation rows.
        for start in range(0, max(1, len(value)), 32000):
            append(methods, [field if start == 0 else f'{field} (continued)', value[start:start + 32000]])
    style(methods)
    warnings = workbook.create_sheet('Warnings')
    append(warnings, ['Warning'])
    for warning in result.warnings or ['No analysis warnings.']:
        append(warnings, [text_value(warning)])
    style(warnings)
    workbook.save(path)
    workbook.close()


def _write_word(path, result, metadata, title):
    from docx import Document
    from docx.enum.section import WD_ORIENT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Inches, Pt, RGBColor
    document = Document()
    section = document.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = Inches(11.69), Inches(8.27)
    section.top_margin = section.bottom_margin = Inches(.6)
    section.left_margin = section.right_margin = Inches(.6)
    normal = document.styles['Normal']
    normal.font.name, normal.font.size = 'Calibri', Pt(9)
    normal.paragraph_format.space_after = Pt(3)
    for name in ('Title', 'Heading 1', 'Heading 2'):
        document.styles[name].font.color.rgb = RGBColor.from_string('006D75')
    document.core_properties.title = title
    document.core_properties.subject = 'AquaProv results and methods'
    section.footer.paragraphs[0].text = 'AquaProv | Results & methods'
    document.add_heading(title, 0)
    document.add_paragraph('AquaProv | Results & methods')
    document.add_heading('Analysis warnings', 1)
    for warning in result.warnings or ['No analysis warnings.']:
        document.add_paragraph(text_value(warning))
    def add_table(headers, rows):
        table = document.add_table(rows=1, cols=len(headers))
        table.style = 'Light Shading Accent 1'
        table.autofit = False
        for column in table.columns:
            column.width = Inches(10.49 / len(headers))
        for cell, value in zip(table.rows[0].cells, headers):
            cell.text = value
            for run in cell.paragraphs[0].runs:
                run.bold = True
            shading = OxmlElement('w:shd')
            shading.set(qn('w:fill'), 'E7F4F7')
            cell._tc.get_or_add_tcPr().append(shading)
        repeat = OxmlElement('w:tblHeader')
        table.rows[0]._tr.get_or_add_trPr().append(repeat)
        for row in rows:
            for cell, value in zip(table.add_row().cells, row):
                cell.text = value
    for name, table in result.tables.items():
        document.add_heading(str(name), 1)
        for part, (headers, rows) in enumerate(table_parts(table), 1):
            if len(table.columns) > 6:
                document.add_heading(f'Columns, part {part}', 2)
            add_table(headers, rows)
    document.add_heading('Methods & settings', 1)
    add_table(['Field', 'Value'], method_rows(metadata))
    document.save(path)


def _write_pdf(path, result, metadata, title):
    from matplotlib import get_data_path
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle
    fonts = Path(get_data_path()) / 'fonts' / 'ttf'
    for name, filename in (('AquaProv', 'DejaVuSans.ttf'), ('AquaProv-Bold', 'DejaVuSans-Bold.ttf')):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(fonts / filename)))
    body = ParagraphStyle('Body', fontName='AquaProv', fontSize=8, leading=11, spaceAfter=4)
    heading = ParagraphStyle('Heading', parent=body, fontName='AquaProv-Bold', fontSize=13,
                             leading=17, textColor=colors.HexColor('#006d75'), spaceBefore=12, spaceAfter=8,
                             keepWithNext=True)
    def paragraph(value, style=body):
        return Paragraph(escape(str(value)).replace('\n', '<br/>'), style)
    document = SimpleDocTemplate(str(path), pagesize=landscape(A4), rightMargin=36, leftMargin=36,
                                 topMargin=32, bottomMargin=36, title=title, author='AquaProv')
    story = [paragraph(title, heading), paragraph('AquaProv | Results & methods'),
             paragraph('Analysis warnings', heading)]
    story.extend(paragraph(text_value(value)) for value in result.warnings or ['No analysis warnings.'])
    def add_table(headers, rows, widths=None):
        data = [[paragraph(value) for value in headers]]
        data.extend([paragraph(value) for value in row] for row in rows)
        table = LongTable(data, colWidths=widths or [document.width / len(headers)] * len(headers),
                          repeatRows=1, splitByRow=1, splitInRow=1, hAlign='LEFT')
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e7f4f7')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7fbfc')]),
            ('GRID', (0, 0), (-1, -1), .35, colors.HexColor('#cfdee5')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.extend([table, Spacer(1, 10)])
    for name, table in result.tables.items():
        for part, (headers, rows) in enumerate(table_parts(table), 1):
            label = str(name) + (f' - columns, part {part}' if len(table.columns) > 6 else '')
            story.append(paragraph(label, heading))
            add_table(headers, rows)
    story.append(paragraph('Methods & settings', heading))
    add_table(['Field', 'Value'], method_rows(metadata), [document.width * .32, document.width * .68])
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(colors.white)
        canvas.rect(0, 0, *landscape(A4), fill=1, stroke=0)
        canvas.setFont('AquaProv', 8)
        canvas.setFillColor(colors.HexColor('#526f80'))
        canvas.drawString(36, 20, 'AquaProv | Results & methods')
        canvas.drawRightString(landscape(A4)[0] - 36, 20, f'Page {doc.page}')
        canvas.restoreState()
    document.build(story, onFirstPage=footer, onLaterPages=footer)


def export_results(result, directory, stem='analysis', *, format='csv', title='AquaProv analysis'):
    paths = result_export_paths(result, directory, stem, format)
    metadata = result.methods_record()
    def write(staged):
        if format == 'csv':
            for table, target in zip(result.tables.values(), staged):
                table.to_csv(target, encoding='utf-8-sig', index=True)
            staged[-1].write_text(json.dumps(metadata, indent=2, ensure_ascii=False,
                                             default=str, allow_nan=False), encoding='utf-8')
        else:
            writers = {'xlsx': _write_excel, 'docx': _write_word, 'pdf': _write_pdf}
            writers[format](staged[0], result, metadata, title)
    return write_export_files(paths, write)
