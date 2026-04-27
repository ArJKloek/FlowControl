import csv
from pathlib import Path

from propar.parameters import parameters


def build_rows():
    all_parameters = parameters.get('allparameters', [])
    parameter_values = parameters.get('parvalue', [])

    options_by_parameter = {}
    for option in parameter_values:
        parameter_number = option.get('parameter')
        options_by_parameter.setdefault(parameter_number, []).append(option)

    rows = []
    for item in all_parameters:
        parameter_number = item.get('parameter')
        options = options_by_parameter.get(parameter_number, [])
        options_text = ' | '.join(
            f"{option.get('value')}: {option.get('description', '')}"
            for option in sorted(options, key=lambda x: (x.get('value') is None, x.get('value')))
        )
        rows.append({
            'parameter': parameter_number,
            'name': item.get('name', ''),
            'longname': item.get('longname', ''),
            'description': item.get('description', ''),
            'process': item.get('process', ''),
            'fbnr': item.get('fbnr', ''),
            'vartype': item.get('vartype', ''),
            'vartype2': item.get('vartype2', ''),
            'default': item.get('default', ''),
            'min': item.get('min', ''),
            'max': item.get('max', ''),
            'read': item.get('read', ''),
            'write': item.get('write', ''),
            'poll': item.get('poll', ''),
            'secured': item.get('secured', ''),
            'highly_secured': item.get('highly secured', ''),
            'available': item.get('available', ''),
            'advanced': item.get('advanced', ''),
            'channels_group0': item.get('group0', ''),
            'channels_group1': item.get('group1', ''),
            'channels_group2': item.get('group2', ''),
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

    workbook.save(output_path)
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
        print('XLSX not written (openpyxl not available). Install openpyxl to enable .xlsx export.')


if __name__ == '__main__':
    main()
