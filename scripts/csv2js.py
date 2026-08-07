#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
csv2js.py — 把 data.csv（Excel 可编辑）转换成 data.js（网页读取的数据）

用法（在项目根目录运行）:
    python3 scripts/csv2js.py

说明:
    - data.csv 必须保持 UTF-8 编码（Excel 另存为时选"CSV UTF-8"）
    - 表头（第一行）不要改动，多值字段（focus / services）用 | 分隔
    - 脚本会备份旧的 data.js 为 data.js.bak，然后生成新的 data.js
"""
import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(ROOT, "data.csv")
JS_PATH = os.path.join(ROOT, "data.js")

HEADER_TMPL = """/*
 * 朝阳区产业孵化器数据（标准化格式）
 * 本文件由 scripts/csv2js.py 从 data.csv 自动生成，请勿手改；如需修改请编辑 data.csv 后重新生成。
 */
window.PARK_DATA = %s;
"""


def read_csv(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit("data.csv 为空或没有数据行")
    return rows


def normalize(rows):
    out = []
    # 行业版字段：与 data.csv 表头一一对应
    STR_FIELDS = [
        "id", "name", "district", "area", "type", "address",
        "focus", "services", "website", "contact", "description",
        "source", "level", "landType", "huanping", "weifei", "bsl", "gmp", "medical", "lab", "analyze",
        "animal", "pilot", "utility", "coldchain", "fitout", "subsidy",
        "fund", "talent", "approval", "metro", "hospital", "operator", "benchmark",
        # Obsidian 同步字段（v5）
        "updateTime", "rentRange", "feeNote", "terms", "bus", "tenants",
        "areaNote", "leaseNote", "height", "location", "highlight", "delivery", "advantage",
    ]
    LIST_FIELDS = ["photos", "updateLog"]  # CSV 中 | 分隔，转数组
    NUM_FIELDS = {
        "lat": "lat", "lng": "lng", "areaSqm": "areaSqm",
        "rent": "rent", "propertyFee": "propertyFee",
        "freeMonths": "freeMonths", "occupancy": "occupancy",
    }
    INT_FIELDS = ["founded", "enterprises"]
    for i, r in enumerate(rows):
        def g(k):
            return (r.get(k) or "").strip()
        record = {}
        for k in STR_FIELDS:
            record[k] = g(k)
        for k in LIST_FIELDS:
            v = g(k)
            record[k] = [x for x in v.split("|")] if v else []
        for k in NUM_FIELDS:
            record[k] = _num(g(k), i + 2)
        for k in INT_FIELDS:
            record[k] = _int(g(k))
        if not record.get("id") or not record.get("name"):
            print("  [警告] 第 %d 行缺少 id 或 name，已跳过" % (i + 2))
            continue
        out.append(record)
    return out


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _num(v, lineno):
    try:
        return float(v)
    except (TypeError, ValueError):
        print("  [警告] 第 %d 行经纬度/面积格式不正确: %r，已置 0" % (lineno, v))
        return 0.0


def main():
    rows = read_csv(CSV_PATH)
    records = normalize(rows)
    if not records:
        raise SystemExit("没有可用的数据行，请检查 data.csv")
    js = HEADER_TMPL % json.dumps(records, ensure_ascii=False, indent=2)
    if os.path.exists(JS_PATH):
        os.replace(JS_PATH, JS_PATH + ".bak")
    with open(JS_PATH, "w", encoding="utf-8") as f:
        f.write(js)
    print("完成：共 %d 条记录 → data.js（旧文件已备份为 data.js.bak）" % len(records))


if __name__ == "__main__":
    main()
