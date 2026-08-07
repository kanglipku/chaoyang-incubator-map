#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
obsidian_parser.py — 以 Obsidian 笔记为数据源，同步园区信息到 data.js

用法:
    python3 scripts/obsidian_parser.py

数据源目录（可配置）:
    /Users/kangli/obsidian/工作/3-2 企业落地/园区信息/*.md

笔记格式（两种标签均支持）:
    ［园区］名称　／　【项目】名称
    ［面积］［报价］［其他费用］［商务条款］［区位］［地铁］［公交］［配套］...
    【租赁面积】【位置】【层高】【物业费】【园区配套】【入驻企业】...
    图片: ![](file:///.../wps1.jpg) 或 相对路径 或 http(s)://

对齐规则:
    - 笔记名与现有园区按名称包含匹配（如"电通创意广场15号楼D区"→"电通创意广场"）
    - 已存在: 用笔记字段更新对应字段，非空才覆盖；记录 updateTime + updateLog（追加）
    - 不存在: 新增园区记录（photos 一并收录）
    - 图片: 自动拷贝到 photos/{园区id}/ 并写入 photos 字段
"""
import json
import os
import re
import shutil
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_JS = os.path.join(ROOT, "data.js")
DATA_CSV = os.path.join(ROOT, "data.csv")
PHOTOS_DIR = os.path.join(ROOT, "photos")
OBSIDIAN_DIR = "/Users/kangli/obsidian/工作/3-2 企业落地/园区信息"

TODAY = date.today().isoformat()

# 笔记名关键词 → 现有园区 id（保证可靠对齐）
NAME_MAP = [
    ("电通创意广场", "diantong-001"),
    ("恒通国际创新园", "hengtong-001"),
    ("望京", "wangjing-001"),
    ("电子城", "jiuxianqiao-001"),
    ("普天", "putian-001"),
    ("创E+", "chuange-001"),
    ("牡丹", "mudan-001"),
    ("瀚海", "hanhai-001"),
    ("时代凌宇", "shidailingyu-001"),
    ("零秒", "lingshui-001"),
    ("融新", "rongxin-001"),
    ("创业大厦", "beichuang-001"),
    ("山河湾谷", "shwhgu-001"),
    ("微电子", "weidianzi-001"),
    ("集成电路", "dzcic-001"),
    ("黑马", "heima-001"),
    ("瀚誉", "hanyu-001"),
    ("朝科创", "chaokechuang-001"),
    ("氪星", "kexing-001"),
    ("E9", "e9-001"),
    ("生命科学园", "wangjingsmkx-001"),
    ("未来显示", "weilai-001"),
    ("金盏", "jinzhan-001"),
    ("CBD数字经济", "cbdcenter-001"),
    ("数字人", "shuziren-001"),
    ("AI Space", "aispace-001"),
    ("未来信息园", "wangjingwl-001"),
    ("优客工场", "jianguomen-002"),
    ("三里屯", "sanlitun-001"),
]

# 标签 → 数据字段（［］和【】通用）
FIELD_MAP = {
    "园区": "name", "项目": "name",
    "面积": "area_note", "租赁面积": "lease_note",
    "报价": "rent_note", "租金": "rent_note",
    "其他费用": "fee_note", "物业费": "prop_note",
    "商务条款": "terms", "区位": "address_note",
    "地理位置": "address_note", "地铁": "metro",
    "公交": "bus", "配套": "services",
    "园区配套": "services", "入驻企业": "tenants",
    "项目优势": "advantage", "层高": "height",
    "位置": "location", "户型亮点": "highlight",
    "交付标准": "delivery", "园区图片": "photo_group",
    "坐标": "latlng", "经纬度": "latlng", "定位": "latlng",
}

# 恢复园区时的真实坐标（按公开地址）: 园区 id → (lat, lng)
LATLNG_FIX = {
    "diantong-001": (39.9800, 116.4980),   # 酒仙桥北路7号 电通创意广场
    "hengtong-001": (39.9780, 116.4990),   # 酒仙桥北路9号 恒通国际创新园
}


def read_data():
    s = open(DATA_JS, encoding="utf-8").read()
    return json.loads(re.search(r"window\.PARK_DATA = (\[.*?\]);", s, re.S).group(1))


def write_data(records):
    HEADER = """/*
 * 朝阳区产业孵化器数据（行业版 v5 · Obsidian 数据源同步）
 * 本文件由 scripts/obsidian_parser.py / build_data.py 生成。
 * 数据源: Obsidian 园区信息笔记 + 手工维护字段；photos 为园区照片。
 */
