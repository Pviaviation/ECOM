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
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ID của các Google Sheet nguồn.
# Repo này đang để chế độ public, nên ID nào đặt ở đây là ai cũng đọc được.
# Cách kín hơn: khai báo ở GitHub → Settings → Secrets and variables → Actions → Variables,
# rồi XOÁ giá trị mặc định phía dưới (để trống trong ngoặc kép).
TRIPCARE_ID = os.environ.get("TRIPCARE_SHEET_ID", "").strip() or "1HjER2aRwjBWaSUvDXOP6ony4sIcYcZ_8"
WBOOKING_ID = os.environ.get("WBOOKING_SHEET_ID", "").strip() or "1wWcru2htgF_hpTy3_1cRUr-EYfouAm9n5kIBZe2Hh_g"
# File "Nhập liệu báo cáo tháng" cả Phòng cùng điền (xem tools/tao_file_nhap_lieu.py).
# CHỦ Ý không ghi sẵn ID ở đây — khai báo qua biến NHAP_LIEU_SHEET_ID để khỏi lộ trên repo public.
NHAP_LIEU_ID = os.environ.get("NHAP_LIEU_SHEET_ID", "").strip()
NAM = 2026
KPI_TRIPCARE_TY = 60          # KPI năm của TripCARE (tỷ) để tính % hoàn thành
VN_TZ = timezone(timedelta(hours=7))

BAT_DAU = "/* ===== AUTO-DATA:START"
KET_THUC = "===== AUTO-DATA:END ===== */"
KY_BAT_DAU = "/* ===== KY-TU-NHAP:START"
KY_KET_THUC = "===== KY-TU-NHAP:END ===== */"

# nhãn trong file nhập liệu -> khoá dùng trong dashboard
MA_TRANG_THAI = {
    "đang tăng trưởng": "tang-truong",
    "sắp go-live": "sap-golive",
    "cần chú ý": "canh-bao",
    "chờ đối tác": "cho-doi-tac",
}
MA_MUC_DO = {"gấp": "gap", "theo dõi": "theo-doi"}
MA_TT_MOC = {"hoàn thành": "done", "đã đến hạn": "qua", "trượt hạn": "truot"}


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


# ------------------------------------- kỳ báo cáo do cả Phòng tự nhập liệu

def so_thuc(o):
    """'2,05' hoặc '2.05' -> 2.05 · ô trống -> None (KHÔNG quy về 0)."""
    chuoi = str(o or "").strip().replace(" ", "")
    if not chuoi:
        return None
    chuoi = chuoi.replace("%", "")
    if chuoi.count(",") == 1 and chuoi.count(".") == 0:
        chuoi = chuoi.replace(",", ".")
    else:
        chuoi = chuoi.replace(",", "")
    try:
        return float(chuoi)
    except ValueError:
        return None


def cac_dong(o):
    """Ô nhiều dòng -> list; bỏ dòng trống và dấu gạch đầu dòng người dùng tự thêm."""
    y = []
    for d in str(o or "").replace("\r", "\n").split("\n"):
        d = re.sub(r"^\s*[-•*·]\s*", "", d).strip()
        if d:
            y.append(d)
    return y


def doc_file_nhap_lieu():
    """Đọc file nhập liệu chung -> dict kỳ báo cáo, hoặc None nếu chưa cấu hình / chưa có nội dung."""
    if not NHAP_LIEU_ID:
        return None
    try:
        tab_ky = tai_tab(NHAP_LIEU_ID, "KỲ BÁO CÁO")
        tab_du_an = tai_tab(NHAP_LIEU_ID, "DỰ ÁN")
    except Exception as loi:
        print("   ! Không đọc được file nhập liệu (%s) — bỏ qua, giữ nguyên kỳ đang có." % loi)
        return None

    thong_tin = {str(lay_o(h, 0)).strip(): str(lay_o(h, 1)).strip() for h in tab_ky if lay_o(h, 0)}
    ma_ky = thong_tin.get("Mã kỳ", "")
    if not re.fullmatch(r"\d{4}-\d{2}", ma_ky):
        print("   ! Tab 'KỲ BÁO CÁO' chưa điền Mã kỳ hợp lệ — bỏ qua.")
        return None

    du_an = {}
    for hang in tab_du_an[1:]:
        ma = str(lay_o(hang, 0)).strip()
        if not ma or ma.lower().startswith("mã"):
            continue
        trang_thai = MA_TRANG_THAI.get(str(lay_o(hang, 3)).strip().lower())
        muc = {
            "trangThai": trang_thai,
            "dt": so_thuc(lay_o(hang, 4)),
            "luyKe": so_thuc(lay_o(hang, 5)),
            "phanTramKPI": so_thuc(lay_o(hang, 6)),
            "cungKy2025": so_thuc(lay_o(hang, 7)),
            "ghiChu": str(lay_o(hang, 8)).strip(),
            "ketQua": cac_dong(lay_o(hang, 9)),
            "keHoach": cac_dong(lay_o(hang, 10)),
        }
        if any(v not in (None, "", []) for v in muc.values()):
            du_an[ma] = {k: v for k, v in muc.items() if v not in (None, "", [])}

    if not du_an:
        print("   ! File nhập liệu chưa có dự án nào được điền — bỏ qua.")
        return None

    kho_khan = []
    try:
        for hang in tai_tab(NHAP_LIEU_ID, "KHÓ KHĂN")[1:]:
            muc = MA_MUC_DO.get(str(lay_o(hang, 0)).strip().lower())
            ten, kho = str(lay_o(hang, 1)).strip(), str(lay_o(hang, 2)).strip()
            if muc and ten and kho:
                kho_khan.append({"muc": muc, "duAn": ten, "kho": kho,
                                 "hoTro": str(lay_o(hang, 3)).strip()})
    except Exception:
        pass

    moc = []
    try:
        for hang in tai_tab(NHAP_LIEU_ID, "MỐC THỜI GIAN")[1:]:
            ngay, ten, nd = (str(lay_o(hang, i)).strip() for i in (0, 1, 2))
            if not (ngay and nd):
                continue
            m = {"ngay": ngay, "duAn": ten, "moc": nd,
                 "hot": str(lay_o(hang, 3)).strip().lower() in ("x", "có", "yes", "true")}
            st = MA_TT_MOC.get(str(lay_o(hang, 4)).strip().lower())
            if st:
                m["st"] = st
            moc.append(m)
    except Exception:
        pass

    return {
        "id": ma_ky,
        "label": thong_tin.get("Nhãn hiển thị") or "Tháng %s/%s" % (ma_ky[5:], ma_ky[:4]),
        "range": thong_tin.get("Khoảng thời gian", ""),
        "chot": thong_tin.get("Chốt số đến ngày", ""),
        "mucTieuNam": so_thuc(thong_tin.get("Mục tiêu năm (tỷ)")) or 100,
        "luuY": thong_tin.get("Lưu ý chung", ""),
        "data": du_an,
        "khoKhan": kho_khan,
        "mocThoiGian": moc,
    }


