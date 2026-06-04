import asyncio, base64, json, struct, sys
from flask import Flask, render_template_string
from flask_sock import Sock
from playwright.async_api import async_playwright

app = Flask(__name__)
sock = Sock(app)
page = None

HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Remote Browser</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#1a1a1a;display:flex;flex-direction:column;height:100vh;font-family:Arial,sans-serif}
#toolbar{background:#2d2d2d;padding:5px 8px;display:flex;gap:4px;align-items:center;flex-wrap:wrap}
#toolbar input{flex:1;min-width:80px;padding:4px 8px;border:1px solid #555;border-radius:3px;background:#3d3d3d;color:#fff;font-size:13px}
#toolbar button{padding:4px 10px;border:none;border-radius:3px;background:#0d6efd;color:#fff;cursor:pointer;font-size:13px}
#toolbar button:hover{background:#0b5ed7}
#toolbar .addr{color:#aaa;font-size:12px;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#wrap{flex:1;position:relative;overflow:hidden;background:#111}
#screen{width:100%;height:100%;object-fit:contain;cursor:crosshair;display:none}
#loading{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#666;font-size:18px;flex-direction:column;gap:12px}
#loading .spinner{width:40px;height:40px;border:4px solid #333;border-top-color:#0d6efd;border-radius:50%;animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
#status{position:absolute;bottom:6px;right:8px;color:#0a0;font-size:11px;background:rgba(0,0,0,.7);padding:2px 6px;border-radius:3px;display:none}
</style>
</head>
<body>
<div id="toolbar">
  <button onclick="goBack()">←</button>
  <button onclick="goForward()">→</button>
  <button onclick="refresh()">↻</button>
  <input id="urlbar" placeholder="URL 입력 후 Enter" onkeydown="if(event.key==='Enter')navigate()"/>
  <button onclick="navigate()">Go</button>
  <span class="addr" id="addr"></span>
</div>
<div id="wrap">
  <div id="loading"><div class="spinner"></div><span>Loading...</span></div>
  <img id="screen"/>
  <div id="status">Connected</div>
</div>
<script>
const img = document.getElementById("screen");
const wrap = document.getElementById("wrap");
const load = document.getElementById("loading");
const urlbar = document.getElementById("urlbar");
const addr = document.getElementById("addr");
const st = document.getElementById("status");
var ws = null;

function connect() {
  ws = new WebSocket("ws://"+location.host+"/ws");
  ws.onopen = function() {
    st.style.display = "block";
    st.textContent = "Connected";
  };
  ws.onmessage = function(e) {
    if (typeof e.data === "string") {
      if (e.data.startsWith("url:")) addr.textContent = e.data.slice(4);
      else if (e.data.startsWith("title:")) document.title = e.data.slice(6);
      else if (e.data === "pong") st.textContent = "Connected";
      return;
    }
    const blob = e.data;
    img.src = URL.createObjectURL(blob);
    img.onload = function() {
      img.style.display = "block";
      load.style.display = "none";
    };
  };
  ws.onclose = function() {
    st.textContent = "Disconnected";
    setTimeout(connect, 1000);
  };
  ws.onerror = function() { st.textContent = "Error"; };
}

function getPos(e) {
  const r = wrap.getBoundingClientRect();
  const sx = img.naturalWidth / img.clientWidth;
  const sy = img.naturalHeight / img.clientHeight;
  return { x: Math.round((e.clientX - r.left) * sx), y: Math.round((e.clientY - r.top) * sy) };
}

wrap.addEventListener("mousedown", function(e) {
  var p = getPos(e);
  ws.send(JSON.stringify({action:"click", x:p.x, y:p.y, button:e.button}));
});
wrap.addEventListener("mouseup", function(e) {
  var p = getPos(e);
  ws.send(JSON.stringify({action:"mouseup", x:p.x, y:p.y, button:e.button}));
});
wrap.addEventListener("mousemove", function(e) {
  var p = getPos(e);
  ws.send(JSON.stringify({action:"mousemove", x:p.x, y:p.y}));
});
wrap.addEventListener("wheel", function(e) {
  ws.send(JSON.stringify({action:"wheel", dx:e.deltaX, dy:e.deltaY}));
  e.preventDefault();
}, {passive:false});
document.addEventListener("keydown", function(e) {
  if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
  ws.send(JSON.stringify({action:"key", key:e.key, code:e.code, ctrl:e.ctrlKey, alt:e.altKey, shift:e.shiftKey}));
  e.preventDefault();
});
document.addEventListener("keyup", function(e) {
  if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
  ws.send(JSON.stringify({action:"keyup", key:e.key, code:e.code}));
});
function navigate() { ws.send(JSON.stringify({action:"navigate", url:urlbar.value})); }
function goBack() { ws.send(JSON.stringify({action:"back"})); }
function goForward() { ws.send(JSON.stringify({action:"forward"})); }
function refresh() { ws.send(JSON.stringify({action:"refresh"})); }

connect();
</script>
</body>
</html>"""

@app.route("/")
def index():
    return render_template_string(HTML)

@sock.route("/ws")
def browser_io(ws):
    global page
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(handle_client(ws, page))

async def send_screenshot(ws, page):
    while True:
        try:
            buf = await page.screenshot(type="jpeg", quality=70)
            await ws.send(buf)
            info = await page.evaluate("()=>({url:location.href, title:document.title})")
            try:
                await ws.send(f"url:{info['url']}")
                await ws.send(f"title:{info['title']}")
            except: pass
            await asyncio.sleep(0.05)
        except:
            break

async def handle_client(ws, page):
    send_task = asyncio.create_task(send_screenshot(ws, page))
    try:
        while True:
            data = await ws.receive()
            if isinstance(data, str) and data.startswith("{"):
                msg = json.loads(data)
                action = msg.get("action")
                if action == "click":
                    await page.mouse.click(msg["x"], msg["y"], button=msg.get("button","left"))
                elif action == "mouseup":
                    await page.mouse.up(button=msg.get("button","left"))
                elif action == "mousemove":
                    await page.mouse.move(msg["x"], msg["y"])
                elif action == "wheel":
                    await page.evaluate(f"window.scrollBy({msg.get('dx',0)},{msg.get('dy',0)})")
                elif action == "navigate":
                    url = msg["url"].strip()
                    if url:
                        if not url.startswith("http"):
                            if "." in url and " " not in url:
                                url = "https://" + url
                            else:
                                url = "https://www.google.com/search?q=" + url.replace(" ","+")
                        try:
                            await page.goto(url, timeout=15000)
                        except Exception as e:
                            print(f"Nav error: {e}")
                elif action == "back":
                    await page.go_back()
                elif action == "forward":
                    await page.go_forward()
                elif action == "refresh":
                    await page.reload()
                elif action == "key":
                    k = msg.get("key","")
                    if len(k) == 1: await page.keyboard.press(k)
                    elif k == "Enter": await page.keyboard.press("Enter")
                    elif k == "Backspace": await page.keyboard.press("Backspace")
                    elif k == "Tab": await page.keyboard.press("Tab")
                    elif k == "Escape": await page.keyboard.press("Escape")
                    elif k.startswith("Arrow"): await page.keyboard.press(k)
                elif action == "keyup":
                    pass
    except:
        pass
    finally:
        send_task.cancel()

async def main():
    global page
    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context(
        viewport={"width": 1280, "height": 720},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    )
    page = await context.new_page()
    await page.goto("about:blank")
    print("Browser ready. http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)

if __name__ == "__main__":
    asyncio.run(main())