window.PARK_DATA = %s;
"""
    with open(DATA_JS, "w", encoding="utf-8") as f:
        f.write(HEADER % json.dumps(records, ensure_ascii=False, indent=2))


def parse_note(path):
    """解析一篇笔记，返回 {字段: 值} 与图片路径列表"""
    text = open(path, encoding="utf-8").read()
    fields = {}
    imgs = re.findall(r"!\[[^\]]*\]\(\s*([^)\s]+)\s*\)", text)
    # 按标签切分（支持 ASCII [ ] 与全角 ［ ］ 【 】
    parts = re.split(r"[\[【［]([^\]】］]{1,16})[\]】］]", text)
    # parts[0] 是前置文本, 之后每两个一组 (标签, 内容)
    for i in range(1, len(parts), 2):
        tag = parts[i].strip()
        content = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if not tag:
            continue
        # 去掉内容中的图片行
        content = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", content).strip()
        content = re.sub(r"\s*\n\s*", "；", content).strip("；")
        if content and tag in FIELD_MAP:
            fld = FIELD_MAP[tag]
            if fld == "photo_group":
                continue
            fields[fld] = content
    return fields, imgs


def match_park(note_name):
    for kw, pid in NAME_MAP:
        if kw in note_name:
            return pid
    return None


def collect_photos(pid, imgs):
    """拷贝图片到 photos/{pid}/，返回相对路径列表（去重）"""
    target_dir = os.path.join(PHOTOS_DIR, pid)
    os.makedirs(target_dir, exist_ok=True)
    out, seen = [], set()
    for img in imgs:
        img = img.strip()
        if not img:
            continue
        src = None
        if img.startswith("file://"):
            src = img[len("file://"):]
        elif img.startswith(("http://", "https://")):
            # 在线图片暂不下载，记录原链接
            out.append(img)
            continue
        elif os.path.exists(img):
            src = img
        elif os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), img)):
            src = img
        if not src or not os.path.exists(src):
            continue
        if not src.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            continue
        ext = os.path.splitext(src)[1].lower()
        name = str(len(out) + 1) + ext
        dest = os.path.join(target_dir, name)
        if os.path.abspath(src) != os.path.abspath(dest):
            shutil.copy2(src, dest)
        rel = "photos/%s/%s" % (pid, name)
        if rel not in seen:
            seen.add(rel)
            out.append(rel)
    return out


def _ensure_industry(rec):
    """补齐缺失的行业字段（幂等，不覆盖已有值）"""
    defaults = {
        "文创园区": dict(huanping="文创/办公业态（待核实）", weifei="无实验室危废处理条件", bsl="无",
                         gmp="无", medical="不适用", lab="无", analyze="无", animal="无", pilot="无",
                         utility="普通供电", coldchain="无", fitout="老厂房改造/创意空间",
                         subsidy="文创产业扶持政策（待核实）", fund="文创基金对接", talent="人才政策",
                         approval="不适用", occupancy=85, operator="园区运营方（待核实）",
                         benchmark="待核实（建议现场调研补充）", rent=3.5, propertyFee=10, freeMonths=2),
        "科技孵化器": dict(huanping="园区环评批复（待核实）", weifei="园区统一危废处置（待核实）", bsl="P1",
                         gmp="无现成洁净区", medical="可探讨", lab="待核实", analyze="待核实", animal="无",
                         pilot="待核实", utility="双回路电|UPS", coldchain="无", fitout="毛坯/精装可选",
                         subsidy="朝阳区房租补贴/中关村政策（待核实）", fund="待核实", talent="人才政策",
                         approval="待核实", occupancy=80, operator="园区运营方（待核实）",
                         benchmark="待核实（建议现场调研补充）", rent=4.0, propertyFee=10, freeMonths=2),
        "综合孵化器": dict(huanping="商务/办公业态（待核实）", weifei="无", bsl="无", gmp="无",
                         medical="不适用", lab="无", analyze="无", animal="无", pilot="无",
                         utility="商务标准供电", coldchain="无", fitout="精装办公/工位制",
                         subsidy="无专项补贴", fund="投融资路演对接", talent="无专项",
                         approval="不适用", occupancy=85, operator="园区运营方（待核实）",
                         benchmark="待核实（建议现场调研补充）", rent=5.0, propertyFee=12, freeMonths=1),
        "数字经济": dict(huanping="办公/园区业态（待核实）", weifei="无", bsl="无", gmp="无",
                       medical="不适用", lab="无", analyze="算力/平台（待核实）", animal="无", pilot="无",
                       utility="双回路电|UPS", coldchain="无", fitout="精装/毛坯可选",
                       subsidy="中关村/朝阳区政策（待核实）", fund="产业基金（待核实）", talent="人才政策",
                       approval="待核实", occupancy=80, operator="园区运营方（待核实）",
                       benchmark="待核实（建议现场调研补充）", rent=4.0, propertyFee=10, freeMonths=2),
    }
    for k, v in defaults.get(rec.get("type", ""), {}).items():
        if k not in rec or rec[k] in (None, ""):
            rec[k] = v


def apply_park(records, by_id, note_name, fields, imgs):
    pid = match_park(note_name)
    today = TODAY
    if pid and pid in by_id:
        rec = by_id[pid]
        # 应用真实坐标（笔记未提供坐标时）
        if pid in LATLNG_FIX and "latlng" not in fields:
            rec["lat"], rec["lng"] = LATLNG_FIX[pid]
        _ensure_industry(rec)
        return _align_park(rec, fields, imgs, today), pid
    # 有映射但不在数据里（如曾被移除的园区）→ 按原 id 恢复；无映射 → 新建
    if pid:
        new_id = pid
        type_, level = _restore_meta(pid)
    else:
        new_id = "obsidian-%02d" % (len(by_id) + 1)
        type_, level = "科技孵化器", "其他"
    rec = {
        "id": new_id, "name": note_name.replace(".md", ""),
        "district": "", "area": "", "type": type_,
        "address": fields.get("address_note", ""),
        "lat": 39.92, "lng": 116.44, "founded": 0,
        "areaSqm": 0, "enterprises": 0,
        "focus": "", "services": fields.get("services", ""),
        "website": "", "contact": "",
        "description": fields.get("advantage", ""),
        "source": "Obsidian 园区信息笔记（待核实）", "level": level,
        "landType": "C65" if type_ == "文创园区" else "B2", "photos": [],
    }
    # 补充默认行业字段（待 Obsidian 补充后覆盖）
    _ensure_industry(rec)
    # 恢复园区使用真实坐标（否则地图标签位置错误）
    if new_id in LATLNG_FIX:
        rec["lat"], rec["lng"] = LATLNG_FIX[new_id]
    _align_park(rec, fields, imgs, today)  # 复用解析逻辑（租金/物业/配套/照片等）
    rec["name"] = note_name.replace(".md", "")
    if fields.get("address_note"):
        rec["address"] = fields["address_note"]
    rec["updateLog"] = ["%s：新建园区（来自 Obsidian 笔记，待补充核实）" % today]
    records.append(rec)
    by_id[new_id] = rec
    return True, new_id


def _restore_meta(pid):
    """被移除园区恢复时的类型/级别预设"""
    if pid in ("diantong-001", "hengtong-001", "798-001", "751-001", "jianguomen-001",
               "baiziwan-001", "e9-001", "tonghuihepan-001", "beidianying-001"):
        return "文创园区", "省市级"
    return "科技孵化器", "省市级"


def _align_park(rec, fields, imgs, today):
    """对齐更新已有园区，返回变更描述"""
    changed = []
    for fld, val in fields.items():
        if not val:
            continue
        if fld in ("rent_note",):
            m = re.search(r"([\d.]+)-?([\d.]*)", val)
            if m:
                lo = float(m.group(1))
                rec["rent"] = lo if not m.group(2) else round((lo + float(m.group(2))) / 2, 1)
            rec["rentRange"] = val
            changed.append("租金报价 " + val)
        elif fld == "prop_note":
            m = re.search(r"([\d.]+)", val)
            if m:
                rec["propertyFee"] = float(m.group(1))
            changed.append("物业费 " + val)
        elif fld in ("fee_note", "terms", "bus", "tenants", "metro"):
            key = "feeNote" if fld == "fee_note" else fld
            rec[key] = val
            if fld == "fee_note":
                m = re.search(r"物业费\s*([\d.]+)\s*元", val)
                if m:
                    rec["propertyFee"] = float(m.group(1))
            changed.append(FIELD_CN.get(fld, fld) + " " + val[:50])
        elif fld == "services":
            rec["services"] = val
            changed.append("配套 " + val[:50])
        elif fld == "latlng":
            m = re.search(r"([\d.]+)\s*[,，]\s*([\d.]+)", val)
            if m:
                rec["lat"] = float(m.group(1))
                rec["lng"] = float(m.group(2))
            changed.append("坐标 " + val[:30])
        elif fld in ("address_note", "area_note", "lease_note", "advantage",
                     "height", "location", "highlight", "delivery"):
            key = {"address_note": "address", "area_note": "areaNote",
                   "lease_note": "leaseNote", "advantage": "advantage",
                   "height": "height", "location": "location",
                   "highlight": "highlight", "delivery": "delivery"}[fld]
            if val and val != rec.get(key, ""):
                rec[key] = val
                if fld == "area_note":
                    m = re.search(r"([\d.]+)\s*万㎡", val) or re.search(r"([\d.]+)㎡", val)
                    if m:
                        n = float(m.group(1))
                        rec["areaSqm"] = round(n / 10000, 2) if n > 1000 else round(n, 2)
                changed.append(FIELD_CN.get(fld, fld) + " " + val[:50])
    if imgs:
        photos = collect_photos(rec["id"], imgs)
        if photos:
            rec["photos"] = sorted(set(list(rec.get("photos", [])) + photos))
            changed.append("照片 ×%d" % len(photos))
    if changed:
        rec["updateTime"] = today
        logs = list(rec.get("updateLog", []))
        entry = "%s：对齐 Obsidian 更新——%s" % (today, "；".join(changed))
        # 同日重复运行：覆盖当天最后一条，避免堆积重复日志
        if logs and logs[-1].startswith(today):
            logs[-1] = entry
        else:
            logs.append(entry)
        rec["updateLog"] = logs
    return True


FIELD_CN = {
    "address_note": "地址", "area_note": "面积", "lease_note": "租赁面积",
    "advantage": "项目优势", "height": "层高", "location": "位置",
    "highlight": "户型亮点", "delivery": "交付标准",
    "fee_note": "其他费用", "terms": "商务条款", "bus": "公交",
    "tenants": "入驻企业", "metro": "地铁", "services": "配套",
}


def write_csv(records):
    cols = list(records[0].keys())
    for r in records:
        for k in r.keys():
            if k not in cols:
                cols.append(k)
    lines = [",".join(cols)]
    for r in records:
        cells = []
        for c in cols:
            v = r.get(c, "")
            if isinstance(v, (list,)):
                v = "|".join(v)
            v = "" if v is None else str(v)
            if any(ch in v for ch in [',', '"', '\n']):
                v = '"' + v.replace('"', '""') + '"'
            cells.append(v)
        lines.append(",".join(cells))
    with open(DATA_CSV, "w", encoding="utf-8-sig", newline="") as f:
        f.write("\n".join(lines) + "\n")


def backup_notes():
    """把 Obsidian 笔记原文备份到项目 obsidian-notes/（随部署上传云端留档）"""
    dst = os.path.join(ROOT, "obsidian-notes")
    os.makedirs(dst, exist_ok=True)
    n = 0
    for f in os.listdir(OBSIDIAN_DIR):
        if f.endswith(".md"):
            shutil.copy2(os.path.join(OBSIDIAN_DIR, f), os.path.join(dst, f))
            n += 1
    return n


def main():
    if not os.path.isdir(OBSIDIAN_DIR):
        sys.exit("Obsidian 目录不存在: %s" % OBSIDIAN_DIR)
    notes = sorted(f for f in os.listdir(OBSIDIAN_DIR) if f.endswith(".md"))
    if not notes:
        sys.exit("Obsidian 园区信息目录下没有 .md 笔记")
    records = read_data()
    by_id = {r["id"]: r for r in records}
    for note in notes:
        note_name = note[:-3]
        fields, imgs = parse_note(os.path.join(OBSIDIAN_DIR, note))
        ok, pid = apply_park(records, by_id, note_name, fields, imgs)
        print("  %s → %s (%s)" % (note_name, pid or "新建", "对齐" if pid else "新增"))
    write_data(records)
    write_csv(records)
    bn = backup_notes()
    print("完成：共 %d 条园区 → data.js + data.csv；Obsidian 笔记已备份 %d 份到 obsidian-notes/（云端留档）" % (len(records), bn))
    print("已更新园区：", [r["name"] for r in records if r.get("updateTime") == TODAY] or "本次无")


if __name__ == "__main__":
    main()
