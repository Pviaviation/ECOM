#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lấy số liệu doanh thu từ 2 Google Sheet của Phòng TMĐT và ghi thẳng vào index.html.

    python tools/update_data.py [đường dẫn index.html]

Script chỉ ghi đè phần nằm giữa 2 mốc AUTO-DATA:START / AUTO-DATA:END trong index.html,
KHÔNG đụng tới nội dung kết quả / kế hoạch / khó khăn (những phần này nhập tay).

Nguồn:
  * TripCARE  — tab "TỔNG HỢP TRIPCARE" (doanh thu & số đơn theo tháng, bồi thường)
                + tab "T<tháng>.2026" / "T<tháng>.2025" để biết tháng đang chạy có số đến ngày nào
                  và lấy đúng từng ấy ngày của năm trước để so sánh cho công bằng.
  * wBooking  — tab "TỔNG HỢP BH HIO" (doanh thu & bồi thường theo tháng)
                + tab "DANH SÁCH BỒI THƯỜNG 2026" (đếm số vụ mỗi tháng).

Chỉ dùng thư viện chuẩn của Python — không cần cài gì thêm.
"""

import csv
import io
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

TRIPCARE_ID = "1HjER2aRwjBWaSUvDXOP6ony4sIcYcZ_8"
WBOOKING_ID = "1wWcru2htgF_hpTy3_1cRUr-EYfouAm9n5kIBZe2Hh_g"
NAM = 2026
KPI_TRIPCARE_TY = 60          # KPI năm của TripCARE (tỷ) để tính % hoàn thành
VN_TZ = timezone(timedelta(hours=7))

BAT_DAU = "/* ===== AUTO-DATA:START"
KET_THUC = "===== AUTO-DATA:END ===== */"


# ---------------------------------------------------------------- tải & đọc

def tai_tab(sheet_id, ten_tab):
    """Tải một tab của Google Sheet dưới dạng CSV (đọc theo TÊN tab, không theo gid)."""
    url = ("https://docs.google.com/spreadsheets/d/%s/gviz/tq"
           "?tqx=out:csv&headers=0&sheet=%s" % (sheet_id, urllib.parse.quote(ten_tab)))
    req = urllib.request.Request(url, headers={"User-Agent": "pvi-tmdt-dashboard/1.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        noi_dung = r.read().decode("utf-8")
    return list(csv.reader(io.StringIO(noi_dung)))


def so_nguyen(o):
    """'  4.918.181.000 ' hoặc '  1,800,878,099 ' -> 4918181000.
    Ô trống, '-' hoặc ô không phải số thuần (vd '1-11', '1-thg 8') -> None."""
    chuoi = str(o or "").strip()
    if not chuoi or chuoi == "-":
        return None
    if not re.fullmatch(r"-?[\d.,\s]+", chuoi):
        return None
    chu_so = re.sub(r"\D", "", chuoi)
    if not chu_so:
        return None
    return -int(chu_so) if chuoi.startswith("-") else int(chu_so)


def o_trong(o):
    return o is None or str(o).strip() in ("", "-")


def lay_o(hang, i):
    return hang[i] if i < len(hang) else ""


def tim_hang(bang, mau, cot=0):
    for i, hang in enumerate(bang):
        if mau in lay_o(hang, cot):
            return i
    raise SystemExit("Không tìm thấy dòng chứa %r trong sheet" % mau)


# ------------------------------------------------------------------ TripCARE

def so_thang_cua_nhan(nhan):
    """'Tháng 8 (đến 5/8)' -> 8 · 'Năm 2026'/'TỔNG LŨY KẾ' -> None.
    Cần thiết vì bản CSV của Google bỏ bớt các dòng trống, không thể đếm theo vị trí."""
    m = re.match(r"\s*Tháng\s*(\d{1,2})", str(nhan or ""))
    return int(m.group(1)) if m and 1 <= int(m.group(1)) <= 12 else None


def doc_khoi_nam_tripcare(bang, nam):
    """Trả về list 12 phần tử [số đơn, phí, TB/ngày, số vụ BT, tiền BT] (None nếu tháng chưa có số)."""
    i = tim_hang(bang, "Năm %d" % nam)
    ket_qua = [{"don": None, "phi": None, "tb": None, "soVu": None, "tienBT": None} for _ in range(12)]
    for hang in bang[i + 1:]:
        nhan = lay_o(hang, 0)
        thang = so_thang_cua_nhan(nhan)
        if thang is None:
            if re.match(r"\s*(Năm|TỔNG)", str(nhan or "")):
                break                      # sang khối năm khác -> dừng
            continue
        ket_qua[thang - 1] = {
            "don": so_nguyen(lay_o(hang, 1)),
            "phi": so_nguyen(lay_o(hang, 2)),
            "tb": so_nguyen(lay_o(hang, 3)),
            "soVu": so_nguyen(lay_o(hang, 7)),
            "tienBT": so_nguyen(lay_o(hang, 8)),
        }
    return ket_qua


def doc_tab_ngay(sheet_id, thang, nam):
    """Đọc tab ngày (vd 'T8.2026'), trả về {ngày: (số đơn, phí)} cho các ngày ĐÃ CÓ số."""
    for ten in ("T%d.%d" % (thang, nam), "T%02d.%d" % (thang, nam)):
        try:
            bang = tai_tab(sheet_id, ten)
            break
        except Exception:
            bang = None
    if not bang:
        return {}
    theo_ngay = {}
    for hang in bang:
        stt = so_nguyen(lay_o(hang, 1))
        nhan_ngay = str(lay_o(hang, 2))
        if not stt or not re.match(r"\s*\d{1,2}\s*-", nhan_ngay):
            continue                      # bỏ dòng tiêu đề và dòng tổng cộng
        phi = so_nguyen(lay_o(hang, 4))
        if phi:
            theo_ngay[stt] = (so_nguyen(lay_o(hang, 3)) or 0, phi)
    return theo_ngay


def gom_tripcare():
    bang = tai_tab(TRIPCARE_ID, "TỔNG HỢP TRIPCARE")
    nam_nay = doc_khoi_nam_tripcare(bang, NAM)
    nam_truoc = doc_khoi_nam_tripcare(bang, NAM - 1)

    co_so = [i for i, m in enumerate(nam_nay) if m["phi"]]
    if not co_so:
        raise SystemExit("Sheet TripCARE chưa có số liệu %d" % NAM)
    thang_cuoi = co_so[-1] + 1

    # tháng cuối đã trọn tháng chưa? -> đếm số ngày có số trên tab ngày
    ngay_nam_nay = doc_tab_ngay(TRIPCARE_ID, thang_cuoi, NAM)
    so_ngay_da_co = max(ngay_nam_nay) if ngay_nam_nay else 0
    so_ngay_trong_thang = (datetime(NAM, thang_cuoi % 12 + 1, 1) - timedelta(days=1)).day \
        if thang_cuoi < 12 else 31
    dang_chay = 0 < so_ngay_da_co < so_ngay_trong_thang

    # cùng kỳ năm trước theo ĐÚNG số ngày đã có (chỉ khi tháng cuối chưa trọn)
    cung_ky_phi = cung_ky_don = None
    if dang_chay:
        ngay_nam_truoc = doc_tab_ngay(TRIPCARE_ID, thang_cuoi, NAM - 1)
        phi = sum(v[1] for n, v in ngay_nam_truoc.items() if n <= so_ngay_da_co)
        don = sum(v[0] for n, v in ngay_nam_truoc.items() if n <= so_ngay_da_co)
        if phi:
            cung_ky_phi, cung_ky_don = phi, don

    ty = lambda x: round(x / 1e9, 3)
    tb_thang = []
    for i, m in enumerate(nam_nay[:thang_cuoi]):
        if dang_chay and i == thang_cuoi - 1 and so_ngay_da_co:
            tb_thang.append(round(m["phi"] / so_ngay_da_co / 1e6, 2))   # tự tính theo số ngày thật
        else:
            tb_thang.append(round((m["tb"] or 0) / 1e6, 2))

    hang_nam = bang[tim_hang(bang, "Năm %d" % NAM)]
    ca_nam_truoc = bang[tim_hang(bang, "Năm %d" % (NAM - 1))]

    return {
        "thang2026": [ty(m["phi"]) for m in nam_nay[:thang_cuoi]],
        "don2026": [m["don"] or 0 for m in nam_nay[:thang_cuoi]],
        "tb2026": tb_thang,
        "thang2025": [ty(m["phi"]) if m["phi"] else 0 for m in nam_truoc],
        "don2025": [m["don"] or 0 for m in nam_truoc],
        "thangDangChay": thang_cuoi if dang_chay else 0,
        "soNgayDaCo": so_ngay_da_co if dang_chay else 0,
        "denNgay": "%02d/%02d/%d" % (so_ngay_da_co, thang_cuoi, NAM) if dang_chay else "",
        "cungKyPhi2025": ty(cung_ky_phi) if cung_ky_phi else 0,
        "cungKyDon2025": cung_ky_don or 0,
        "soVuBT": so_nguyen(lay_o(hang_nam, 7)) or 0,
        "boiThuong": ty(so_nguyen(lay_o(hang_nam, 8)) or 0),
        "caNam2025": ty(so_nguyen(lay_o(ca_nam_truoc, 2)) or 0),
        "kpiNam": KPI_TRIPCARE_TY,
    }


# ------------------------------------------------------------------ wBooking

def dem_vu_boi_thuong_wbooking():
    """Đếm số vụ bồi thường mỗi tháng từ tab danh sách (ngày nằm trong chuỗi '... ngày 20/01/2026')."""
    try:
        bang = tai_tab(WBOOKING_ID, "DANH SÁCH BỒI THƯỜNG %d" % NAM)
    except Exception:
        return {}
    dem = {}
    for hang in bang:
        for o in hang:
            m = re.search(r"ngày\s*(\d{1,2})/(\d{1,2})/(\d{4})", str(o))
            if m and int(m.group(3)) == NAM:
                thang = int(m.group(2))
                dem[thang] = dem.get(thang, 0) + 1
                break
    return dem


def gom_wbooking():
    bang = tai_tab(WBOOKING_ID, "TỔNG HỢP BH HIO")
    i = tim_hang(bang, "Năm %d" % NAM, cot=1)
    so_vu = dem_vu_boi_thuong_wbooking()
    hang_thang = []
    for hang in bang[i + 1:]:
        nhan = lay_o(hang, 1)
        thang = so_thang_cua_nhan(nhan)
        if thang is None:
            if re.match(r"\s*(Năm|TỔNG)", str(nhan or "")):
                break
            continue
        dt = so_nguyen(lay_o(hang, 10))
        if not dt:
            continue                       # tháng chưa có số -> bỏ qua
        bt = so_nguyen(lay_o(hang, 11)) or 0
        hang_thang.append([thang, dt, bt, so_vu.get(thang, 0), round(bt / dt * 100, 2)])
    hang_thang.sort(key=lambda x: x[0])
    return {"thang2026": hang_thang}


# ------------------------------------------------------- ghi vào index.html

def gon(gia_tri):
    """JSON một dòng — để mỗi mảng nằm gọn 1 dòng, diff trên GitHub dễ đọc."""
    return json.dumps(gia_tri, ensure_ascii=False)


def dung_khoi_js(tripcare, wbooking, moc_thoi_gian):
    t, dong = tripcare, []
    dong.append("%s — do GitHub Action ghi tự động từ Google Sheet, ĐỪNG SỬA TAY ===== */" % BAT_DAU)
    dong.append("    const AUTO_DATA = {")
    dong.append('      capNhat: %s,' % gon(moc_thoi_gian.strftime("%d/%m/%Y %H:%M")))
    dong.append('      capNhatNgay: %s,' % gon(moc_thoi_gian.strftime("%d/%m/%Y")))
    dong.append("      tripcare: {")
    dong.append("        thang2026: %s," % gon(t["thang2026"]))
    dong.append("        don2026: %s," % gon(t["don2026"]))
    dong.append("        tb2026: %s," % gon(t["tb2026"]))
    dong.append("        thang2025: %s," % gon(t["thang2025"]))
    dong.append("        don2025: %s," % gon(t["don2025"]))
    dong.append("        thangDangChay: %d, soNgayDaCo: %d, denNgay: %s,"
                % (t["thangDangChay"], t["soNgayDaCo"], gon(t["denNgay"])))
    dong.append("        cungKyPhi2025: %s, cungKyDon2025: %d,   // cùng kỳ 2025 tính đúng số ngày đã có"
                % (gon(t["cungKyPhi2025"]), t["cungKyDon2025"]))
    dong.append("        soVuBT: %d, boiThuong: %s, caNam2025: %s, kpiNam: %s"
                % (t["soVuBT"], gon(t["boiThuong"]), gon(t["caNam2025"]), gon(t["kpiNam"])))
    dong.append("      },")
    dong.append("      wbooking: {")
    dong.append("        /* [tháng, doanh thu (đ), bồi thường (đ), số vụ, tỷ lệ BT (%)] */")
    dong.append("        thang2026: [")
    for hang in wbooking["thang2026"]:
        dong.append("          %s," % gon(hang))
    dong.append("        ]")
    dong.append("      }")
    dong.append("    };")
    dong.append("    /* %s" % KET_THUC)
    return "\n".join(dong)


def main():
    duong_dan = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "index.html"
    if not duong_dan.exists():
        raise SystemExit("Không thấy file %s" % duong_dan)

    print("Đang tải số liệu TripCARE…")
    tripcare = gom_tripcare()
    print("   %d tháng có số · tháng đang chạy: %s" %
          (len(tripcare["thang2026"]), tripcare["denNgay"] or "không (đã trọn tháng)"))
    print("Đang tải số liệu wBooking…")
    wbooking = gom_wbooking()
    print("   %d tháng có số" % len(wbooking["thang2026"]))

    html = duong_dan.read_text(encoding="utf-8")
    dau = html.find(BAT_DAU)
    cuoi = html.find(KET_THUC)
    if dau < 0 or cuoi < 0:
        raise SystemExit("index.html thiếu mốc AUTO-DATA:START / AUTO-DATA:END")
    cuoi += len(KET_THUC)

    moi = html[:dau] + dung_khoi_js(tripcare, wbooking, datetime.now(VN_TZ)) + html[cuoi:]
    if moi == html:
        print("Số liệu không đổi — không ghi lại file.")
        return
    duong_dan.write_text(moi, encoding="utf-8")
    print("Đã cập nhật %s" % duong_dan)


if __name__ == "__main__":
    main()
