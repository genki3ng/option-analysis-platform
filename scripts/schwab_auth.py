#!/usr/bin/env python3
"""
Schwab OAuth2 — 一次性 refresh_token 生成脚本（本地跑，不进 Vercel）。

用法：
    python3 scripts/schwab_auth.py

流程：
    1. 脚本打印一个 Schwab 授权 URL
    2. 你在浏览器打开，用 Schwab 客户账号登录、授权
    3. Schwab 把你重定向到 https://127.0.0.1/?code=XXX&...
    4. 浏览器会显示"无法连接"（正常 — 127.0.0.1 没东西）
    5. 你从地址栏复制完整 URL（含 ?code=...），粘贴给脚本
    6. 脚本用 code 换 access_token + refresh_token
    7. 打印 refresh_token；你把它设到 Vercel env var SCHWAB_REFRESH_TOKEN

refresh_token 有效期 7 天，到期需重跑此脚本。
"""
import base64
import urllib.parse
import urllib.request
import json
import sys
import getpass

CALLBACK_URL = "https://127.0.0.1"
AUTH_URL = "https://api.schwabapi.com/v1/oauth/authorize"
TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"


def main():
    print("=" * 70)
    print("Schwab OAuth — refresh_token 生成器")
    print("=" * 70)

    # Step 0: collect credentials
    client_id = input("\n粘贴你的 Client ID (App Key): ").strip()
    if not client_id:
        sys.exit("Client ID 不能为空")
    client_secret = getpass.getpass("粘贴你的 Client Secret (隐藏输入): ").strip()
    if not client_secret:
        sys.exit("Client Secret 不能为空")

    # Step 1: print auth URL
    auth_url = (
        f"{AUTH_URL}"
        f"?client_id={urllib.parse.quote(client_id)}"
        f"&redirect_uri={urllib.parse.quote(CALLBACK_URL)}"
    )

    print("\n" + "=" * 70)
    print("Step 1: 打开下面这个 URL（浏览器登录 Schwab + 授权）：")
    print("=" * 70)
    print(f"\n{auth_url}\n")
    print("=" * 70)
    print("Step 2: 授权完成后，浏览器会跳到 https://127.0.0.1/?code=...")
    print("        会显示 'Unable to connect' — 这是预期的（127.0.0.1 没东西）")
    print("=" * 70)
    print("Step 3: 从浏览器地址栏复制完整 URL，粘贴到下面：\n")

    redirected_url = input("粘贴完整重定向 URL: ").strip()
    if not redirected_url:
        sys.exit("URL 不能为空")

    # Extract code
    parsed = urllib.parse.urlparse(redirected_url)
    qs = urllib.parse.parse_qs(parsed.query)
    code = qs.get("code", [None])[0]
    if not code:
        sys.exit(f"URL 里没找到 code 参数。URL: {redirected_url}")

    print(f"\n✓ 拿到 authorization code: {code[:30]}...")

    # Step 4: exchange code for tokens
    print("\n用 code 换 access_token + refresh_token...")
    auth_str = f"{client_id}:{client_secret}"
    auth_b64 = base64.b64encode(auth_str.encode()).decode()

    body = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": CALLBACK_URL,
    }).encode()

    req = urllib.request.Request(
        TOKEN_URL,
        data=body,
        headers={
            "Authorization": f"Basic {auth_b64}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    try:
        resp = urllib.request.urlopen(req, timeout=30)
        tokens = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"\nHTTP {e.code}: {e.read().decode()}")
    except Exception as e:
        sys.exit(f"\n异常: {e}")

    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    expires_in = tokens.get("expires_in")

    if not refresh_token:
        sys.exit(f"\n响应里没 refresh_token: {tokens}")

    print("\n" + "=" * 70)
    print("✅ 成功！")
    print("=" * 70)
    print(f"\naccess_token (有效 {expires_in}s ≈ {expires_in // 60} min):")
    print(f"  {access_token[:40]}...")
    print(f"\nrefresh_token (有效 7 天):")
    print(f"  {refresh_token}")
    print("\n" + "=" * 70)
    print("下一步：把上面这个 refresh_token 设到 Vercel 环境变量")
    print("=" * 70)
    print("\n用 Vercel API 一行搞定（替换 <TOKEN> 后跑）：")
    print(f"""
curl -X POST 'https://api.vercel.com/v10/projects/option-analysis-platform-web/env' \\
  -H 'Authorization: Bearer <VERCEL_TOKEN>' \\
  -H 'Content-Type: application/json' \\
  -d '{{"key":"SCHWAB_REFRESH_TOKEN","value":"{refresh_token}","type":"encrypted","target":["production","preview","development"]}}'
""")
    print("或者把这个 token 贴回聊天，我用现成的脚本帮你设。")
    print()


if __name__ == "__main__":
    main()
