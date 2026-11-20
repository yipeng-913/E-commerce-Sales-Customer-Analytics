"""Build grain-safe datasets from the nine Olist exports."""
import argparse
import io
import json
from pathlib import Path
from zipfile import ZipFile

import pandas as pd

SOURCES = {
    name: f"olist_{name}_dataset.csv"
    for name in ("customers", "geolocation", "order_items", "order_payments",
                 "order_reviews", "orders", "products", "sellers")
}
SOURCES["translation"] = "product_category_name_translation.csv"


def prepare(source, target):
    if source.is_dir():
        payload = {key: (source / filename).read_bytes() for key, filename in SOURCES.items()}
    else:
        with ZipFile(source) as archive:
            names = {Path(name).name: name for name in archive.namelist() if not name.endswith("/")}
            payload = {key: archive.read(names[filename]) for key, filename in SOURCES.items()}

    tables, audit = {}, {}
    for name, data in payload.items():
        frame = pd.read_csv(io.BytesIO(data), dtype={key: "string" for key in (
            "customer_zip_code_prefix", "seller_zip_code_prefix", "geolocation_zip_code_prefix"
        )})
        audit[name] = {"raw_rows": len(frame), "exact_duplicates": int(frame.duplicated().sum()),
                       "null_counts": frame.isna().sum().to_dict(), "invalid_dates": {}}
        frame = frame.drop_duplicates().copy()
        for col in frame:
            if col.endswith(("_date", "_timestamp", "_at")):
                parsed = pd.to_datetime(frame[col], errors="coerce")
                audit[name]["invalid_dates"][col] = int((frame[col].notna() & parsed.isna()).sum())
                frame[col] = parsed
        tables[name] = frame

    geo = tables["geolocation"]
    valid = geo.geolocation_lat.between(-34, 6) & geo.geolocation_lng.between(-74, -32)
    audit["geolocation"]["excluded_outside_coordinate_bounds"] = int((~valid).sum())
    geo = geo.loc[valid].groupby("geolocation_zip_code_prefix", as_index=False)[
        ["geolocation_lat", "geolocation_lng"]].median()

    customers = tables["customers"][["customer_id", "customer_unique_id", "customer_state"]]
    orders = tables["orders"].merge(customers, on="customer_id", validate="one_to_one")
    items = tables["order_items"].copy()
    valid_money = items.price.ge(0) & items.freight_value.ge(0)
    audit["order_items"]["excluded_invalid_money_rows"] = int((~valid_money).sum())
    items = items.loc[valid_money].copy()
    products = tables["products"][["product_id", "product_category_name"]].merge(
        tables["translation"], how="left", on="product_category_name", validate="many_to_one")
    products["category"] = products.product_category_name_english.fillna(
        products.product_category_name).fillna("unknown")
    payments = tables["order_payments"].copy()
    audit["order_payments"]["invalid_money_values"] = int((~payments.payment_value.ge(0)).sum())
    payments.loc[~payments.payment_value.ge(0), "payment_value"] = pd.NA
    payments["payment_type"] = payments.payment_type.fillna("unknown")
    reviews = tables["order_reviews"].copy()
    valid_reviews = reviews.review_score.between(1, 5)
    audit["order_reviews"]["excluded_invalid_scores"] = int((~valid_reviews).sum())
    latest = reviews.loc[valid_reviews].sort_values(
        ["review_answer_timestamp", "review_creation_date", "review_id", "review_score"],
        na_position="first").drop_duplicates("order_id", keep="last")
    audit["order_reviews"]["superseded_valid_reviews"] = int(valid_reviews.sum() - len(latest))
    orders = orders.merge(latest[["order_id", "review_score"]], how="left", on="order_id",
                          validate="one_to_one")
    orders["purchase_date"] = orders.order_purchase_timestamp.dt.normalize()
    delivered_date = orders.order_delivered_customer_date.dt.normalize()
    estimate = orders.order_estimated_delivery_date.dt.normalize()
    orders["delivery_days"] = (delivered_date - orders.purchase_date).dt.days
    valid_delivery = (
        orders.order_status.eq("delivered") & orders.delivery_days.ge(0)
    )
    audit["orders"]["negative_delivery_intervals"] = int(orders.delivery_days.lt(0).sum())
    orders["delivery_days"] = orders.delivery_days.where(valid_delivery).astype("Int64")
    comparable = valid_delivery & estimate.notna() & estimate.ge(orders.purchase_date)
    orders["delivery_band"] = "Unassessable"
    orders.loc[comparable, "delivery_band"] = "On time"
    orders.loc[comparable & delivered_date.gt(estimate), "delivery_band"] = "Late"
    orders["review_score"] = orders.review_score.astype("Int64")
    audit["orders"]["delivery_unassessable"] = int((~comparable).sum())
    audit["orders"]["missing_purchase_dates"] = int(orders.purchase_date.isna().sum())
    orders = orders.loc[orders.purchase_date.notna(), [
        "order_id", "customer_id", "customer_unique_id", "customer_state", "order_status",
        "purchase_date", "delivery_days", "delivery_band", "review_score"
    ]]
    orders["customer_state"] = orders.customer_state.fillna("Unknown")
    orders["order_status"] = orders.order_status.fillna("unknown")
    output = {
        "orders": orders,
        "items": items.loc[items.order_id.isin(orders.order_id),
                           ["order_id", "order_item_id", "product_id", "seller_id", "price", "freight_value"]],
        "payments": payments.loc[payments.order_id.isin(orders.order_id),
                                 ["order_id", "payment_sequential", "payment_type", "payment_value"]],
        "products": products[["product_id", "category"]],
        "sellers": tables["sellers"][["seller_id", "seller_state"]],
        "geolocation": geo,
    }
    for name, frame in output.items():
        keys = {"orders": ["order_id"], "items": ["order_id", "order_item_id"],
                "payments": ["order_id", "payment_sequential"], "products": ["product_id"],
                "sellers": ["seller_id"], "geolocation": ["geolocation_zip_code_prefix"]}[name]
        if frame[keys].isna().any().any() or frame.duplicated(keys).any():
            raise ValueError(f"Null or duplicate key in {name}")
        target.mkdir(parents=True, exist_ok=True)
        frame.to_csv(target / f"{name}.csv", index=False)
    (target / "quality.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Original ZIP or directory with all nine CSVs")
    parser.add_argument("--output", type=Path, default=Path("data/clean"))
    args = parser.parse_args()
    prepare(args.source, args.output)
