"""Generate the version-controlled Power BI project and its four native report pages."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path("powerbi")
REPORT = ROOT / "Olist.Report"
MODEL = ROOT / "Olist.SemanticModel"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/"


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def artifact(path, schema, **content):
    write(path, {"$schema": SCHEMA + schema + "/schema.json", **content})


columns = {
    "Orders": {
        "order_id": "string", "customer_id": "string", "customer_unique_id": "string",
        "customer_state": "string", "order_status": "string", "purchase_date": "dateTime",
        "delivery_days": "int64", "delivery_band": "string", "review_score": "int64",
    },
    "Items": {"order_id": "string", "order_item_id": "int64", "product_id": "string",
              "seller_id": "string", "price": "decimal", "freight_value": "decimal"},
    "Payments": {"order_id": "string", "payment_sequential": "int64", "payment_type": "string",
                 "payment_value": "decimal"},
    "Products": {"product_id": "string", "category": "string"},
    "Sellers": {"seller_id": "string", "seller_state": "string"},
}
currency = '"R$ " #,0.00'
calculations = {
    "Revenue": ('CALCULATE(SUM(Items[price]), Orders[order_status] = "delivered")', currency),
    "Order Count": ('CALCULATE(COUNTROWS(Orders), Orders[order_status] = "delivered")', "#,0"),
    "All Orders": ("COUNTROWS(Orders)", "#,0"),
    "Average Order Value": ("DIVIDE([Revenue], [Order Count])", currency),
    "Customers": ('CALCULATE(DISTINCTCOUNT(Orders[customer_unique_id]), Orders[order_status] = "delivered")', "#,0"),
    "Repeat Customers": ('COUNTROWS(FILTER(VALUES(Orders[customer_unique_id]), [Order Count] >= 2)) + 0', "#,0"),
    "One-time Customers": ("[Customers] - [Repeat Customers]", "#,0"),
    "Repeat Purchase Rate": ("DIVIDE([Repeat Customers], [Customers])", "0.0%"),
    "Rated Order Count": ('CALCULATE(COUNT(Orders[review_score]), Orders[order_status] = "delivered")', "#,0"),
    "Average Review Score": ('CALCULATE(AVERAGE(Orders[review_score]), Orders[order_status] = "delivered")', "0.00"),
    "Comparable Review Score": ('CALCULATE([Average Review Score], KEEPFILTERS(Orders[delivery_band] IN {"Late", "On time"}))', "0.00"),
    "Average Delivery Days": ("AVERAGE(Orders[delivery_days])", "0.0"),
    "Late Orders": ('CALCULATE(COUNTROWS(Orders), KEEPFILTERS(Orders[delivery_band] = "Late"))', "#,0"),
    "Comparable Orders": ('CALCULATE(COUNTROWS(Orders), KEEPFILTERS(Orders[delivery_band] IN {"Late", "On time"}))', "#,0"),
    "Late Delivery Rate": ("DIVIDE([Late Orders], [Comparable Orders])", "0.0%"),
    "Item Count": ('CALCULATE(COUNTROWS(Items), Orders[order_status] = "delivered")', "#,0"),
    "Merchandise Orders": ('CALCULATE(DISTINCTCOUNT(Items[order_id]), Orders[order_status] = "delivered")', "#,0"),
    "Average Item Price": ("DIVIDE([Revenue], [Item Count])", currency),
    "Revenue Share": ("DIVIDE([Revenue], CALCULATE([Revenue], REMOVEFILTERS(Products[category])))", "0.0%"),
    "Paid Amount": ('CALCULATE(SUM(Payments[payment_value]), Orders[order_status] = "delivered")', currency),
    "Category Rank": ("IF(NOT ISBLANK([Revenue]), RANKX(ALLSELECTED(Products[category]), [Revenue], , DESC, DENSE))", "0"),
    "Top 10 Category Revenue": ("IF([Category Rank] <= 10, [Revenue])", currency),
}
types = {"string": "type text", "dateTime": "type date", "int64": "Int64.Type", "decimal": "Currency.Type"}


def import_table(name, spec):
    type_pairs = ", ".join(f'{{"{key}", {types[kind]}}}' for key, kind in spec.items())
    query = [
        "let",
        f'    Source = Csv.Document(File.Contents(DataFolder & "{name.lower()}.csv"), '
        '[Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),',
        "    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),",
        f'    Typed = Table.TransformColumnTypes(Headers, {{{type_pairs}}}, "en-US")',
        "in",
        "    Typed",
    ]
    fields = [
        {"name": col, "dataType": kind, "sourceColumn": col, "summarizeBy": "none",
         **({"formatString": "yyyy-mm-dd"} if kind == "dateTime" else {})}
        for col, kind in spec.items()
    ]
    return {"name": name, "columns": fields, "partitions": [
        {"name": name, "mode": "import", "source": {"type": "m", "expression": query}}
    ]}


tables = [import_table(name, spec) for name, spec in columns.items()]
tables[0]["columns"].append({"name": "Purchase Month", "type": "calculated", "dataType": "string",
                             "summarizeBy": "none", "expression": 'FORMAT(Orders[purchase_date], "yyyy-MM")'})
tables[0]["measures"] = [
    {"name": name, "expression": dax, "formatString": style} for name, (dax, style) in calculations.items()
]
relationships = [
    {"name": f"{many}_{one}", "fromTable": many, "fromColumn": col, "toTable": one,
     "toColumn": col, "crossFilteringBehavior": "oneDirection"}
    for many, one, col in [("Items", "Orders", "order_id"), ("Payments", "Orders", "order_id"),
                           ("Items", "Products", "product_id"), ("Items", "Sellers", "seller_id")]
]
folder = sys.argv[1] if len(sys.argv) > 1 else "C:\\Olist\\data\\clean\\"
if not folder.endswith(("/", "\\")):
    folder += "\\"
m_value = folder.replace('"', '""')
write(MODEL / "model.bim", {
    "name": "Olist", "compatibilityLevel": 1600, "model": {
        "culture": "en-US", "defaultPowerBIDataSourceVersion": "powerBI_V3",
        "sourceQueryCulture": "en-US", "tables": tables, "relationships": relationships,
        "expressions": [{"name": "DataFolder", "kind": "m",
                         "expression": f'"{m_value}" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]'}],
    }
})
artifact(MODEL / "definition.pbism", "semanticModel/definitionProperties/1.0.0", version="1.0")
artifact(REPORT / "definition.pbir", "report/definitionProperties/2.0.0", version="4.0",
         datasetReference={"byPath": {"path": "../Olist.SemanticModel"}})
write(ROOT / "Olist.pbip", {"$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json", "version": "1.0", "artifacts": [{"report": {"path": "Olist.Report"}}],
                            "settings": {"enableAutoRecovery": True}})
definition = REPORT / "definition"
artifact(definition / "version.json", "report/definition/versionMetadata/1.0.0", version="2.0.0")
theme = {"name": "CY24SU02", "reportVersionAtImport": {"report": "3.0.0", "page": "2.0.0", "visual": "2.0.0"},
         "type": "SharedResources"}
custom = {**theme, "name": "Olist", "type": "RegisteredResources"}
artifact(definition / "report.json", "report/definition/report/3.0.0",
         themeCollection={"baseTheme": theme, "customTheme": custom}, resourcePackages=[
             {"name": "Olist", "type": "RegisteredResources",
              "items": [{"name": "Olist", "path": "Olist.json", "type": "CustomTheme"}]}
         ])
write(REPORT / "StaticResources" / "RegisteredResources" / "Olist.json", {
    "name": "Olist", "dataColors": ["#087C7D", "#DB743F", "#3773A7", "#79AFB6", "#C8A26D", "#735A91"],
    "background": "#FFFFFF", "foreground": "#12304A", "tableAccent": "#087C7D",
})


def field(table, name, kind="Column"):
    return {kind: {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}}


def measure(name):
    return field("Orders", name, "Measure")


def literal(value):
    return {"expr": {"Literal": {"Value": value}}}


def visual(page, kind, title, x, y, w, h, roles=None):
    key = hashlib.sha1(f"{page}/{title}".encode()).hexdigest()[:20]
    config = {"visualType": kind, "drillFilterOtherVisuals": True,
              "visualContainerObjects": {"title": [{"properties": {
                  "show": literal("true"), "text": literal("'" + title.replace("'", "''") + "'"),
                  "fontSize": literal("13D"), "bold": literal("true")
              }}]}}
    if roles:
        config["query"] = {"queryState": {
            role: {"projections": [
                {"field": value, "queryRef": f"{spec['Expression']['SourceRef']['Entity']}.{spec['Property']}",
                 "nativeQueryRef": spec["Property"], "active": True}
                for value in fields for spec in value.values()
            ]} for role, fields in roles.items()
        }}
        if kind == "barChart":
            config["query"]["sortDefinition"] = {"sort": [{"field": roles["Y"][0], "direction": "Descending"}]}
    artifact(definition / "pages" / page / "visuals" / key / "visual.json",
             "report/definition/visualContainer/2.0.0", name=key,
             position={"x": x, "y": y, "z": 0, "width": w, "height": h, "tabOrder": y * 10 + x},
             visual=config)


def page_id(name):
    return hashlib.sha1(name.encode()).hexdigest()[:20]


def chart(page, kind, title, box, category, *values):
    visual(page, kind, title, *box, {"Category": [category], "Y": [measure(name) for name in values]})


def table(page, title, box, category, *values):
    visual(page, "tableEx", title, *box, {"Values": [category, *map(measure, values)]})


month = field("Orders", "Purchase Month")
state = field("Orders", "customer_state")
category = field("Products", "category")
band = field("Orders", "delivery_band")
page_specs = [
    ("Sales Overview", ["Revenue", "Order Count", "Average Order Value", "Average Review Score"]),
    ("Customer Analytics", ["Customers", "One-time Customers", "Repeat Customers", "Repeat Purchase Rate"]),
    ("Delivery Performance", ["Comparable Orders", "Late Orders", "Late Delivery Rate", "Average Delivery Days"]),
    ("Product Performance", ["Revenue", "Item Count", "Average Item Price", "Merchandise Orders"]),
]
ids = [page_id(name) for name, _ in page_specs]
left, right = (32, 236, 675, 450), (725, 236, 523, 450)
for index, (name, metrics) in enumerate(page_specs):
    page = ids[index]
    artifact(definition / "pages" / page / "page.json", "report/definition/page/2.0.0",
             name=page, displayName=name, width=1280, height=720, displayOption="FitToPage",
             objects={"background": [{"properties": {
                 "color": {"solid": {"color": literal("'#EEF4F8'")}}, "transparency": literal("0D")
             }}]})
    visual(page, "slicer", "Purchase month", 32, 18, 350, 89, {"Values": [month]})
    visual(page, "slicer", "Category" if index == 3 else "Customer state",
           400, 18, 350, 89, {"Values": [category if index == 3 else state]})
    for slot, metric in enumerate(metrics):
        visual(page, "card", metric, 32 + 307 * slot, 124, 295, 94, {"Values": [measure(metric)]})

sales, customers, delivery, products = ids
chart(sales, "lineChart", "Monthly merchandise revenue", left, month, "Revenue")
visual(sales, "donutChart", "Payment mix by amount", *right, {
    "Category": [field("Payments", "payment_type")], "Y": [measure("Paid Amount")]
})
chart(customers, "lineChart", "Active buyers and repeat buyers within month", left,
      month, "Customers", "Repeat Customers")
table(customers, "Buyer segments by state", right, state, "One-time Customers",
      "Repeat Customers", "Repeat Purchase Rate")
chart(delivery, "barChart", "Average review by delivery outcome", left, band, "Comparable Review Score")
table(delivery, "Delivery performance by state", right, state, "Comparable Orders",
      "Late Orders", "Late Delivery Rate", "Average Review Score", "Rated Order Count")
chart(products, "barChart", "Top 10 categories by merchandise revenue", left, category, "Top 10 Category Revenue")
table(products, "Merchandise contribution by category", right, category, "Revenue", "Revenue Share", "Item Count")
artifact(definition / "pages" / "pages.json", "report/definition/pagesMetadata/1.0.0",
         pageOrder=ids, activePageName=sales)
