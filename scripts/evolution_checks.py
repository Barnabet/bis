"""Independent readback assertions for the fixed evolution experiment.

No candidate preparation or observation extraction is used to calculate expected
answers. Expected values are frozen fixtures; source membership is checked using
standard CSV/date parsing independently of the reporting adapter.
"""
from __future__ import annotations

import csv
from decimal import Decimal
import hashlib
from io import StringIO
import re
import unicodedata


def number_equal(actual, expected):
    if actual is None or expected is None:
        return actual is expected
    try:
        return Decimal(str(actual)) == Decimal(str(expected))
    except ArithmeticError:
        return False


def region_slug(label):
    """Documented fact-ID encoding, independent of business calculations."""
    key = " ".join(unicodedata.normalize("NFKC", label).split()).casefold()
    slug = re.sub(r"[^a-z0-9]+", "_", key).strip("_")
    if not slug or slug != key:
        slug = (slug[:50] or "region") + "_" + hashlib.sha256(key.encode()).hexdigest()[:8]
    return slug


def snapshot_errors(snapshot, expected, selection, source, rows):
    errors = []
    def check(ok, label):
        if not ok:
            errors.append(label)
    facts = snapshot['facts']
    totals = expected['totals']
    for field in ('current', 'comparison', 'change'):
        check(number_equal(facts['revenue.' + field]['value'], totals[field]), 'total ' + field)
        check(facts['revenue.' + field].get('status') == 'known', 'total ' + field + ' status')
    check(number_equal(facts['revenue.growth']['value'], totals['growth_value']), 'total growth value')
    check(facts['revenue.growth']['display'] == totals['growth_display'], 'total growth display')
    check(facts['revenue.growth'].get('status') == ('undefined' if totals['growth_value'] is None else 'known'),
          'total growth status')
    check(facts['driver.region']['value'] == expected['driver']['region'], 'selected region')
    check(number_equal(facts['driver.change']['value'], expected['driver']['change']), 'selected region change')
    check(facts['driver.region'].get('status') == 'known' and facts['driver.change'].get('status') == 'known',
          'selected region status')
    if selection == 'largest_current_revenue':
        check(number_equal(facts['driver.current']['value'], expected['driver']['current']), 'selected current value')
    if selection == 'largest_percentage_change':
        check(number_equal(facts['driver.growth']['value'], expected['driver']['growth_value']), 'selected growth value')
    check(snapshot['metadata']['reporting_policy']['selection'] == selection, 'frozen selection policy')
    actual_regions = snapshot['datasets']['regional_totals']['rows']
    check([r['region'] for r in actual_regions] == [r['region'] for r in expected['regions']], 'regional membership/order')
    for row in expected['regions']:
        slug = region_slug(row['region'])
        for field in ('current', 'comparison', 'change', 'growth'):
            fid = f'region.{slug}.{field}'
            answer = row['growth_value'] if field == 'growth' else row[field]
            check(fid in facts and number_equal(facts[fid]['value'], answer), fid)
            if fid in facts:
                check(facts[fid].get('status') == ('undefined' if answer is None else 'known'), fid + ' status')
                if field == 'growth':
                    check(facts[fid]['display'] == row['growth_display'], fid + ' display')
        actual = next((r for r in actual_regions if r['region'] == row['region']), {})
        for field in ('current', 'comparison', 'change', 'growth'):
            check(field in actual and number_equal(actual[field], row['growth_value'] if field == 'growth' else row[field]),
                  row['region'] + ' dataset ' + field)
    expected_pivot = [(r['region'], p, Decimal(r[p])) for r in expected['regions'] for p in ('current', 'comparison')]
    actual_pivot = [(r['region'], r['period'], Decimal(r['revenue'])) for r in snapshot['datasets']['pivot_source']['rows']]
    check(actual_pivot == expected_pivot, 'pivot rows, membership, values and order')
    suffix = {'largest_current_revenue': '.current', 'largest_absolute_change': '.change',
              'largest_percentage_change': '.growth'}[selection]
    check(facts['driver.region']['inputs'] == [f"region.{region_slug(r['region'])}{suffix}" for r in expected['regions']],
          'driver dependency policy')
    check(snapshot['source_assets'] == [{k: source[k] for k in ('id', 'digest', 'filename')}], 'only current source bound')
    # Current and comparison source lines are checked exactly, including the
    # declared missing-region-zero provenance fallback to the nonempty window.
    period = snapshot['period']
    windows = {'current': period, 'comparison': period['comparison']}
    for row in expected['regions']:
        for field, window in windows.items():
            included = [(i + 2, item) for i, item in enumerate(rows)
                        if item['status'].casefold() == 'posted' and window['start'] <= item['date'] < window['end_exclusive']]
            selected = [line for line, item in included if item['region'].strip().casefold() == row['region'].casefold()]
            expected_lines = selected or [line for line, _ in included]
            fact = facts.get(f"region.{region_slug(row['region'])}.{field}", {})
            observed_lines = []
            for ref in fact.get('sources', []):
                check(ref['asset_id'] == source['id'] and ref['artifact_sha256'] == source['digest'], 'source provenance identity')
                match = re.fullmatch(r'csv:lines=([0-9,]+);columns=date,region,status,amount,currency', ref['locator'])
                check(bool(match), 'physical CSV source locator')
                if match:
                    observed_lines += [int(item) for item in match[1].split(',')]
            check(sorted(observed_lines) == sorted(expected_lines), row['region'] + ' ' + field + ' physical source lines')
    return errors


