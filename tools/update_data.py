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
    "đang thực hiện": "dang-thuc-hien",
    "sắp go-live": "sap-golive",
    "cần chú ý": "canh-bao",
    "chờ đối tác": "cho-doi-tac",
}
MA_MUC_DO = {"gấp": "gap", "theo dõi": "theo-doi"}
MA_TT_MOC = {"hoàn thành": "done", "đã đến hạn": "qua", "trượt hạn": "truot"}


# ---------------------------------------------------------------- tải & đọc

def tai_tab(sheet_id, ten_tab, dong_tieu_de=0):
    """Tải một tab của Google Sheet dưới dạng CSV (đọc theo TÊN tab, không theo gid).

    dong_tieu_de=1 dùng cho file nhập liệu: nếu để 0, Google suy ra kiểu dữ liệu cho
    từng cột và sẽ NUỐT MẤT ô tiêu đề dạng chữ của cột toàn số (vd cột "Ưu tiên"),
    khiến script không nhận ra cột đó.
    """
    url = ("https://docs.google.com/spreadsheets/d/%s/gviz/tq"
           "?tqx=out:csv&headers=%d&sheet=%s" % (sheet_id, dong_tieu_de, urllib.parse.quote(ten_tab)))
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

    # CHỐT AN TOÀN: doanh thu TripCARE một tháng luôn nằm trong khoảng vài tỷ.
    # Ra ngoài khoảng này gần như chắc chắn là sheet đang được sửa dở -> không ghi gì.
    for i in co_so:
        ty = nam_nay[i]["phi"] / 1e9
        if not (0.3 <= ty <= 15):
            raise SystemExit("DỪNG: TripCARE tháng %d đọc được %.3f tỷ — ngoài khoảng hợp lý "
                             "(0,3–15 tỷ), nhiều khả năng sheet đang sửa dở." % (i + 1, ty))

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
        # số tiền bồi thường nhỏ nên giữ 5 chữ số thập phân, làm tròn 3 sẽ mất số lẻ (44,75 tr -> 45 tr)
        "boiThuong": round((so_nguyen(lay_o(hang_nam, 8)) or 0) / 1e9, 5),
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
        dt = so_nguyen(lay_o(hang, 10)) or 0
        bt = so_nguyen(lay_o(hang, 11)) or 0
        if not dt and not bt:
            continue                       # tháng chưa có gì -> bỏ qua
        # Tháng đã có bồi thường nhưng chưa ghi nhận doanh thu -> tỷ lệ để trống, không chia cho 0
        ty_le = round(bt / dt * 100, 2) if dt else None
        # CHỐT AN TOÀN: sheet đang được gõ dở có thể trả về số rác (đã từng đọc phải
        # 257.728đ cho tháng 7 giữa lúc nhân viên sửa ô) -> thà không cập nhật còn hơn
        # đẩy số sai lên dashboard của lãnh đạo.
        if dt and bt and ty_le > 1000:
            raise SystemExit("DỪNG: wBooking tháng %d có tỷ lệ bồi thường %.0f%% "
                             "(DT %d đ / BT %d đ) — số bất thường, nhiều khả năng sheet "
                             "đang sửa dở. Không ghi gì cả, lần chạy sau sẽ lấy lại."
                             % (thang, ty_le, dt, bt))
        if dt and dt < 1_000_000:
            raise SystemExit("DỪNG: wBooking tháng %d chỉ có %d đ doanh thu — số bất thường, "
                             "nhiều khả năng sheet đang sửa dở." % (thang, dt))
        hang_thang.append([thang, dt, bt, so_vu.get(thang, 0), ty_le])
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


def dinh_vi_cot(hang_tieu_de, tu_khoa):
    """Tìm vị trí cột theo TIÊU ĐỀ thay vì theo thứ tự cố định.

    Nhờ vậy Phòng thêm cột mới hoặc đổi chỗ các cột thì script vẫn đọc đúng.
    tu_khoa: {tên trường: [các từ khoá xuất hiện trong tiêu đề]}
    """
    vi_tri = {}
    for i, o in enumerate(hang_tieu_de):
        nhan = re.sub(r"\s+", " ", str(o or "")).strip().lower()
        if not nhan:
            continue
        for truong, khoa in tu_khoa.items():
            if truong in vi_tri:
                continue
            if any(k in nhan for k in khoa):
                vi_tri[truong] = i
                break
    return vi_tri


def o_theo_ten(hang, vi_tri, truong):
    i = vi_tri.get(truong)
    return lay_o(hang, i) if i is not None else ""


