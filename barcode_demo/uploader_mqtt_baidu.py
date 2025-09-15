#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import time, json, argparse, os, ssl
import paho.mqtt.client as mqtt

def tail_f(path):
    while not os.path.exists(path):
        time.sleep(0.5)
    with open(path, "r", encoding="utf-8") as f:
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.1); continue
            yield line.rstrip("\n")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="logs/events.jsonl", help="识别事件 JSONL 文件")
    ap.add_argument("--host", required=True, help="MQTT broker host（百度物接入接入点）")
    ap.add_argument("--port", type=int, default=8884, help="端口：8884(TLS) 或 1883(明文)")
    ap.add_argument("--client-id", required=True, help="Client ID（控制台给的或自定义）")
    ap.add_argument("--username", required=True, help="用户名/设备名（控制台）")
    ap.add_argument("--password", required=True, help="密码/设备密钥（控制台）")
    ap.add_argument("--topic", required=True, help="发布主题，如 /devices/<deviceName>/events")
    ap.add_argument("--cafile", default="", help="CA 根证书路径（TLS 推荐配置）")
    ap.add_argument("--qos", type=int, default=1, choices=[0,1,2], help="MQTT QoS")
    ap.add_argument("--keepalive", type=int, default=60)
    args = ap.parse_args()

    cli = mqtt.Client(client_id=args.client_id, clean_session=True)
    cli.username_pw_set(args.username, args.password)

    if args.port == 8884:
        
        if args.cafile:
            cli.tls_set(ca_certs=args.cafile, certfile=None, keyfile=None,
                        cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS, ciphers=None)
        else:
            cli.tls_set()  
        cli.tls_insecure_set(False)

   
    cli.on_connect = lambda c,u,f,rc: print(f"[CONNECT] rc={rc}")
    cli.on_publish = lambda c,u,mid:  print(f"[PUB] mid={mid}")

    print(f"[INFO] Connecting to {args.host}:{args.port} ...")
    cli.connect(args.host, args.port, keepalive=args.keepalive)
    cli.loop_start()

    print(f"[INFO] Tail {args.file} -> MQTT {args.topic} (QoS={args.qos})")
    for line in tail_f(args.file):
        try:
            evt = json.loads(line)   
            
            cli.publish(args.topic, payload=json.dumps(evt, ensure_ascii=False),
                        qos=args.qos, retain=False)
        except Exception as e:
            print("[SKIP]", e)

if __name__ == "__main__":
    main()
