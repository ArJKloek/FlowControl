import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from propar.parameters import parameters, values


def build_rows():
    all_parameters = parameters
    parameter_values = values

    options_by_parameter = {}
    for option in parameter_values:
        parameter_number = option.get('parameter')
        options_by_parameter.setdefault(parameter_number, []).append(option)

    rows = []
    for item in all_parameters:
        parameter_number = item.get('Parameter')
        options = options_by_parameter.get(parameter_number, [])
        options_text = ' | '.join(
            f"{option.get('value')}: {option.get('description', '')}"
            for option in sorted(options, key=lambda x: (x.get('value') is None, x.get('value')))
        )
        rows.append({
            'parameter': parameter_number,
            'name': item.get('Name', ''),
            'longname': item.get('Name', ''),
            'description': '',
            'process': item.get('ProPar', {}).get('Process', ''),
            'fbnr': item.get('ProPar', {}).get('Parameter', ''),
            'vartype': item.get('Type', ''),
            'vartype2': '',
            'default': '',
            'min': '',
            'max': '',
            'read': '',
            'write': '',
            'poll': '',
            'secured': '',
            'highly_secured': '',
            'available': '',
            'advanced': '',
            'channels_group0': '',
            'channels_group1': '',
            'channels_group2': '',
            'value_options_count': len(options),
            'value_options': options_text,
        })

    rows.sort(key=lambda x: x['parameter'])
    return rows, parameter_values


def write_csv(rows, output_path):
    fieldnames = [
        'parameter', 'name', 'longname', 'description', 'process', 'fbnr',
        'vartype', 'vartype2', 'default', 'min', 'max',
        'read', 'write', 'poll', 'secured', 'highly_secured', 'available', 'advanced',
        'channels_group0', 'channels_group1', 'channels_group2',
        'value_options_count', 'value_options',
    ]
    with output_path.open('w', newline='', encoding='utf-8-sig') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_xlsx(rows, parameter_values, output_path):
    try:
        from openpyxl import Workbook
    except Exception:
        return False

    workbook = Workbook()
    ws_parameters = workbook.active
    ws_parameters.title = 'parameters'

    headers = [
        'parameter', 'name', 'longname', 'description', 'process', 'fbnr',
        'vartype', 'vartype2', 'default', 'min', 'max',
        'read', 'write', 'poll', 'secured', 'highly_secured', 'available', 'advanced',
        'channels_group0', 'channels_group1', 'channels_group2',
        'value_options_count', 'value_options',
    ]
    ws_parameters.append(headers)
    for row in rows:
        ws_parameters.append([row[h] for h in headers])

    ws_values = workbook.create_sheet('value_options')
    value_headers = ['parameter', 'name', 'value', 'description', 'filter', 'id']
    ws_values.append(value_headers)
    for option in sorted(parameter_values, key=lambda x: (x.get('parameter'), x.get('value'))):
        ws_values.append([
            option.get('parameter', ''),
            option.get('name', ''),
            option.get('value', ''),
            option.get('description', ''),
            option.get('filter', ''),
            option.get('id', ''),
        ])

    try:
        workbook.save(output_path)
    except PermissionError:
        return False
    return True


def main():
    script_dir = Path(__file__).resolve().parent
    rows, parameter_values = build_rows()

    csv_path = script_dir / 'parameters_overview.csv'
    xlsx_path = script_dir / 'parameters_overview.xlsx'

    write_csv(rows, csv_path)
    xlsx_ok = write_xlsx(rows, parameter_values, xlsx_path)

    print(f'CSV written: {csv_path}')
    if xlsx_ok:
        print(f'XLSX written: {xlsx_path}')
    else:
        print('XLSX not written (openpyxl not available or file is locked). Close the workbook or install openpyxl to enable .xlsx export.')


if __name__ == '__main__':
    main()