def doc_file_nhap_lieu(duong_dan_html=None):
    """Đọc file nhập liệu chung -> DANH SÁCH kỳ báo cáo.

    Mỗi dòng trong các tab đều có cột "Kỳ", nên một file dùng được cho nhiều
    tháng cùng lúc: người này sửa dòng kỳ 2026-08, người kia thêm dòng kỳ 2026-07.
    Các cột được nhận diện theo TIÊU ĐỀ nên thêm cột mới không làm hỏng script.
    Trả về "BO_QUA" nếu không đọc được (giữ nguyên dữ liệu lần trước).
    """
    if not NHAP_LIEU_ID:
        return "BO_QUA"
    try:
        tab_ky = tai_tab(NHAP_LIEU_ID, "KỲ BÁO CÁO", dong_tieu_de=1)
        tab_du_an = tai_tab(NHAP_LIEU_ID, "DỰ ÁN", dong_tieu_de=1)
    except Exception as loi:
        print("   ! Không đọc được file nhập liệu (%s) — giữ nguyên dữ liệu lần trước." % loi)
        return "BO_QUA"

    def ma_ky_hop_le(o):
        o = str(o or "").strip()
        return o if re.fullmatch(r"\d{4}-\d{2}", o) else None

    # --- tab KỲ BÁO CÁO: mỗi kỳ một dòng ---
    thong_tin = {}
    for hang in tab_ky[1:]:
        mk = ma_ky_hop_le(lay_o(hang, 0))
        if mk:
            thong_tin[mk] = {
                "label": str(lay_o(hang, 1)).strip() or "Tháng %s/%s" % (mk[5:], mk[:4]),
                "range": str(lay_o(hang, 2)).strip(),
                "chot": str(lay_o(hang, 3)).strip(),
                "mucTieuNam": so_thuc(lay_o(hang, 4)) or 100,
                "luuY": str(lay_o(hang, 5)).strip(),
            }
    if not thong_tin:
        print("   ! Tab 'KỲ BÁO CÁO' chưa có dòng nào hợp lệ (cột Mã kỳ dạng 2026-08) — bỏ qua.")
        return None

    ky_theo_ma = {}   # mã kỳ -> dict dữ liệu
    thong_tin_du_an = {}   # mã dự án -> {ten, doiTac, phuTrach} để tạo thẻ cho dự án mới

    def lay_ky(mk):
        if mk not in ky_theo_ma:
            tt = thong_tin.get(mk) or {"label": "Tháng %s/%s" % (mk[5:], mk[:4]),
                                       "range": "", "chot": "", "mucTieuNam": 100, "luuY": ""}
            ky_theo_ma[mk] = dict(tt, id=mk, data={}, khoKhan=[], mocThoiGian=[])
        return ky_theo_ma[mk]

    # --- tab DỰ ÁN: nhận diện cột theo tiêu đề ---
    cot = dinh_vi_cot(tab_du_an[0] if tab_du_an else [], {
        "ky": ["kỳ"], "ma": ["mã dự án", "mã"], "ten": ["tên dự án", "tên"],
        "phuTrach": ["phụ trách"], "hoTro": ["hỗ trợ"], "uuTien": ["ưu tiên"],
        "trangThai": ["trạng thái"], "dt": ["dt tháng", "doanh thu tháng"],
        "luyKe": ["lũy kế"], "phanTramKPI": ["% kpi", "kpi năm"],
        "cungKy2025": ["cùng kỳ"], "ghiChu": ["ghi chú"],
        "ketQua": ["kết quả"], "keHoach": ["kế hoạch"],
    })
    for hang in tab_du_an[1:]:
        mk = ma_ky_hop_le(o_theo_ten(hang, cot, "ky"))
        ma = str(o_theo_ten(hang, cot, "ma")).strip()
        if not mk or not ma or ma.lower().startswith("mã"):
            continue
        muc = {
            "trangThai": MA_TRANG_THAI.get(str(o_theo_ten(hang, cot, "trangThai")).strip().lower()),
            "dt": so_thuc(o_theo_ten(hang, cot, "dt")),
            "luyKe": so_thuc(o_theo_ten(hang, cot, "luyKe")),
            "phanTramKPI": so_thuc(o_theo_ten(hang, cot, "phanTramKPI")),
            "cungKy2025": so_thuc(o_theo_ten(hang, cot, "cungKy2025")),
            "ghiChu": cac_dong(o_theo_ten(hang, cot, "ghiChu")),
            "ketQua": cac_dong(o_theo_ten(hang, cot, "ketQua")),
            "keHoach": cac_dong(o_theo_ten(hang, cot, "keHoach")),
        }
        muc = {k: v for k, v in muc.items() if v not in (None, "", [])}
        if muc:
            lay_ky(mk)["data"][ma] = muc
        # cột "Tên dự án" Phòng đang dùng để ghi chương trình/nhóm -> hiện ở dòng phụ
        # dưới tên thẻ; dự án chưa có trong dashboard sẽ được tạo thẻ mới.
        ten_ct = str(o_theo_ten(hang, cot, "ten")).strip()
        nguoi = str(o_theo_ten(hang, cot, "phuTrach")).strip()
        ho_tro = str(o_theo_ten(hang, cot, "hoTro")).strip()
        uu_tien = so_thuc(o_theo_ten(hang, cot, "uuTien"))
        if ten_ct or nguoi or ho_tro or uu_tien:
            tt = {"ten": ma, "doiTac": ten_ct, "phuTrach": nguoi, "hoTro": ho_tro}
            if uu_tien:
                tt["uuTien"] = max(1, min(5, int(uu_tien)))
            thong_tin_du_an[ma] = tt

    # --- tab KHÓ KHĂN ---
    try:
        bang_kk = tai_tab(NHAP_LIEU_ID, "KHÓ KHĂN", dong_tieu_de=1)
        ckk = dinh_vi_cot(bang_kk[0] if bang_kk else [], {
            "ky": ["kỳ"], "muc": ["mức"], "duAn": ["dự án"],
            "kho": ["khó khăn", "vướng"], "hoTro": ["hỗ trợ", "đề xuất"]})
        for hang in bang_kk[1:]:
            mk = ma_ky_hop_le(o_theo_ten(hang, ckk, "ky"))
            muc = MA_MUC_DO.get(str(o_theo_ten(hang, ckk, "muc")).strip().lower())
            ten = str(o_theo_ten(hang, ckk, "duAn")).strip()
            kho = str(o_theo_ten(hang, ckk, "kho")).strip()
            if mk and muc and ten and kho:
                lay_ky(mk)["khoKhan"].append({"muc": muc, "duAn": ten, "kho": kho,
                                              "hoTro": str(o_theo_ten(hang, ckk, "hoTro")).strip()})
    except Exception:
        pass

    # --- tab MỐC THỜI GIAN ---
    try:
        bang_m = tai_tab(NHAP_LIEU_ID, "MỐC THỜI GIAN", dong_tieu_de=1)
        cm = dinh_vi_cot(bang_m[0] if bang_m else [], {
            "ky": ["kỳ"], "ngay": ["ngày", "thời điểm"], "duAn": ["dự án"],
            "moc": ["nội dung"], "hot": ["quan trọng"], "st": ["trạng thái"]})
        for hang in bang_m[1:]:
            mk = ma_ky_hop_le(o_theo_ten(hang, cm, "ky"))
            ngay = str(o_theo_ten(hang, cm, "ngay")).strip()
            ten = str(o_theo_ten(hang, cm, "duAn")).strip()
            nd = str(o_theo_ten(hang, cm, "moc")).strip()
            if not (mk and ngay and nd):
                continue
            m = {"ngay": ngay, "duAn": ten, "moc": nd,
                 "hot": str(o_theo_ten(hang, cm, "hot")).strip().lower() in ("x", "có", "yes", "true")}
            st = MA_TT_MOC.get(str(o_theo_ten(hang, cm, "st")).strip().lower())
            if st:
                m["st"] = st
            lay_ky(mk)["mocThoiGian"].append(m)
    except Exception:
        pass

    if not ky_theo_ma:
        print("   ! File nhập liệu chưa có dòng nào được điền — bỏ qua.")
        return None

    # CHỐT AN TOÀN: kỳ HOÀN TOÀN MỚI chỉ được tạo khi đã có nội dung thật, tránh
    # dashboard mọc thêm một kỳ rỗng đứng đầu khi ai đó mới chọn vài ô trạng thái.
    html_hien_tai = ""
    if duong_dan_html:
        html_hien_tai = duong_dan_html.read_text(encoding="utf-8")
        d, c = html_hien_tai.find(KY_BAT_DAU), html_hien_tai.find(KY_KET_THUC)
        if d >= 0 and c >= 0:                      # bỏ khối lần trước ra kẻo tự thấy chính mình
            html_hien_tai = html_hien_tai[:d] + html_hien_tai[c:]

    ket_qua = []
    for mk in sorted(ky_theo_ma, reverse=True):
        ky = ky_theo_ma[mk]
        co_noi_dung = any(any(k in m for k in ("luyKe", "dt", "ghiChu", "ketQua", "keHoach"))
                          for m in ky["data"].values()) or ky["khoKhan"] or ky["mocThoiGian"]
        da_ton_tai = ('id: "%s"' % mk) in html_hien_tai if html_hien_tai else True
        if not da_ton_tai and not co_noi_dung:
            print("   ! Bỏ qua kỳ %s: chưa có trong dashboard và mới chỉ có trạng thái." % mk)
            continue
        ket_qua.append(ky)
    if not ket_qua:
        return None
    ket_qua[0]["_duAn"] = thong_tin_du_an     # gắn vào kỳ đầu tiên, dashboard đọc chung
    return ket_qua



