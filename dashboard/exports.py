"""CSV / Excel file responses."""

import csv

from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


def csv_response(filename, headers, rows):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("﻿")  # BOM so Excel opens UTF-8 correctly
    writer = csv.writer(response)
    writer.writerow(headers)
    writer.writerows(rows)
    return response


def xlsx_workbook(title, headers, rows, widths, money_col=None, date_col=None):
    wb = Workbook()
    ws = wb.active
    ws.title = title
    ws.append(headers)
    header_fill = PatternFill("solid", fgColor="4F46E5")
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
    for row in rows:
        ws.append(row)
    last_row = ws.max_row

    if money_col:
        letter = get_column_letter(money_col)
        ws.append([])
        ws.append([""] * (money_col - 2) + ["Total", f"=SUM({letter}2:{letter}{last_row})"])
        ws.cell(ws.max_row, money_col - 1).font = Font(bold=True)
        ws.cell(ws.max_row, money_col).font = Font(bold=True)
        for r in ws.iter_rows(min_row=2, min_col=money_col, max_col=money_col):
            r[0].number_format = '"$"#,##0.00'
    if date_col:
        for r in ws.iter_rows(min_row=2, min_col=date_col, max_col=date_col):
            r[0].number_format = "yyyy-mm-dd"
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{last_row}"
    return wb


def xlsx_response(filename, workbook):
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    workbook.save(response)
    return response
