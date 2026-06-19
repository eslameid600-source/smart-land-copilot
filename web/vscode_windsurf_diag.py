#!/usr/bin/env python3
"""
VS Code Windsurf (Codeium) diagnostic script

Checks:
 - VS Code version and installed extensions (searching for Windsurf/Codeium)
 - VS Code setting `workbench.experimental.webViewExternalBrowser`
 - Proxy environment and VS Code `http.proxy` setting
 - Scans VS Code log files for network/auth related errors

Outputs a concise diagnostic and can optionally enable external webview browser.

Usage:
  python tools/vscode_windsurf_diag.py --report
  python tools/vscode_windsurf_diag.py --apply-external-browser

Note: Run on the same machine where VS Code is running. On Windows it inspects %APPDATA%/Code logs and settings.
"""
from __future__ import print_function
import argparse
import json
import os
import platform
import re
import shutil
import subprocess
from datetime import datetime

def run_cmd(cmd):
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, shell=False)
        return out.decode('utf-8', errors='replace').strip()
    except Exception as e:
        return None

def get_code_version():
    # prefer `code` (stable) then `code-insiders`
    for exe in ("code", "code-insiders", "code.cmd"):
        try:
            out = run_cmd([exe, "--version"])
            if out:
                lines = out.splitlines()
                return exe, lines[0].strip(), lines
        except Exception:
            continue
    return None, None, None

def list_extensions():
    try:
        out = run_cmd(["code", "--list-extensions", "--show-versions"]) or ""
    except Exception:
        out = None
    if out is None:
        return None
    return [l.strip() for l in out.splitlines() if l.strip()]

def find_settings_files():
    paths = []
    system = platform.system()
    # User settings path
    if system == 'Windows':
        appdata = os.environ.get('APPDATA')
        if appdata:
            paths.append(os.path.join(appdata, 'Code', 'User', 'settings.json'))
            paths.append(os.path.join(appdata, 'Code - Insiders', 'User', 'settings.json'))
    else:
        home = os.path.expanduser('~')
        paths.append(os.path.join(home, '.config', 'Code', 'User', 'settings.json'))
        paths.append(os.path.join(home, '.config', 'Code - Insiders', 'User', 'settings.json'))
    # workspace-level (in current folder .vscode)
    cwd = os.getcwd()
    workspace = os.path.join(cwd, '.vscode', 'settings.json')
    paths.append(workspace)
    return [p for p in paths if p and os.path.exists(p)]

def load_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None

def check_webview_setting(settings):
    # the requested key
    key = 'workbench.experimental.webViewExternalBrowser'
    if not settings:
        return None, None
    # settings may be a list (multiple files); accept dict
    if isinstance(settings, dict):
        val = settings.get(key)
        return key, val
    return key, None

def check_proxy_env():
    env_keys = ['HTTP_PROXY', 'http_proxy', 'HTTPS_PROXY', 'https_proxy', 'NO_PROXY', 'no_proxy']
    found = {}
    for k in env_keys:
        v = os.environ.get(k)
        if v:
            found[k] = v
    return found

def scan_vscode_logs(limit_lines=500):
    system = platform.system()
    logs = []
    if system == 'Windows':
        appdata = os.environ.get('APPDATA')
        base = os.path.join(appdata, 'Code', 'logs') if appdata else None
    else:
        home = os.path.expanduser('~')
        base = os.path.join(home, '.config', 'Code', 'logs')
    if not base or not os.path.exists(base):
        return []
    # find newest folder
    try:
        folders = sorted([os.path.join(base, d) for d in os.listdir(base)], key=os.path.getmtime, reverse=True)
    except Exception:
        return []
    for folder in folders[:3]:
        for root, _, files in os.walk(folder):
            for f in files:
                if f.endswith('.log'):
                    path = os.path.join(root, f)
                    try:
                        with open(path, 'r', encoding='utf-8', errors='replace') as fh:
                            data = fh.read().splitlines()
                            tail = data[-limit_lines:]
                            logs.append((path, tail))
                    except Exception:
                        continue
    return logs

def search_patterns_in_logs(logs):
    patterns = [r'ERROR', r'ERR_', r'Failed', r'401', r'403', r'proxy', r'authentication', r'oauth', r'invalid', r'Network']
    hits = []
    for path, lines in logs:
        for i, line in enumerate(lines[-200:]):
            for p in patterns:
                if re.search(p, line, re.IGNORECASE):
                    hits.append((path, i+1, p, line.strip()))
    return hits