def dung_khoi_ky(ky):
    """Sinh object kỳ báo cáo (JS) từ dữ liệu file nhập liệu."""
    if not ky:
        return "%s — chưa có kỳ nào từ file nhập liệu ===== */\n      /* %s" % (KY_BAT_DAU, KY_KET_THUC)
    d = []
    d.append("%s — do Action sinh từ file nhập liệu của Phòng, ĐỪNG SỬA TAY ===== */" % KY_BAT_DAU)
    d.append("      {")
    d.append('        id: %s, type: "month", label: %s, range: %s, chot: %s, mucTieuNam: %s,'
             % (gon(ky["id"]), gon(ky["label"]), gon(ky["range"]), gon(ky["chot"]), gon(ky["mucTieuNam"])))
    if ky["luuY"]:
        d.append("        luuY: %s," % gon(ky["luuY"]))
    d.append("        data: {")
    for ma, m in ky["data"].items():
        phan = []
        for khoa in ("trangThai", "dt", "luyKe", "phanTramKPI", "cungKy2025"):
            if khoa in m:
                phan.append("%s: %s" % (khoa, gon(m[khoa])))
        d.append("          %s: {" % (gon(ma) if "-" in ma else ma))
        if phan:
            d.append("            %s," % ", ".join(phan))
        if "ghiChu" in m:
            d.append("            ghiChu: %s," % gon(m["ghiChu"]))
        for khoa in ("ketQua", "keHoach"):
            if khoa in m:
                d.append("            %s: %s," % (khoa, gon(m[khoa])))
        d[-1] = d[-1].rstrip(",")
        d.append("          },")
    d[-1] = d[-1].rstrip(",")
    d.append("        },")
    d.append("        khoKhan: [")
    for k in ky["khoKhan"]:
        d.append("          { muc: %s, duAn: %s, kho: %s, hoTro: %s },"
                 % (gon(k["muc"]), gon(k["duAn"]), gon(k["kho"]), gon(k["hoTro"])))
    d.append("        ],")
    d.append("        mocThoiGian: [")
    for m in ky["mocThoiGian"]:
        st = ", st: %s" % gon(m["st"]) if "st" in m else ""
        d.append("          { ngay: %s, duAn: %s, moc: %s, hot: %s%s },"
                 % (gon(m["ngay"]), gon(m["duAn"]), gon(m["moc"]), "true" if m["hot"] else "false", st))
        d[-1] = d[-1]
    d.append("        ]")
    d.append("      },")
    d.append("      /* %s" % KY_KET_THUC)
    return "\n".join(d)


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

    print("Đang đọc file nhập liệu của Phòng…" if NHAP_LIEU_ID
          else "Chưa cấu hình NHAP_LIEU_SHEET_ID — bỏ qua phần nhập liệu.")
    ky = doc_file_nhap_lieu()
    if ky:
        print("   kỳ %s · %d dự án · %d khó khăn · %d mốc"
              % (ky["id"], len(ky["data"]), len(ky["khoKhan"]), len(ky["mocThoiGian"])))

    html = duong_dan.read_text(encoding="utf-8")

    def thay(noi_dung, mo, dong, khoi_moi):
        dau, cuoi = noi_dung.find(mo), noi_dung.find(dong)
        if dau < 0 or cuoi < 0:
            raise SystemExit("index.html thiếu mốc %s … %s" % (mo, dong))
        return noi_dung[:dau] + khoi_moi + noi_dung[cuoi + len(dong):]

    moi = thay(html, BAT_DAU, KET_THUC, dung_khoi_js(tripcare, wbooking, datetime.now(VN_TZ)))
    if ky:
        moi = thay(moi, KY_BAT_DAU, KY_KET_THUC, dung_khoi_ky(ky))

    if moi == html:
        print("Số liệu không đổi — không ghi lại file.")
        return
    duong_dan.write_text(moi, encoding="utf-8")
    print("Đã cập nhật %s" % duong_dan)


if __name__ == "__main__":
    main()
