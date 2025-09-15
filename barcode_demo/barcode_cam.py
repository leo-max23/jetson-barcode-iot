#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import os, sys, csv, time, json, argparse, subprocess, signal
from datetime import datetime
from pathlib import Path
import cv2
import numpy as np
from pyzbar.pyzbar import decode, ZBarSymbol

def run_cmd(cmd):
    try:
        subprocess.run(cmd, shell=True, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def try_set_camera(device, width, height, use_mjpg=False, controls=None):
    
    if use_mjpg:
        run_cmd(f"v4l2-ctl -d {device} --set-fmt-video=width={width},height={height},pixelformat=MJPG")
    else:
        run_cmd(f"v4l2-ctl -d {device} --set-fmt-video=width={width},height={height},pixelformat=YUYV")
    if controls:
        ctrl = " ".join([f"-c {c}" for c in controls])
        run_cmd(f"v4l2-ctl -d {device} {ctrl}")

def load_goods(csv_path):
    goods = {}
    if not os.path.exists(csv_path):
        print(f"[WARN] {csv_path} 不存在，识别只输出条码号", file=sys.stderr)
        return goods
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            code = (r.get("barcode") or "").strip()
            if not code: continue
            goods[code] = {
                "sku":   (r.get("sku") or "").strip(),
                "name":  (r.get("name") or "").strip(),
                "price": (r.get("price") or "").strip(),
            }
    print(f"[INFO] 商品库载入: {len(goods)} 条", file=sys.stderr)
    return goods

def ensure_dir(p: Path): p.mkdir(parents=True, exist_ok=True)

def clip_bbox(x, y, w, h, W, H):
    x = max(0, x); y = max(0, y)
    w = max(1, min(w, W - x)); h = max(1, min(h, H - y))
    return x, y, w, h


def enhance(gray):
    
    gray = cv2.equalizeHist(gray)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    gray = clahe.apply(gray)
    
    blur = cv2.GaussianBlur(gray, (0,0), 1.0)
    sharp = cv2.addWeighted(gray, 1.5, blur, -0.5, 0)
    
    th = cv2.adaptiveThreshold(sharp,255,cv2.ADAPTIVE_THRESH_MEAN_C,cv2.THRESH_BINARY,35,5)
    th = cv2.medianBlur(th, 3)
    
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3,1))
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, kernel, iterations=1)
    return th

SYMS = [ZBarSymbol.EAN13, ZBarSymbol.EAN8, ZBarSymbol.UPCA, ZBarSymbol.UPCE, ZBarSymbol.CODE128, ZBarSymbol.QRCODE]

def try_decode_multi(gray):
    
    imgs = [
        gray,
        cv2.rotate(gray, cv2.ROTATE_90_CLOCKWISE),
        cv2.rotate(gray, cv2.ROTATE_180),
        cv2.rotate(gray, cv2.ROTATE_90_COUNTERCLOCKWISE),
    ]
    for g in imgs:
        r = decode(g, symbols=SYMS)
        if not r:
            inv = 255 - g
            r = decode(inv, symbols=SYMS)
        if r: return r
    return []

def main():
    ap = argparse.ArgumentParser(description="Jetson Nano 条码识别(增强版)")
    ap.add_argument("--device", default="/dev/video0")
    ap.add_argument("--width", type=int, default=640)   
    ap.add_argument("--height", type=int, default=480)  
    ap.add_argument("--mjpg", action="store_true", help="使用MJPG(默认YUYV)")
    ap.add_argument("--set-controls", default="", help="例如 focus_auto=0,exposure_auto=1,exposure_absolute=200")
    ap.add_argument("--csv", default="goods_db.csv")
    ap.add_argument("--dedup-ms", type=int, default=1500)
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--save-crops", default="")
    ap.add_argument("--log-jsonl", default="")
    ap.add_argument("--log-csv",   default="")
    args = ap.parse_args()

    controls = [c.strip() for c in args.set_controls.split(",") if c.strip()]
    try_set_camera(args.device, args.width, args.height, use_mjpg=args.mjpg, controls=controls)

    cam_index = 0
    if args.device.startswith("/dev/video"):
        try: cam_index = int(args.device.replace("/dev/video",""))
        except: pass

    cap = cv2.VideoCapture(cam_index)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    if not cap.isOpened():
        print("[ERR] Failed to open camera", file=sys.stderr); sys.exit(1)

    goods = load_goods(args.csv)
    last_seen = {}

    jsonl_fp = None; csv_fp=None; csv_writer=None
    if args.log_jsonl:
        ensure_dir(Path(args.log_jsonl).parent)
        jsonl_fp = open(args.log_jsonl, "a", encoding="utf-8")
    if args.log_csv:
        ensure_dir(Path(args.log_csv).parent)
        newf = not os.path.exists(args.log_csv)
        csv_fp = open(args.log_csv, "a", newline="", encoding="utf-8")
        csv_writer = csv.writer(csv_fp)
        if newf:
            csv_writer.writerow(["ts","code","symbology","x","y","w","h","found","sku","name","price"])

    crops_dir = None
    if args.save_crops:
        crops_dir = Path(args.save_crops); ensure_dir(crops_dir)

    stop = {"v": False}
    signal.signal(signal.SIGINT, lambda a,b: stop.update(v=True))

    print("[INFO] Start recognition, Ctrl+C to exit。", file=sys.stderr)

    while not stop["v"]:
        ok, frame = cap.read()
        if not ok: continue
        gray0 = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        proc = enhance(gray0)

        H, W = gray0.shape
        
        y1, y2 = int(H*0.35), int(H*0.65)
        x1, x2 = int(W*0.10), int(W*0.90)
        roi = proc[y1:y2, x1:x2].copy()

        results = try_decode_multi(roi)
        if not results:
            results = try_decode_multi(proc)  

        now = int(time.time()*1000)
        for s in results:
            code = s.data.decode("utf-8", errors="ignore")
            typ  = s.type
            
            x,y,w,h = s.rect
            if results is not None and s in results and roi is not None and roi.data is not None:
                
                if y1 < y2 and x1 < x2 and y>=0 and x>=0:
                    y += y1; x += x1
            x,y,w,h = clip_bbox(x,y,w,h,W, H)

            if not code: continue
            if code in last_seen and now - last_seen[code] < args.dedup_ms: continue
            last_seen[code] = now

            m = goods.get(code, {}); found = bool(m)
            event = {
                "ts": now, "code": code, "symbology": typ, "bbox": [x,y,w,h],
                "match": {"found": found, "sku": m.get("sku",""), "name": m.get("name",""), "price": m.get("price","")}
            }
            print(json.dumps(event, ensure_ascii=False), flush=True)

            if crops_dir:
                crop = frame[y:y+h, x:x+w].copy()
                name = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                cv2.imwrite(str(crops_dir / f"{name}_{typ}_{code}.jpg"), crop)

            if jsonl_fp:
                jsonl_fp.write(json.dumps(event, ensure_ascii=False)+"\n"); jsonl_fp.flush()
            if csv_writer:
                csv_writer.writerow([now, code, typ, x,y,w,h, int(found), m.get("sku",""), m.get("name",""), m.get("price","")])
                csv_fp.flush()

        if args.show and os.environ.get("DISPLAY"):
            cv2.imshow("barcode-boost", frame)
            if cv2.waitKey(1) & 0xFF == 27: break

    cap.release()
    if args.show and os.environ.get("DISPLAY"): cv2.destroyAllWindows()
    if jsonl_fp: jsonl_fp.close()
    if csv_fp: csv_fp.close()

if __name__ == "__main__":
    main()