def dung_khoi_ky(ds_ky):
    """Sinh hằng NHAP_LIEU (JS) — một MẢNG các kỳ báo cáo lấy từ file nhập liệu.

    Trang web sẽ tự gộp từng kỳ vào kỳ trùng mã (ô để trống thì giữ nguyên nội dung
    đã soạn tay), hoặc tạo kỳ mới nếu mã kỳ chưa có.
    """
    if not ds_ky:
        return ("%s — chưa có dữ liệu từ file nhập liệu ===== */\n"
                "    const NHAP_LIEU = [];\n"
                "    /* %s" % (KY_BAT_DAU, KY_KET_THUC))
    d = ["%s — do Action sinh từ file nhập liệu của Phòng, ĐỪNG SỬA TAY ===== */" % KY_BAT_DAU,
         "    const NHAP_LIEU = ["]
    for ky in ds_ky:
        d.append("      {")
        d.append("        id: %s, label: %s, range: %s, chot: %s, mucTieuNam: %s,"
                 % (gon(ky["id"]), gon(ky["label"]), gon(ky["range"]), gon(ky["chot"]), gon(ky["mucTieuNam"])))
        if ky["luuY"]:
            d.append("        luuY: %s," % gon(ky["luuY"]))
        d.append("        data: {")
        for ma, m in ky["data"].items():
            phan = []
            for khoa in ("trangThai", "dt", "luyKe", "phanTramKPI", "cungKy2025",
                         "ghiChu", "ketQua", "keHoach"):
                if khoa in m:
                    phan.append("%s: %s" % (khoa, gon(m[khoa])))
            d.append("          %s: { %s }," % (gon(ma), ", ".join(phan)))
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
        d.append("        ]")
        if ky.get("_duAn"):
            d.append("        ,duAn: {")
            for ma, tt in ky["_duAn"].items():
                phan = ["ten: %s" % gon(tt["ten"]), "doiTac: %s" % gon(tt["doiTac"]),
                        "phuTrach: %s" % gon(tt["phuTrach"])]
                if tt.get("hoTro"):
                    phan.append("hoTro: %s" % gon(tt["hoTro"]))
                if tt.get("uuTien"):
                    phan.append("uuTien: %d" % tt["uuTien"])
                d.append("          %s: { %s }," % (gon(ma), ", ".join(phan)))
            d.append("        }")
        d.append("      },")
    d.append("    ];")
    d.append("    /* %s" % KY_KET_THUC)
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

    if NHAP_LIEU_ID:
        print("Đang đọc file nhập liệu của Phòng…")
    else:
        print("!" * 78)
        print("CHƯA KHAI BÁO biến NHAP_LIEU_SHEET_ID → nội dung Phòng nhập trên Google")
        print("Sheet sẽ KHÔNG lên dashboard. Khai báo tại: repo → Settings →")
        print("Secrets and variables → Actions → tab Variables → New repository variable.")
        print("!" * 78)
    ky = doc_file_nhap_lieu(duong_dan)
    if ky and ky != "BO_QUA":
        for k in ky:
            print("   kỳ %s · %d dự án · %d khó khăn · %d mốc"
                  % (k["id"], len(k["data"]), len(k["khoKhan"]), len(k["mocThoiGian"])))

    html = duong_dan.read_text(encoding="utf-8")

    def thay(noi_dung, mo, dong, khoi_moi):
        dau, cuoi = noi_dung.find(mo), noi_dung.find(dong)
        if dau < 0 or cuoi < 0:
            raise SystemExit("index.html thiếu mốc %s … %s" % (mo, dong))
        return noi_dung[:dau] + khoi_moi + noi_dung[cuoi + len(dong):]

    moi = thay(html, BAT_DAU, KET_THUC, dung_khoi_js(tripcare, wbooking, datetime.now(VN_TZ)))
    if ky != "BO_QUA":
        # ky = None -> ghi khoi rong, xoa du lieu cu (vd Phong da xoa het noi dung sheet)
        moi = thay(moi, KY_BAT_DAU, KY_KET_THUC, dung_khoi_ky(ky))

    if moi == html:
        print("Số liệu không đổi — không ghi lại file.")
        return
    # LUÔN ghi bằng LF (newline="\n"). Nếu để mặc định, Python trên Windows sẽ ghi CRLF
    # trong khi GitHub Action (Linux) ghi LF -> Git tưởng cả file bị sửa và gây đụng độ.
    with open(duong_dan, "w", encoding="utf-8", newline="\n") as f:
        f.write(moi)
    print("Đã cập nhật %s" % duong_dan)


if __name__ == "__main__":
    main()
