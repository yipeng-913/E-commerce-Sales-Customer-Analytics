"""Explore clean Olist data and export a reproducible portfolio snapshot."""
from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd

DATA = Path("data/clean")
DOCS = Path("docs")
DOCS.mkdir(exist_ok=True)
orders = pd.read_csv(DATA / "orders.csv", parse_dates=["purchase_date"])
items = pd.read_csv(DATA / "items.csv")
products = pd.read_csv(DATA / "products.csv")
payments = pd.read_csv(DATA / "payments.csv")
delivered = orders.loc[orders.order_status.eq("delivered")].copy()
sales = items.merge(delivered[["order_id", "purchase_date"]], on="order_id", validate="many_to_one")
sales = sales.merge(products, on="product_id", validate="many_to_one")
order_value = sales.groupby("order_id").price.sum()
delivered["revenue"] = delivered.order_id.map(order_value).fillna(0)
delivered["month"] = delivered.purchase_date.dt.to_period("M").astype(str)
monthly = delivered.groupby("month").agg(orders=("order_id", "size"), revenue=("revenue", "sum"))
cohorts = delivered.groupby("customer_unique_id").order_id.size()
repeat = cohorts.ge(2)
valid = delivered.loc[delivered.delivery_band.isin(["On time", "Late"])].copy()
valid["late"] = valid.delivery_band.eq("Late")
ratings = valid.groupby("delivery_band").review_score.agg(["mean", "count"])
states = valid.groupby("customer_state").late.agg(["sum", "size", "mean"]).sort_values("sum", ascending=False)
categories = sales.groupby("category").price.agg(["sum", "size"]).sort_values("sum", ascending=False)
order_distribution = (sales.groupby("order_id").size().value_counts()
                      .sort_index().rename_axis("items_per_order").rename("orders"))
order_distribution.to_csv(DOCS / "order-distribution.csv")
payment_mix = payments.loc[payments.order_id.isin(delivered.order_id)].groupby("payment_type").payment_value.sum()
payment_mix.sort_values(ascending=False).rename("paid_amount").to_csv(
    DOCS / "payment-mix.csv", float_format="%.2f")
revenue = delivered.revenue.sum()
for name, frame in (("monthly", monthly), ("delivery-states", states), ("categories", categories)):
    frame.to_csv(DOCS / f"{name}.csv", float_format="%.4f")

fig, axes = plt.subplots(2, 2, figsize=(14, 8.5), layout="constrained", facecolor="#eef4f8")
navy, teal, orange = "#12304a", "#117e7e", "#c65e38"
fig.suptitle("OLIST  /  BRAZIL E-COMMERCE PERFORMANCE", fontsize=21, weight="bold", color=navy)
for ax in axes.flat:
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_color("#dae4eb")
    ax.set_axisbelow(True)
    ax.tick_params(length=0, colors=navy, pad=6)
    ax.margins(x=.08)
ax = axes[0, 0]
ax.plot(monthly.index, monthly.revenue / 1e6, color=teal, linewidth=2.5)
ax.fill_between(monthly.index, 0, monthly.revenue / 1e6, color=teal, alpha=.11)
ax.set_xticks(monthly.index[::4])
ax.grid(axis="y", color="#e1e9ef")
ax.set_ylabel("BRL millions")
ax.set_title(f"Sales  |  R$ {revenue / 1e6:.2f}M  ·  {len(delivered):,} orders", loc="left", color=navy)
ax = axes[0, 1]
customer_counts = [int((~repeat).sum()), int(repeat.sum())]
bars = ax.barh(["Repeat", "One-time"], customer_counts[::-1], color=[orange, teal])
ax.bar_label(bars, labels=[f"{n:,}" for n in customer_counts[::-1]], padding=5)
ax.set_xlim(0, max(customer_counts) * 1.2)
ax.set_title(f"Customers  |  {repeat.mean():.1%} repeat purchase rate", loc="left", color=navy)
ax = axes[1, 0]
bars = ax.barh(["Late", "On time"], ratings.loc[["Late", "On time"], "mean"], color=[orange, teal])
ax.bar_label(bars, fmt="%.2f", padding=5)
ax.set_xlim(0, 5)
ax.set_xlabel("Average review score out of 5")
ax.set_title(f"Delivery  |  {valid.late.mean():.1%} late", loc="left", color=navy)
ax = axes[1, 1]
top = categories.head(6).iloc[::-1]
ax.barh(top.index.str.replace("_", " ").str.title(), top["sum"] / 1e6, color=teal)
ax.set_xlabel("BRL millions")
ax.set_title("Products  |  Top six categories by revenue", loc="left", color=navy)
fig.savefig(DOCS / "dashboard-preview.png", dpi=135, bbox_inches="tight")
plt.close(fig)

