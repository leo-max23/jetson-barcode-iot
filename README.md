# 📦 Jetson Barcode IoT

Using **Jetson Nano** with a USB camera to recognize barcodes (EAN-13, QR, etc.) and upload product info to the **cloud (Baidu IoT)** via MQTT.

---

## ✨ Features
- 🔍 Real-time barcode detection using **OpenCV + pyzbar**
- 📑 Product database lookup (**CSV → SKU, Name, Price**)
- 📝 Export results as **JSON / CSV / Logs**
- 🖼️ Optional **barcode snapshot saving**
- ☁️ Cloud integration via **MQTT (Baidu IoT Core)**
- 🎥 Works with **low-cost USB cameras** (e.g. 640×480 MJPEG/YUYV)

---

## 📂 Project Structure
barcode_demo/
├── barcode_cam.py # Main barcode recognition script
├── uploader_mqtt_baidu.py # MQTT uploader for Baidu IoT Core
├── goods_db.csv # Example product database

---

## 🚀 Quick Start

### 1️⃣ Install Dependencies

sudo apt update
sudo apt install -y python3-opencv v4l-utils
pip3 install pyzbar paho-mqtt

2️⃣ Prepare Product Database

Example goods_db.csv:

barcode,sku,name,price
6934502301850,SKU001,Dongpeng 500ml,5.00
6928804014570,SKU002,Coca-Cola 330ml,3.00
6928804014648,SKU003,Sprite 330ml,3.00
6921168509256,SKU004,Nongfu Spring 550ml,2.00


3️⃣ Run Barcode Recognition
python3 barcode_cam.py --device /dev/video0 --width 640 --height 480 --csv goods_db.csv --show


Example output:
{
  "ts": 1757850528056,
  "code": "6928804014570",
  "symbology": "EAN13",
  "bbox": [88, 262, 303, 15],
  "match": {
    "found": true,
    "sku": "SKU002",
    "name": "Coca-Cola 330ml",
    "price": "3.00"
  }
}


4️⃣ Upload to Baidu IoT Core
python3 uploader_mqtt_baidu.py


This script publishes recognition results to:

$iot/{deviceName}/user/test

