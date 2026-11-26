import webview
import traceback

try:
    print("Starting WebView GUI test...")
    window = webview.create_window(
        "Smart Campus - GUI Test",
        html="<h1>Smart Campus</h1><p>WebView is working!</p>",
        width=900,
        height=600
    )
    webview.start(gui="edgechromium", debug=True)
    print("WebView closed normally.")

except Exception:
    traceback.print_exc()
    input("Press Enter to exit...")
