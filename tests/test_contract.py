import pandas as pd

from olist_analytics.contract import check_contract
from olist_analytics.io import CONTRACT


def test_contract_flags_duplicate_key_and_bad_zip(tables):
    t = dict(tables)
    t["orders"] = pd.concat([t["orders"], t["orders"].iloc[[0]]], ignore_index=True)
    t["customers"] = t["customers"].assign(customer_zip_code_prefix=["1001"] + ["01001"] * 6)   # lost leading zero
    t["category_translation"] = pd.DataFrame({"product_category_name": ["a"], "product_category_name_english": ["a"]})
    r = check_contract(t).set_index(["table", "check"])
    assert r.loc[("orders", "unique key (order_id)"), "status"] == "FAIL"
    assert r.loc[("customers", "zip prefix is 5 digits (string): customer_zip_code_prefix"), "violations"] == 1


def test_review_key_is_review_id_plus_order_id():
    assert CONTRACT["order_reviews"]["key"] == ["review_id", "order_id"]
    assert CONTRACT["order_items"]["key"] == ["order_id", "order_item_id"]


def test_orders_customer_foreign_key_is_checked(tables):
    t = dict(tables)
    t["customers"] = t["customers"][t["customers"].customer_id != "c1"]
    t["category_translation"] = pd.DataFrame({"product_category_name": ["a"], "product_category_name_english": ["a"]})
    r = check_contract(t).set_index(["table", "check"])
    assert r.loc[("orders", "foreign key customer_id -> customers.customer_id"), "violations"] == 1
