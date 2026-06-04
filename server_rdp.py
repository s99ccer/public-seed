"""
Server RDP - 브라우저에서 원격 윈도우 데스크톱 사용
================================================
실행: python server_rdp.py
접속: http://서버IP:5000

기능:
- Windows 화면 실시간 캡처 (PIL.ImageGrab)
- 마우스/키보드 입력 전달 (Win32 API)
- WebSocket 양방향 통신
- Nginx/IIS 리버스 프록시로 443에 연결 가능
"""

import json, io, time, ctypes, threading
from PIL import ImageGrab
from flask import Flask, render_template_string
from flask_sock import Sock

app = Flask(__name__)
sock = Sock(app)

# Win32 API setup
user32 = ctypes.windll.user32

# Virtual key code mapping
VK_MAP = {
    "Enter": 0x0D, "Backspace": 0x08, "Tab": 0x09, "Escape": 0x1B,
    "Shift": 0x10, "Control": 0x11, "Alt": 0x12, "CapsLock": 0x14,
    "ArrowUp": 0x26, "ArrowDown": 0x28, "ArrowLeft": 0x25, "ArrowRight": 0x27,
    "Delete": 0x2E, "Insert": 0x2D, "Home": 0x24, "End": 0x23,
    "PageUp": 0x21, "PageDown": 0x22, "Space": 0x20,
    "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73,
    "F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77,
    "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
}

def vk_from_key(key):
    if key in VK_MAP:
        return VK_MAP[key]
    if len(key) == 1:
        return ord(key.upper())
    return 0

def send_mouse_click(x, y, button="left"):
    user32.SetCursorPos(x, y)
    if button == 1:  # right
        user32.mouse_event(0x0008, 0, 0, 0, 0)  # RDOWN
        user32.mouse_event(0x0010, 0, 0, 0, 0)  # RUP
    else:
        user32.mouse_event(0x0002, 0, 0, 0, 0)  # LDOWN
        user32.mouse_event(0x0004, 0, 0, 0, 0)  # LUP

def send_mouse_down(x, y, button="left"):
    user32.SetCursorPos(x, y)
    if button == 1:
        user32.mouse_event(0x0008, 0, 0, 0, 0)
    else:
        user32.mouse_event(0x0002, 0, 0, 0, 0)

def send_mouse_up(button="left"):
    if button == 1:
        user32.mouse_event(0x0010, 0, 0, 0, 0)
    else:
        user32.mouse_event(0x0004, 0, 0, 0, 0)

def send_mouse_move(x, y):
    user32.SetCursorPos(x, y)

def send_scroll(dy):
    user32.mouse_event(0x0800, 0, 0, int(dy / 3), 0)  # WHEEL

def send_key_down(key):
    vk = vk_from_key(key)
    if vk:
        user32.keybd_event(vk, 0, 0, 0)

def send_key_up(key):
    vk = vk_from_key(key)
    if vk:
        user32.keybd_event(vk, 0, 0x0002, 0)

HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Remote Desktop</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#111;overflow:hidden;height:100vh;font-family:Arial,sans-serif;display:flex;flex-direction:column}
#bar{background:#1a1a2e;padding:6px 10px;display:flex;align-items:center;gap:8px;color:#fff;font-size:13px;flex-wrap:wrap}
#bar .dot{width:10px;height:10px;border-radius:50%;background:#0f0}
#bar .dot.off{background:#f00}
#bar .fps{color:#888;font-size:11px;margin-left:auto}
#wrap{flex:1;position:relative;overflow:hidden;display:flex;align-items:center;justify-content:center;background:#000}
#canvas{width:100%;height:100%;object-fit:contain;cursor:crosshair;image-rendering:pixelated}
#loading{position:absolute;color:#555;font-size:16px}
</style>
</head>
<body>
<div id="bar">
  <span class="dot" id="dot"></span>
  <span id="stat">Connecting...</span>
  <span class="fps" id="fps">0 FPS</span>
</div>
<div id="wrap">
  <canvas id="canvas"></canvas>
  <div id="loading">Waiting for stream...</div>
</div>
<script>
var c=document.getElementById("canvas"),ctx=c.getContext("2d"),
    w=document.getElementById("wrap"),dt=document.getElementById("dot"),
    st=document.getElementById("stat"),fp=document.getElementById("fps"),
    ws=null,t0=performance.now(),fc=0;

