"""PDF documents: order invoices and the sales summary report."""

import io
from datetime import date

from django.db.models import Sum
from django.utils import timezone
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import analytics as an
from .currency import convert, symbol
from .models import Order, OrderItem, Region

INDIGO = colors.HexColor("#4f46e5")
INK = colors.HexColor("#0f172a")
MUTED = colors.HexColor("#64748b")
LINE = colors.HexColor("#e2e8f0")
SOFT = colors.HexColor("#f1f5f9")

styles = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=20,
                    textColor=INK, spaceAfter=2)
H2 = ParagraphStyle("h2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12,
                    textColor=INK, spaceBefore=10, spaceAfter=6)
BODY = ParagraphStyle("body", parent=styles["Normal"], fontName="Helvetica", fontSize=9.5,
                      textColor=INK, leading=13)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8.5, textColor=MUTED, leading=11)
RIGHT = ParagraphStyle("right", parent=BODY, alignment=TA_RIGHT)


def _money(value, decimals=2):
    return f"{symbol()}{convert(value):,.{decimals}f}"


def _table(data, widths, header=True, align_right=()):
    t = Table(data, colWidths=widths, hAlign="LEFT")
    style = [
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    if header:
        style += [
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
            ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
            ("BACKGROUND", (0, 0), (-1, 0), SOFT),
        ]
    for col in align_right:
        style.append(("ALIGN", (col, 0), (col, -1), "RIGHT"))
    t.setStyle(TableStyle(style))
    return t


def _footer(text):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 10 * mm, text)
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()
    return draw


def _brand_header(title, subtitle):
    brand = Paragraph('<font color="#4f46e5"><b>Pulse</b></font><b>Analytics</b>', ParagraphStyle(
        "brand", parent=BODY, fontSize=14, leading=18))
    right = Paragraph(f"<b>{title}</b><br/><font color='#64748b'>{subtitle}</font>",
                      ParagraphStyle("hr", parent=RIGHT, fontSize=11, leading=15))
    t = Table([[brand, right]], colWidths=[85 * mm, 89 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), 2, INDIGO),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    return t


def invoice(order):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=18 * mm,
                            title=f"Invoice {order.number}", author="Pulse Analytics (demo)")
    c = order.customer
    story = [
        _brand_header(f"INVOICE {order.number.replace('SO', 'INV')}",
                      f"Issued {order.created:%B %d, %Y}"),
        Spacer(1, 10 * mm),
    ]
    bill_to = Paragraph(
        f"<font color='#64748b' size='8'>BILL TO</font><br/><b>{c.name}</b><br/>"
        f"{c.company + '<br/>' if c.company else ''}{c.email}<br/>{c.country}", BODY)
    details = Paragraph(
        f"<font color='#64748b' size='8'>ORDER DETAILS</font><br/>Order: <b>{order.number}</b><br/>"
        f"Date: {order.created:%b %d, %Y}<br/>Payment: {order.get_payment_display()}<br/>"
        f"Status: {order.get_status_display()}", BODY)
    seller = Paragraph(
        "<font color='#64748b' size='8'>FROM</font><br/><b>Pulse Demo Store Ltd.</b><br/>"
        "100 Example Street<br/>London, United Kingdom<br/>billing@example.com", BODY)
    info = Table([[seller, bill_to, details]], colWidths=[58 * mm, 58 * mm, 58 * mm])
    info.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [info, Spacer(1, 10 * mm)]

    rows = [["ITEM", "SKU", "QTY", "UNIT PRICE", "AMOUNT"]]
    for item in order.items.select_related("product"):
        rows.append([item.product.name, item.product.sku, str(item.quantity),
                     _money(item.unit_price), _money(item.line_total)])
    story.append(_table(rows, [70 * mm, 28 * mm, 16 * mm, 30 * mm, 30 * mm], align_right=(2, 3, 4)))

    subtotal = order.total or 0
    totals = Table([
        ["Subtotal", _money(subtotal)],
        ["Tax (0%, demo)", _money(0)],
        ["Total due", _money(subtotal)],
    ], colWidths=[40 * mm, 34 * mm], hAlign="RIGHT")
    totals.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9.5),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("TEXTCOLOR", (0, 0), (-1, 1), MUTED),
        ("FONT", (0, 2), (-1, 2), "Helvetica-Bold", 12),
        ("TEXTCOLOR", (0, 2), (-1, 2), INDIGO),
        ("LINEABOVE", (0, 2), (-1, 2), 1, INK),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [Spacer(1, 4 * mm), totals, Spacer(1, 14 * mm)]
    if order.status == Order.Status.REFUNDED:
        story.append(Paragraph("<font color='#dc2626'><b>REFUNDED</b></font> - this invoice has been "
                               "credited in full.", BODY))
    else:
        story.append(Paragraph("Thank you for your business!", BODY))
    story.append(Paragraph("This is a demo invoice with fictional data.", SMALL))

    doc.build(story, onFirstPage=_footer("Pulse Analytics · demo invoice"),
              onLaterPages=_footer("Pulse Analytics · demo invoice"))
    return buf.getvalue()


