"""Tiny hand-built Olist tables. Every expected value in the tests can be checked by hand."""
import pandas as pd
import pytest

T = pd.Timestamp
NA = pd.NaT


def _orders():
    rows = [
        # id,  status,      purchase,              approved,              carrier,               delivered,             estimated
        ("o1", "delivered", "2018-03-01 10:00", "2018-03-01 11:00", "2018-03-02 09:00", "2018-03-08 18:00", "2018-03-08"),  # on time, same day
        ("o2", "delivered", "2018-03-01 10:00", "2018-03-01 11:00", "2018-03-02 09:00", "2018-03-09 08:00", "2018-03-08"),  # 1 day late
        ("o3", "delivered", "2018-03-02 10:00", "2018-03-02 12:00", "2018-03-02 08:00", "2018-03-07 10:00", "2018-03-10"),  # carrier before approval
        ("o4", "delivered", "2018-03-02 10:00", "2018-03-02 11:00", "2018-03-03 10:00", None,                "2018-03-10"),  # delivered, no date
        ("o5", "canceled",  "2018-03-02 10:00", "2018-03-02 11:00", None,                "2018-03-06 10:00", "2018-03-10"),  # canceled w/ date
        ("o6", "shipped",   "2018-03-03 10:00", "2018-03-03 11:00", "2018-03-04 10:00", None,                "2018-03-12"),  # in progress
        ("o7", "delivered", "2018-03-03 10:00", "2018-03-03 11:00", "2018-03-04 10:00", "2018-03-06 10:00", "2018-03-12"),  # multi-seller
    ]
    df = pd.DataFrame(rows, columns=["order_id", "order_status", "order_purchase_timestamp", "order_approved_at",
                                     "order_delivered_carrier_date", "order_delivered_customer_date",
                                     "order_estimated_delivery_date"])
    for c in df.columns[2:]:
        df[c] = pd.to_datetime(df[c])
    df.insert(1, "customer_id", ["c" + r[1:] for r in df.order_id])
    df.insert(0, "source_record_no", range(1, len(df) + 1))
    return df


@pytest.fixture
def tables():
    orders = _orders()
    customers = pd.DataFrame({"customer_id": orders.customer_id, "customer_unique_id": orders.customer_id,
                              "customer_zip_code_prefix": ["01001"] * 7, "customer_city": "sp",
                              "customer_state": "SP"})
    items = pd.DataFrame([
        # o1: two lines of the SAME product (order_item_id distinguishes them) -> 2 lines, 1 product
        ("o1", 1, "p1", "s1", 10.0, 2.0), ("o1", 2, "p1", "s1", 10.0, 2.0),
        ("o2", 1, "p2", "s1", 50.0, 5.0), ("o3", 1, "p1", "s1", 10.0, 1.0),
        ("o4", 1, "p2", "s1", 50.0, 5.0), ("o5", 1, "p2", "s1", 50.0, 5.0),
        ("o6", 1, "p1", "s1", 10.0, 1.0),
        ("o7", 1, "p1", "s1", 10.0, 1.0), ("o7", 2, "p2", "s2", 50.0, 4.0),
    ], columns=["order_id", "order_item_id", "product_id", "seller_id", "price", "freight_value"])
    items["shipping_limit_date"] = T("2018-03-05")
    items.insert(0, "source_record_no", range(1, len(items) + 1))
    payments = pd.DataFrame([
        ("o1", 1, 12.0), ("o1", 2, 12.0),            # o1: 2 lines x 2 payments -> totals 24 and 24, not 48
        ("o2", 1, 55.0), ("o3", 1, 11.0), ("o4", 1, 55.0), ("o5", 1, 55.0), ("o6", 1, 11.0), ("o7", 1, 65.0),
    ], columns=["order_id", "payment_sequential", "payment_value"])
    payments.insert(0, "source_record_no", range(1, len(payments) + 1))
    reviews = pd.DataFrame([
        ("r1", "o1", 5, "2018-03-09 10:00", "2018-03-10 10:00"),
        ("r0", "o2", 3, "2018-03-05 10:00", "2018-03-05 12:00"),   # answered BEFORE delivery -> not primary
        ("r2", "o2", 1, "2018-03-10 10:00", "2018-03-11 10:00"),   # first answered after delivery -> primary
        ("r3", "o2", 2, "2018-03-12 10:00", "2018-03-13 10:00"),   # latest -> sensitivity
    ], columns=["review_id", "order_id", "review_score", "review_creation_date", "review_answer_timestamp"])
    for c in ["review_creation_date", "review_answer_timestamp"]:
        reviews[c] = pd.to_datetime(reviews[c])
    reviews.insert(0, "source_record_no", range(1, len(reviews) + 1))
    sellers = pd.DataFrame({"seller_id": ["s1", "s2"], "seller_zip_code_prefix": ["01002", "20000"],
                            "seller_city": "x", "seller_state": ["SP", "RJ"]})
    products = pd.DataFrame({"product_id": ["p1", "p2"], "product_category_name": ["a", "b"],
                             "product_weight_g": [100.0, None]})
    geo = pd.DataFrame({"geolocation_zip_code_prefix": ["01001", "01001", "01001", "01002", "20000"],
                        "geolocation_lat": [-23.55, -23.56, 40.0, -23.60, -22.90],   # 40.0 is outside Brazil
                        "geolocation_lng": [-46.63, -46.64, -3.0, -46.70, -43.20]})
    return {"orders": orders, "customers": customers, "order_items": items, "order_payments": payments,
            "order_reviews": reviews, "sellers": sellers, "products": products, "geolocation": geo}
