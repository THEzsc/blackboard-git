import Cocoa
import WebKit

final class Fetcher: NSObject, NSApplicationDelegate, WKScriptMessageHandler, WKNavigationDelegate, WKUIDelegate, NSWindowDelegate {
    var web: WKWebView!
    var window: NSWindow!
    var timer: Timer?
    var probing = false
    var exporting = false
    var total = 0
    var received = Set<String>()
    let args = CommandLine.arguments
    var output: URL { URL(fileURLWithPath: args[2], isDirectory: true) }
    var course: String { args[3] }
    func log(_ text: String) { FileHandle.standardError.write(Data((text + "\n").utf8)) }
    func stop(_ code: Int32, _ message: String) -> Never { log(message); Darwin.exit(code) }
    func applicationDidFinishLaunching(_ notification: Notification) {
        guard args.count == 5, let url = URL(string: args[1]), url.scheme == "https", url.host == "learn.intl.zju.edu.cn",
              course.range(of: "^_[0-9]+_[0-9]+$", options: .regularExpression) != nil else { stop(2, "Invalid course URL or arguments") }
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default()
        // An isolated JavaScript world prevents page scripts from writing local files via our bridge.
        config.userContentController.add(self, contentWorld: .defaultClient, name: "blackboardExport")
        web = WKWebView(frame: .zero, configuration: config)
        web.navigationDelegate = self
        web.uiDelegate = self
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1100, height: 760), styleMask: [.titled, .closable, .resizable, .miniaturizable], backing: .buffered, defer: false)
        window.title = "blackboard-git — 登录一次，后续复用会话"
        window.contentView = web
        window.delegate = self
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        log("Blackboard: checking saved session. Complete SSO in the window if requested.")
        web.load(URLRequest(url: url))
        timer = Timer.scheduledTimer(withTimeInterval: 3, repeats: true) { [weak self] _ in self?.probe() }
        DispatchQueue.main.asyncAfter(deadline: .now() + 900) { self.stop(3, "Login/export timed out; repository not updated") }
    }
    func windowWillClose(_ notification: Notification) { stop(3, "Login window closed; repository not updated") }
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if navigationAction.targetFrame == nil { webView.load(navigationAction.request) }
        return nil
    }
    func probe() {
        guard !probing, !exporting, web.url?.host == "learn.intl.zju.edu.cn", !web.isLoading else { return }
        let path = web.url?.path ?? ""
        if ["bb-zjdxsso", "customLogin", "authValidate", "/webapps/login", "cas/login", "index.jsp"].contains(where: path.contains) { return }
        probing = true
        web.callAsyncJavaScript("try { const r = await fetch('/learn/api/public/v1/courses/' + course, {credentials:'same-origin'}); return r.ok && (r.headers.get('content-type') || '').includes('json'); } catch { return false; }", arguments: ["course": course], in: nil, in: .defaultClient) { result in
            self.probing = false
            if case .success(let value) = result, (value as? Bool) == true { self.startExport() }
        }
    }
    func startExport() {
        exporting = true
        timer?.invalidate()
        do {
            try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
            let script = try String(contentsOfFile: args[4], encoding: .utf8)
            log("Blackboard: authenticated; downloading course content…")
            web.callAsyncJavaScript("window.__blackboardCourseId = course;\n" + script, arguments: ["course": course], in: nil, in: .defaultClient) { result in
                if case .failure(_) = result { self.stop(4, "Exporter could not run; repository not updated") }
            }
        } catch { stop(4, "Could not load exporter or create output directory") }
    }
    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
        guard exporting, message.frameInfo.isMainFrame, message.frameInfo.securityOrigin.host == "learn.intl.zju.edu.cn",
              let body = message.body as? [String: Any], let kind = body["kind"] as? String else { return }
        if kind == "progress", let text = body["text"] as? String { log(text); return }
        if kind == "done" {
            guard body["complete"] as? Bool == true, received.contains("manifest.json"), received.contains("announcements-source.html") else { stop(4, "Incomplete export; repository not updated") }
            stop(0, "Blackboard: online snapshot downloaded successfully")
        }
        guard kind == "file", let path = body["path"] as? String, let encoded = body["base64"] as? String,
              !path.hasPrefix("/"), !path.split(separator: "/").contains(".."), !path.contains("\\"),
              ["files/", "pages/"].contains(where: path.hasPrefix) || ["index.html", "manifest.json", "announcements-source.html"].contains(path),
              let data = Data(base64Encoded: encoded), !received.contains(path) else { stop(4, "Invalid exporter output") }
        total += data.count
        guard total < 320 * 1024 * 1024 else { stop(4, "Export exceeds size limit") }
        do {
            let target = output.appendingPathComponent(path)
            try FileManager.default.createDirectory(at: target.deletingLastPathComponent(), withIntermediateDirectories: true)
            try data.write(to: target, options: .atomic)
            received.insert(path)
        } catch { stop(4, "Unable to save exported file") }
    }
}
let app = NSApplication.shared
let delegate = Fetcher()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