def _line_chart(labels, values, width=174 * mm, height=60 * mm):
    d = Drawing(width, height)
    chart = HorizontalLineChart()
    chart.x, chart.y = 34, 18
    chart.width, chart.height = width - 44, height - 28
    chart.data = [[float(convert(v)) for v in values] or [0]]
    step = max(1, len(labels) // 8)
    chart.categoryAxis.categoryNames = [
        (date.fromisoformat(l).strftime("%b %d") if i % step == 0 else "") for i, l in enumerate(labels)
    ]
    chart.categoryAxis.labels.fontSize = 7
    chart.categoryAxis.labels.fillColor = MUTED
    chart.categoryAxis.strokeColor = LINE
    chart.valueAxis.labels.fontSize = 7
    chart.valueAxis.labels.fillColor = MUTED
    chart.valueAxis.strokeColor = colors.white
    chart.valueAxis.gridStrokeColor = LINE
    chart.valueAxis.visibleGrid = True
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labelTextFormat = lambda v: f"{symbol()}{v / 1000:,.0f}k"
    chart.lines[0].strokeColor = INDIGO
    chart.lines[0].strokeWidth = 2
    d.add(chart)
    return d


def _bar_chart(labels, values, bar_colors, width=174 * mm, height=55 * mm):
    d = Drawing(width, height)
    chart = VerticalBarChart()
    chart.x, chart.y = 34, 18
    chart.width, chart.height = width - 44, height - 28
    chart.data = [[float(convert(v)) for v in values] or [0]]
    chart.categoryAxis.categoryNames = labels
    chart.categoryAxis.labels.fontSize = 7
    chart.categoryAxis.labels.fillColor = MUTED
    chart.categoryAxis.strokeColor = LINE
    chart.valueAxis.labels.fontSize = 7
    chart.valueAxis.labels.fillColor = MUTED
    chart.valueAxis.strokeColor = colors.white
    chart.valueAxis.gridStrokeColor = LINE
    chart.valueAxis.visibleGrid = True
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labelTextFormat = lambda v: f"{symbol()}{v / 1000:,.0f}k"
    chart.bars.strokeColor = None
    chart.barSpacing = 4
    for i, color in enumerate(bar_colors):
        chart.bars[(0, i)].fillColor = colors.HexColor(color)
    d.add(chart)
    if not values:
        d.add(String(width / 2, height / 2, "No data", textAnchor="middle", fillColor=MUTED))
    return d


def sales_report(filters, user=None):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=18 * mm,
                            title="Sales report", author="Pulse Analytics (demo)")
    items = filters.apply_to_items(OrderItem.objects.all())
    prev_start, prev_end = filters.previous
    cur = an.totals(items)
    prev = an.totals(filters.apply_to_items(OrderItem.objects.all(), prev_start, prev_end))

    scope = [filters.label]
    if filters.category:
        scope.append(filters.category.name)
    if filters.region:
        scope.append(Region(filters.region).label)
    story = [
        _brand_header("SALES REPORT", f"{filters.start:%b %d, %Y} – {filters.end:%b %d, %Y}"),
        Spacer(1, 6 * mm),
        Paragraph(f"Scope: {' · '.join(scope)}", SMALL),
        Spacer(1, 4 * mm),
    ]

    def delta(a, b):
        change = an.pct_change(a, b)
        if change is None:
            return "<font color='#64748b'>–</font>"
        color = "#059669" if change >= 0 else "#dc2626"
        return f"<font color='{color}'>{'▲' if change >= 0 else '▼'} {abs(change):.1f}%</font>"

    kpi_cells = []
    for label, value, a, b in [
        ("Revenue", _money(cur["revenue"], 0), cur["revenue"], prev["revenue"]),
        ("Orders", f"{cur['orders']:,}", cur["orders"], prev["orders"]),
        ("Avg. order", _money(cur["aov"], 0), cur["aov"], prev["aov"]),
        ("Gross profit", _money(cur["profit"], 0), cur["profit"], prev["profit"]),
    ]:
        kpi_cells.append(Paragraph(
            f"<font color='#64748b' size='8'>{label.upper()}</font><br/>"
            f"<font size='14'><b>{value}</b></font><br/><font size='8'>{delta(a, b)} vs prev.</font>",
            ParagraphStyle("kpi", parent=BODY, leading=17)))
    kpis = Table([kpi_cells], colWidths=[43.5 * mm] * 4)
    kpis.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
        ("BACKGROUND", (0, 0), (-1, -1), SOFT),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story += [kpis, Paragraph("Revenue trend", H2)]

    size, _ = an.bucket_size(filters.days)
    labels, revenue, _ = an.series(items, filters.start, filters.end, size)
    story.append(_line_chart(labels, revenue))

    by_category = list(
        items.values("product__category__name", "product__category__color")
        .annotate(revenue=Sum(an.REVENUE)).order_by("-revenue")
    )
    story += [
        Paragraph("Revenue by category", H2),
        _bar_chart([c["product__category__name"] for c in by_category],
                   [c["revenue"] for c in by_category],
                   [c["product__category__color"] for c in by_category]),
    ]

    top = (
        items.values("product__name", "product__category__name")
        .annotate(units=Sum("quantity"), revenue=Sum(an.REVENUE)).order_by("-revenue")[:10]
    )
    rows = [["PRODUCT", "CATEGORY", "UNITS", "REVENUE", "SHARE"]]
    for p in top:
        share = float(p["revenue"] / cur["revenue"] * 100) if cur["revenue"] else 0
        rows.append([p["product__name"], p["product__category__name"], f"{p['units']:,}",
                     _money(p["revenue"], 0), f"{share:.1f}%"])
    story += [Paragraph("Top 10 products", H2),
              _table(rows, [62 * mm, 34 * mm, 22 * mm, 32 * mm, 24 * mm], align_right=(2, 3, 4))]

    generated = timezone.localtime().strftime("%b %d, %Y %H:%M %Z")
    by = f" by {user.get_full_name() or user.username}" if user else ""
    footer = _footer(f"Pulse Analytics · generated {generated}{by} · fictional demo data")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
