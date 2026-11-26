"""The raw layer's contract: one explicit schema per source file.

Nothing is auto-detected. A file whose columns or types do not match fails the load instead of
landing as a table of strings. Times are DATETIME, not TIMESTAMP: the source records Brazilian
local time with no zone, and calling it UTC would shift every hour (docs/adr/0003).
"""

from __future__ import annotations

from dataclasses import dataclass

STRING, INT, NUM, DT = "STRING", "INT64", "NUMERIC", "DATETIME"

# Columns the loader adds to the four change tables (orders, items, payments, reviews), which
# hold one row per version of a record as the daily replay delivers it (pipeline/replay.py).
BATCH_COLUMNS = (
    ("_batch", INT, "REQUIRED"),  # replay batch; the table is integer-range partitioned on it
    ("_as_of", "DATE", "REQUIRED"),  # the simulated date the row is known at
    ("_loaded_at", "TIMESTAMP", "REQUIRED"),  # real load time
)


@dataclass(frozen=True)
class RawTable:
    name: str
    file: str
    columns: tuple[tuple[str, str, str], ...]  # (name, type, mode)
    description: str

    @property
    def key(self) -> str:
        return self.columns[0][0]


def _cols(*spec: tuple[str, str] | tuple[str, str, str]) -> tuple[tuple[str, str, str], ...]:
    return tuple((c[0], c[1], c[2] if len(c) == 3 else "NULLABLE") for c in spec)


RAW_TABLES: tuple[RawTable, ...] = (
    RawTable("orders", "olist_orders_dataset.csv", _cols(
        ("order_id", STRING, "REQUIRED"), ("customer_id", STRING, "REQUIRED"), ("order_status", STRING, "REQUIRED"),
        ("order_purchase_timestamp", DT, "REQUIRED"), ("order_approved_at", DT),
        ("order_delivered_carrier_date", DT), ("order_delivered_customer_date", DT),
        ("order_estimated_delivery_date", DT),
    ), "One row per order."),
    RawTable("customers", "olist_customers_dataset.csv", _cols(
        ("customer_id", STRING, "REQUIRED"), ("customer_unique_id", STRING, "REQUIRED"),
        ("customer_zip_code_prefix", STRING), ("customer_city", STRING), ("customer_state", STRING),
    ), "One row per customer id; customer_unique_id identifies the person across orders."),
    RawTable("order_items", "olist_order_items_dataset.csv", _cols(
        ("order_id", STRING, "REQUIRED"), ("order_item_id", INT, "REQUIRED"), ("product_id", STRING, "REQUIRED"),
        ("seller_id", STRING, "REQUIRED"), ("shipping_limit_date", DT), ("price", NUM), ("freight_value", NUM),
    ), "One row per item in an order."),
    RawTable("order_payments", "olist_order_payments_dataset.csv", _cols(
        ("order_id", STRING, "REQUIRED"), ("payment_sequential", INT), ("payment_type", STRING),
        ("payment_installments", INT), ("payment_value", NUM),
    ), "One row per payment; an order can be paid in several."),
    RawTable("order_reviews", "olist_order_reviews_dataset.csv", _cols(
        ("review_id", STRING, "REQUIRED"), ("order_id", STRING, "REQUIRED"), ("review_score", INT),
        ("review_comment_title", STRING), ("review_comment_message", STRING),
        ("review_creation_date", DT), ("review_answer_timestamp", DT),
    ), "Customer reviews; a few orders have more than one."),
    RawTable("products", "olist_products_dataset.csv", _cols(
        ("product_id", STRING, "REQUIRED"), ("product_category_name", STRING),
        ("product_name_lenght", INT), ("product_description_lenght", INT), ("product_photos_qty", INT),
        ("product_weight_g", INT), ("product_length_cm", INT), ("product_height_cm", INT), ("product_width_cm", INT),
    ), "One row per product; column names keep the source's spelling."),
    RawTable("sellers", "olist_sellers_dataset.csv", _cols(
        ("seller_id", STRING, "REQUIRED"), ("seller_zip_code_prefix", STRING), ("seller_city", STRING),
        ("seller_state", STRING),
    ), "One row per seller."),
    RawTable("product_category_name_translation", "product_category_name_translation.csv", _cols(
        ("product_category_name", STRING, "REQUIRED"), ("product_category_name_english", STRING, "REQUIRED"),
    ), "Portuguese category name to English."),
)  # fmt: skip

# Not loaded: olist_geolocation_dataset.csv (1M rows, 59 MB) feeds no model, and the sandbox's
# 10 GiB storage allowance is for the lifetime of the project (docs/adr/0001).
SKIPPED_FILES = ("olist_geolocation_dataset.csv",)