def analyze_report(code_info, exts, settings_files, settings_data, proxy_env, log_hits):
    reasons = []
    suggestions = []
    # VS Code & extension
    exe, version, raw = code_info
    installed_windsurf = False
    if exts:
        for e in exts:
            if 'windsurf' in e.lower() or 'codeium' in e.lower():
                installed_windsurf = True
    # webview setting
    key = 'workbench.experimental.webViewExternalBrowser'
    webview_val = None
    for sd in settings_data:
        if isinstance(sd, dict) and key in sd:
            webview_val = sd[key]
            break

    if webview_val is False or webview_val in (0, 'false', 'False'):
        reasons.append('Embedded webview in use (webViewExternalBrowser is false).')
        suggestions.append('Enable `workbench.experimental.webViewExternalBrowser` (set to true) to use external browser.')
    elif webview_val is True:
        reasons.append('External browser is configured for webviews (webViewExternalBrowser is true).')

    # proxy or env
    if proxy_env:
        reasons.append('Proxy environment variables detected.')
        suggestions.append('Verify proxy allows auth endpoints; set `http.proxy` in VS Code settings if needed.')

    # log hits
    auth_errors = [h for h in log_hits if re.search(r'oauth|auth|401|invalid', h[3], re.IGNORECASE)]
    network_errors = [h for h in log_hits if re.search(r'proxy|Network|Failed|ERR', h[3], re.IGNORECASE)]
    if auth_errors:
        reasons.append('Authentication-related errors found in logs.')
        suggestions.append('Inspect auth error lines and confirm client id/redirect URIs and tokens.')
    if network_errors:
        reasons.append('Network-related errors found in logs.')
        suggestions.append('Check system proxy, firewall, or corporate network restrictions.')

    # final categorization
    category = 'unknown'
    if auth_errors and not network_errors:
        category = 'auth'
    elif network_errors and not auth_errors:
        category = 'network'
    elif (webview_val is False or webview_val is None) and not network_errors:
        category = 'embedded-webview'
    elif network_errors and webview_val in (False, None):
        category = 'network+embedded'

    report = {
        'vscode_executable': exe,
        'vscode_version': version,
        'windsurf_installed': installed_windsurf,
        'settings_files_checked': settings_files,
        'webview_setting': webview_val,
        'proxy_env': proxy_env,
        'log_hits': log_hits[:20],
        'reasons': reasons,
        'suggestions': suggestions,
        'category': category,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }
    return report

def write_report(report, out_path=None):
    text = []
    text.append('VS Code Diagnostic Report')
    text.append('Timestamp: %s' % report['timestamp'])
    text.append('VS Code: %s %s' % (report['vscode_executable'] or 'unknown', report['vscode_version'] or 'unknown'))
    text.append('Windsurf/Codeium installed: %s' % ('yes' if report['windsurf_installed'] else 'no'))
    text.append('WebView external browser setting: %s' % str(report['webview_setting']))
    text.append('Detected proxy env vars: %s' % (', '.join(report['proxy_env'].keys()) if report['proxy_env'] else 'none'))
    text.append('Detected issues:')
    for r in report['reasons']:
        text.append(' - ' + r)
    text.append('Suggested actions:')
    for s in report['suggestions']:
        text.append(' - ' + s)
    text.append('Recommended category: %s' % report['category'])

    text.append('\nDeveloper Tools Network Log capture instructions:')
    text.append('  1) In VS Code press Ctrl+Shift+I (or Help > Toggle Developer Tools).')
    text.append('  2) Switch to Network tab, reproduce the login attempt.')
    text.append('  3) Right-click the network table and choose "Save all as HAR with content" or "Export HAR".')
    text.append('  4) Attach the HAR file for deeper analysis.')

    content = '\n'.join(text)
    if out_path:
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(content)
    print(content)

def set_webview_external_browser(value=True, settings_files=None):
    key = 'workbench.experimental.webViewExternalBrowser'
    if not settings_files:
        settings_files = find_settings_files()
    if not settings_files:
        # create user settings
        system = platform.system()
        if system == 'Windows':
            appdata = os.environ.get('APPDATA')
            cfg = os.path.join(appdata, 'Code', 'User')
        else:
            cfg = os.path.join(os.path.expanduser('~'), '.config', 'Code', 'User')
        os.makedirs(cfg, exist_ok=True)
        path = os.path.join(cfg, 'settings.json')
        settings_files = [path]

    for path in settings_files:
        data = {}
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = {}
        data[key] = value
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        print('Updated', path)

def main():
    p = argparse.ArgumentParser(description='VS Code Windsurf/Codeium diagnostic helper')
    p.add_argument('--report', action='store_true', help='Run checks and print report')
    p.add_argument('--apply-external-browser', action='store_true', help='Set webViewExternalBrowser = true in user settings')
    p.add_argument('--output', help='Write report to file')
    args = p.parse_args()

    exe, version, raw = get_code_version()
    exts = list_extensions()
    settings_files = find_settings_files()
    settings_data = [load_json(p) for p in settings_files]
    webview_key, webview_val = None, None
    for sd in settings_data:
        if isinstance(sd, dict) and 'workbench.experimental.webViewExternalBrowser' in sd:
            webview_key = 'workbench.experimental.webViewExternalBrowser'
            webview_val = sd.get(webview_key)
            break

    proxy_env = check_proxy_env()
    logs = scan_vscode_logs()
    hits = search_patterns_in_logs(logs)

    report = analyze_report((exe, version, raw), exts, settings_files, settings_data, proxy_env, hits)

    if args.apply_external_browser:
        set_webview_external_browser(True, settings_files)

    if args.report:
        write_report(report, args.output)
    else:
        # default: print short summary
        print('VS Code:', exe, version)
        print('Windsurf/Codeium installed:', 'yes' if report['windsurf_installed'] else 'no')
        print('webViewExternalBrowser:', report['webview_setting'])
        print('Proxy vars:', ','.join(proxy_env.keys()) if proxy_env else 'none')
        print('Suggested category:', report['category'])
        print('Run with --report for a detailed diagnostic and steps.')

if __name__ == '__main__':
    main()