function connect(){
  ws=new WebSocket("ws://"+location.host+"/ws");
  ws.binaryType="arraybuffer";
  ws.onopen=function(){dt.className="dot";st.textContent="Connected";};
  ws.onclose=function(){dt.className="dot off";st.textContent="Retrying...";setTimeout(connect,2000);};
  ws.onerror=function(){st.textContent="Error";};
  ws.onmessage=function(e){
    if(typeof e.data==="string"){
      var d=JSON.parse(e.data);
      if(d.w&&d.h){c.width=d.w;c.height=d.h;document.getElementById("loading").style.display="none";}
      if(d.f!==undefined)fp.textContent=d.f+" FPS";
      return;
    }
    var b=new Uint8Array(e.data),im=new Image();
    im.onload=function(){ctx.drawImage(im,0,0);fc++;var t=(performance.now()-t0)/1000;if(t>=1){fp.textContent=Math.round(fc/t)+" FPS";fc=0;t0=performance.now();}};
    im.src=URL.createObjectURL(new Blob([b],{type:"image/jpeg"}));
  };
}
function s(o){if(ws&&ws.readyState===1)ws.send(JSON.stringify(o));}
function pos(e){
  var r=w.getBoundingClientRect(),cw=c.width||1,ch=c.height||1,cwd=c.clientWidth||1,chd=c.clientHeight||1;
  return{x:Math.round((e.clientX-r.left)*(cw/cwd)),y:Math.round((e.clientY-r.top)*(ch/chd))};
}
w.addEventListener("mousedown",function(e){var p=pos(e);s({a:"md",x:p.x,y:p.y,b:e.button});});
w.addEventListener("mouseup",function(e){s({a:"mu",b:e.button});});
w.addEventListener("mousemove",function(e){var p=pos(e);s({a:"mm",x:p.x,y:p.y});});
w.addEventListener("wheel",function(e){s({a:"wh",dy:e.deltaY});e.preventDefault();},{passive:false});
document.addEventListener("contextmenu",function(e){e.preventDefault();});
document.addEventListener("keydown",function(e){if(e.target.tagName==="INPUT"||e.target.tagName==="TEXTAREA")return;s({a:"kd",k:e.key});e.preventDefault();});
document.addEventListener("keyup",function(e){if(e.target.tagName==="INPUT"||e.target.tagName==="TEXTAREA")return;s({a:"ku",k:e.key});e.preventDefault();});
connect();
</script>
</body>
</html>"""

@app.route("/")
def index():
    return render_template_string(HTML)

@sock.route("/ws")
def ws_handler(ws):
    stop = False
    fps_counter = [0]
    fps_t0 = [time.time()]
    ws_lock = threading.Lock()

    def ws_send(data):
        with ws_lock:
            try:
                ws.send(data)
            except:
                pass

    # Send initial screen size
    try:
        img = ImageGrab.grab()
        ws_send(json.dumps({"w": img.size[0], "h": img.size[1]}))
    except:
        pass

    def get_viewer_rect():
        """Find browser window showing remote desktop, return (x1,y1,x2,y2) or None"""
        try:
            hwnd = user32.GetDesktopWindow()
            win = user32.FindWindowExW(0, 0, None, None)
            wins = []
            while win:
                buf = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(win, buf, 256)
                title = buf.value
                if title and ("Remote Desktop" in title or "localhost:5000" in title):
                    if user32.IsWindowVisible(win):
                        rect = ctypes.wintypes.RECT()
                        user32.GetWindowRect(win, ctypes.byref(rect))
                        sw = user32.GetSystemMetrics(0)  # screen width
                        sh = user32.GetSystemMetrics(1)  # screen height
                        # Check if window is on the primary screen
                        if rect.left < sw and rect.top < sh and rect.right > 0 and rect.bottom > 0:
                            return (rect.left, rect.top, rect.right, rect.bottom)
                win = user32.FindWindowExW(0, win, None, None)
        except:
            pass
        return None

    def send_frames():
        nonlocal stop
        while not stop:
            try:
                img = ImageGrab.grab()
                # Black out the viewer window to prevent infinite recursion
                vr = get_viewer_rect()
                if vr:
                    from PIL import ImageDraw
                    draw = ImageDraw.Draw(img)
                    draw.rectangle([vr[0], vr[1], vr[2], vr[3]], fill=(0, 0, 0))
                    # Add text "RDP Viewer Hidden"
                    try:
                        from PIL import ImageFont
                        font = ImageFont.load_default()
                        draw.text((vr[0]+8, vr[1]+8), "RDP Viewer Hidden", fill=(100, 100, 100), font=font)
                    except: pass
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=65, optimize=True)
                ws_send(buf.getvalue())

                fps_counter[0] += 1
                now = time.time()
                if now - fps_t0[0] >= 1.0:
                    ws_send(json.dumps({"f": fps_counter[0]}))
                    fps_counter[0] = 0
                    fps_t0[0] = now

                time.sleep(0.066)  # ~15 FPS
            except:
                stop = True
                break

    def recv_events():
        nonlocal stop
        while not stop:
            try:
                data = ws.receive()
                if isinstance(data, str) and data.startswith("{"):
                    msg = json.loads(data)
                    a = msg.get("a")
                    if a == "md":
                        send_mouse_down(msg["x"], msg["y"], msg.get("b", 0))
                    elif a == "mu":
                        send_mouse_up(msg.get("b", 0))
                    elif a == "mm":
                        send_mouse_move(msg["x"], msg["y"])
                    elif a == "wh":
                        send_scroll(msg.get("dy", 0))
                    elif a == "kd":
                        send_key_down(msg["k"])
                    elif a == "ku":
                        send_key_up(msg["k"])
            except:
                stop = True
                break

    t1 = threading.Thread(target=send_frames, daemon=True)
    t2 = threading.Thread(target=recv_events, daemon=True)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

if __name__ == "__main__":
    print("=" * 50)
    print("  Remote Desktop Server")
    print("  접속: http://127.0.0.1:5000")
    print("  종료: Ctrl+C")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