report = f"""# Olist 巴西电商分析报告

公开 Olist 数据。成交指标统计已交付订单，货币为巴西雷亚尔（BRL）。收入为商品价格合计，运费和支付金额单独统计。迟到按实际送达日超过承诺日期判断，比较使用日历日期。

| 指标 | 结果 |
| --- | ---: |
| 总订单（所有状态） | {len(orders):,} |
| 已交付订单 | {len(delivered):,} |
| 商品收入 | R$ {revenue:,.2f} |
| 已交付订单平均商品金额 | R$ {revenue / len(delivered):,.2f} |
| 已交付买家 | {len(cohorts):,} |
| 复购买家 | {repeat.sum():,}（{repeat.mean():.2%}） |
| 可判断是否迟到的订单 | {len(valid):,} |
| 迟到订单 | {valid.late.sum():,}（{valid.late.mean():.2%}） |
| 送达时长中位数 | {delivered.delivery_days.median():.0f} 天 |
| 每单商品件数中位数（有商品行的已交付订单） | {sales.groupby("order_id").size().median():.0f} |

## 优先行动

1. **先查 RJ 配送线路，同时降低 SP 的迟到量。** RJ 有 {int(states.loc["RJ", "sum"]):,} 单迟到，迟到率为 {states.loc["RJ", "mean"]:.2%}。SP 迟到量最高（{int(states.loc["SP", "sum"]):,} 单），迟到率为 {states.loc["SP", "mean"]:.2%}。先按目的州、发货州和承运线路拆分时效，跟踪每周迟到单数与分母。
2. **在可能逾期时主动通知。** 迟到订单的平均评分为 {ratings.loc["Late", "mean"]:.2f}（有评分 {int(ratings.loc["Late", "count"]):,} 单），准时订单为 {ratings.loc["On time", "mean"]:.2f}（有评分 {int(ratings.loc["On time", "count"]):,} 单）。试点预计超时提醒并记录送达及时率与低分比例。评分差异属于观察性关联。
3. **优先保障头部品类可用库存。** 美妆健康、钟表礼品、床浴餐桌合计贡献 {categories.head(3)["sum"].sum() / revenue:.1%} 的商品收入。建议对这三类先做热销商品缺货与商家履约监控，再用利润、退货和库存数据验证投入优先级。
4. **开展首单后复购试验。** 观察期内 {repeat.mean():.2%} 的买家完成两单及以上。用有完整观察期的新客做 60/90 天分组试验，比较触达组与对照组的复购率。接近数据截止期的买家有较短的复购观察时间。

## 趋势与口径

2017 年 11 月达到 R$ {monthly.loc["2017-11", "revenue"]:,.2f} 与 {int(monthly.loc["2017-11", "orders"]):,} 单，为已交付订单历史月度峰值。数据首尾月份覆盖不完整。按订单状态筛选、按支付方式拆分和按品类拆分时，分别使用订单、支付记录和商品行粒度。最近一次有效评分代表该订单。

[公开 Olist 数据集](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
"""
(DOCS / "report.zh-CN.md").write_text(report, encoding="utf-8")