def exported_text(path, fmt):
    if fmt == 'docx':
        from docx import Document
        document = Document(path)
        return '\n'.join(p.text for p in document.paragraphs)
    if fmt == 'pdf':
        from pypdf import PdfReader
        return '\n'.join(page.extract_text() for page in PdfReader(path).pages)
    if fmt == 'pptx':
        from pptx import Presentation
        return '\n'.join(s.text for slide in Presentation(path).slides for s in slide.shapes if s.has_text_frame)
    from openpyxl import load_workbook
    workbook = load_workbook(path, data_only=True)
    try:
        return '\n'.join(str(cell.value) for sheet in workbook for row in sheet for cell in row if cell.value is not None)
    finally:
        workbook.close()


def export_errors(path, fmt, snapshot, expected):
    """Reopen real exported bytes; validate prose and table numbers by format."""
    errors = []
    text = exported_text(path, fmt)
    normalize = lambda value: ' '.join(value.split())
    for node in snapshot['nodes']:
        if node['kind'] == 'rich_text':
            rendered = ''.join(run['text'] if run['type'] == 'text' else snapshot['facts'][run['fact_id']]['display'] for run in node['runs'])
            if normalize(rendered) not in normalize(text):
                errors.append('exported ' + node['id'] + ' text')
    table_rows = []
    if fmt == 'docx':
        from docx import Document
        tables = Document(path).tables
        table_rows = [[c.text for c in row.cells] for table in tables if len(table.columns) == 5 for row in table.rows[1:]]
    elif fmt == 'pptx':
        from pptx import Presentation
        table_rows = [[c.text for c in row.cells] for slide in Presentation(path).slides for shape in slide.shapes
                      if shape.has_table and len(shape.table.columns) == 5 for row in list(shape.table.rows)[1:]]
    elif fmt == 'xlsx':
        from openpyxl import load_workbook
        workbook = load_workbook(path, data_only=True)
        try:
            sheet = workbook['Overview']
            header = next(i for i, row in enumerate(sheet.values, 1) if row[0] == 'Region')
            table_rows = [[sheet.cell(header + offset, col).value for col in range(1, 6)]
                          for offset in range(1, len(expected['regions']) + 1)]
            if not workbook['Analysis']._pivots or not workbook['Analysis']._charts:
                errors.append('native workbook pivot/chart')
        finally:
            workbook.close()
    else:
        from pypdf import PdfReader
        reader = PdfReader(path)
        if len(reader.named_destinations) != 5:
            errors.append('PDF complete named destinations')
        # Layout extraction preserves column gaps. The regional table has five
        # columns; the separate static pivot has three and must not substitute
        # for missing or incorrect regional table values.
        for page in reader.pages:
            for line in page.extract_text(extraction_mode='layout').splitlines():
                cells = re.split(r'\s{2,}', line.strip())
                if len(cells) == 5 and cells[0] != 'Region':
                    table_rows.append(cells)
    if [row[0] for row in table_rows] != [row['region'] for row in expected['regions']]:
        errors.append('export regional membership/order')
    for answer, actual in zip(expected['regions'], table_rows):
        for index, field in enumerate(('current', 'comparison', 'change'), 1):
            value = str(actual[index]).replace(',', '').replace('€', '')
            if not number_equal(value, answer[field]):
                errors.append(f'export {answer["region"]} {field}')
        value = actual[4]
        if answer['growth_value'] is None:
            # The exported dataset table uses the declared "Undefined" label;
            # prose facts and independent historical targets use "Not defined".
            if value != 'Undefined':
                errors.append('export undefined growth')
        elif fmt == 'xlsx':
            if abs(Decimal(str(value)) - Decimal(answer['growth_value'])) > Decimal('0.000000000001'):
                errors.append('export workbook growth')
        elif Decimal(str(value).replace('%', '').replace(',', '')) != Decimal(answer['growth_display'].replace('%', '')):
            errors.append('export displayed growth')
    return errors


def read_rows(data):
    return list(csv.DictReader(StringIO(data.decode('utf-8'))))


def write_rows(rows):
    out = StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=['transaction_id', 'date', 'region', 'status', 'amount', 'currency'])
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode()
